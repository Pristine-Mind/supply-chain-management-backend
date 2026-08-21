import logging

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from requests.exceptions import RequestException

from producer.models import Order, Sale

from .locks import lock_manager
from .models import Negotiation

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_negotiations():
    """
    Periodic task to mark old negotiations as rejected/expired.
    """
    from market.models import Negotiation

    expired_count = 0
    # Only check active negotiations
    active_negotiations = Negotiation.objects.filter(
        status__in=[Negotiation.Status.PENDING, Negotiation.Status.COUNTER_OFFER]
    )

    for neg in active_negotiations:
        if neg.mark_as_expired():
            expired_count += 1

    return f"Marked {expired_count} negotiations as expired."


@shared_task(bind=True, max_retries=3, default_retry_delay=300)  # 5 minute delay between retries
def send_email(self, to_email, subject, template_name, context):
    """
    Send an email with improved error handling for SendGrid issues.
    Retries on temporary failures, logs permanent failures.
    """
    try:
        if context and isinstance(context, dict) and "sale_id" in context:
            try:
                context["sale_obj"] = Sale.objects.get(id=context["sale_id"])
            except Sale.DoesNotExist:
                context["sale_obj"] = None
        # Add Order object if needed
        if context and isinstance(context, dict) and "order_id" in context:
            try:
                context["order_obj"] = Order.objects.get(id=context["order_id"])
            except Order.DoesNotExist:
                context["order_obj"] = None

        html_message = render_to_string(template_name, context)

        # Try sending email
        _ = send_mail(
            subject=subject,
            message=strip_tags(html_message),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Email sent successfully to {to_email} with subject: {subject}")
        return f"Email sent successfully to {to_email}"

    except Exception as e:
        error_msg = str(e).lower()

        # Check for SendGrid-specific errors that might be temporary
        if any(keyword in error_msg for keyword in ["maximum credits exceeded", "rate limit", "temporary", "timeout"]):
            logger.warning(f"Temporary email error for {to_email}: {e}")
            if self.request.retries < self.max_retries:
                # Exponential backoff: 5min, 10min, 20min
                countdown = 300 * (2**self.request.retries)
                raise self.retry(exc=e, countdown=countdown)
            else:
                logger.error(f"Email failed permanently after {self.max_retries} retries to {to_email}: {e}")
        else:
            # Log permanent errors (like invalid email, template not found, etc.)
            logger.error(f"Email error (non-retryable) to {to_email}: {e}")

        # Don't raise the exception - just log it and continue
        # This prevents the entire payment process from failing due to email issues
        return f"Email failed to {to_email}: {str(e)}"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms(self, to_number: str, body: str) -> dict:
    payload = {
        "token": settings.SPARROWSMS_API_KEY,
        "from": settings.SPARROWSMS_SENDER_ID,
        "to": to_number,
        "text": body,
    }

    try:
        resp = requests.post(
            settings.SPARROWSMS_ENDPOINT,
            data=payload,
            timeout=10,
        )

        data = resp.json()

    except requests.RequestException as exc:
        logger.exception("SparrowSMS request failed")

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)

        return {
            "code": 500,
            "status": "failed",
            "message": str(exc),
            "sms_code": "NETWORK_ERROR",
        }

    except ValueError:
        logger.error(
            "Invalid SparrowSMS response: %s",
            resp.text,
        )

        return {
            "code": 500,
            "status": "failed",
            "message": "Invalid response from SparrowSMS",
            "sms_code": "INVALID_RESPONSE",
        }

    code = str(data.get("response_code", ""))

    if code == "200":
        logger.info("SMS sent successfully to %s", to_number)

        return {
            "code": 200,
            "status": "success",
            "message": "Message sent successfully",
            "sms_code": "200",
        }

    logger.error(
        "SparrowSMS error: to=%s response=%s",
        to_number,
        data,
    )

    # Only retry actual temporary/unknown errors.
    # Do NOT retry invalid IP/token/receiver errors.
    if code not in {
        "1001",  # Invalid IP / API configuration
        "1002",  # Invalid token
        "1007",  # Invalid receiver
        "1011",  # Unknown receiver
        "1607",  # Authentication failure
    }:
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=Exception(f"SparrowSMS error: {data}"),
                countdown=60,
            )

    return {
        "code": 400,
        "status": "failed",
        "message": data.get("message", "SMS failed"),
        "sms_code": code or "0000",
    }


@shared_task
def update_recent_purchases():
    """
    Celery task to update recent_purchases_count for all marketplace products.
    This should be scheduled to run periodically (e.g., every hour).
    """
    try:
        from django.core.management import call_command

        _ = call_command("update_recent_purchases")
        logger.info("Recent purchases updated successfully")
        return "Successfully updated recent purchases count"
    except Exception as e:
        logger.error(f"Failed to update recent purchases: {e}")
        return f"Error updating recent purchases: {e}"


@shared_task
def cleanup_expired_locks():
    """
    Clean up expired locks and update negotiation status.
    Runs periodically via Celery.
    """
    try:
        # Find negotiations with expired locks
        expired_negotiations = Negotiation.objects.filter(
            Q(status=Negotiation.Status.LOCKED) & Q(lock_expires_at__lt=timezone.now())
        )

        for negotiation in expired_negotiations:
            # Release lock in Redis
            lock_data = lock_manager.get_lock_owner(negotiation.id)
            if lock_data:
                lock_manager.release_lock(negotiation.id, lock_data["user_id"], lock_data["lock_id"])

            # Update negotiation status
            negotiation.status = Negotiation.Status.COUNTER_OFFER
            negotiation.lock_owner = None
            negotiation.lock_expires_at = None
            negotiation.save()

            logger.info(f"Released expired lock for negotiation {negotiation.id}")

        # Clean up expired view permissions (optional)
        # This would require scanning Redis keys - consider using Redis TTL instead

        return f"Cleaned up {expired_negotiations.count()} expired locks"

    except Exception as e:
        logger.error(f"Error cleaning up expired locks: {e}")
        return f"Error: {e}"


@shared_task
def update_sales_banner_stats():
    """
    Periodic task to calculate and update sales banner statistics.
    Runs every 5 minutes to keep dashboard/banner data fresh.

    Calculates:
    - Total products sold (sum of all sale quantities)
    - Total revenue (sum of all sale prices * quantities)
    - Total number of sales transactions
    """
    from decimal import Decimal

    from django.db.models import Count, F, Sum

    from market.models import SalesBannerStats

    try:
        # Get or create the banner stats record
        stats = SalesBannerStats.get_or_create_banner_stats()

        # Calculate aggregated statistics from all marketplace sales
        sales_aggregates = MarketplaceSale.objects.filter(is_deleted=False, payment_status="completed").aggregate(
            total_quantity=Sum("quantity"),
            total_count=Count("id"),
            # Calculate revenue: sum of total_amount
            total_revenue=Sum("total_amount"),
        )

        # Update the statistics
        stats.total_products_sold = sales_aggregates["total_quantity"] or 0
        stats.total_sales_count = sales_aggregates["total_count"] or 0
        stats.total_revenue = Decimal(str(sales_aggregates["total_revenue"] or 0))
        stats.save()

        logger.info(
            f"Updated sales banner stats: {stats.total_products_sold} products sold, "
            f"${stats.total_revenue} revenue, {stats.total_sales_count} transactions"
        )

        return {
            "status": "success",
            "total_products_sold": stats.total_products_sold,
            "total_revenue": float(stats.total_revenue),
            "total_sales_count": stats.total_sales_count,
            "updated_at": stats.last_updated.isoformat(),
        }

    except Exception as e:
        logger.error(f"Error updating sales banner stats: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
