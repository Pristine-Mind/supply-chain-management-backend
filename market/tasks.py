import logging

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from requests.exceptions import RequestException

from producer.models import Order, Sale

logger = logging.getLogger(__name__)


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
    """
    Send an SMS via SparrowSMS.
    Retries up to 3 times on failure, waiting 60s between attempts.
    Returns a dict with keys: code, status, message, sms_code.
    """
    payload = {
        "token": settings.SPARROWSMS_API_KEY,
        "from": settings.SPARROWSMS_SENDER_ID,
        "to": to_number,
        "text": body,
    }
    headers = {
        "Authorization": settings.SPARROWSMS_API_KEY,
        "Idempotency-Key": f"{to_number}",
        "Accept": "application/json",
        "Accept-Language": "en-us",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(settings.SPARROWSMS_ENDPOINT, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except RequestException as exc:
        if exc.response is not None:
            try:
                data = exc.response.json()
            except ValueError:
                # If we can't parse JSON, retry for network issues
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=exc, countdown=60)
                raise Exception(f"SparrowSMS network error: {exc}")
        else:
            # Network issues - retry
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc, countdown=60)
            raise Exception(f"SparrowSMS connection error: {exc}")

    code = str(data.get("response_code", ""))
    mapping = {
        "200": {"code": 200, "status": "success", "message": "Message sent successfully", "sms_code": "200"},
        "1007": {"code": 401, "status": "error", "message": "Invalid Receiver", "sms_code": "1007"},
        "1607": {"code": 401, "status": "error", "message": "Authentication Failure", "sms_code": "1607"},
        "1002": {"code": 401, "status": "error", "message": "Invalid Token", "sms_code": "1002"},
        "1011": {"code": 401, "status": "error", "message": "Unknown Receiver", "sms_code": "1011"},
        "1001": {"code": 400, "status": "error", "message": "General API Error", "sms_code": "1001"},
    }

    result = mapping.get(
        code,
        {
            "code": 400,
            "status": "error",
            "message": data.get("message", "Unknown error"),
            "sms_code": code or "0000",
        },
    )

    # For known temporary errors (like 1001), retry
    if code in ["1001"] and self.request.retries < self.max_retries:
        raise self.retry(exc=Exception(f"SparrowSMS temporary error: {result}"), countdown=60)

    # For unknown errors that might be temporary, also retry
    if result["code"] != 200 and code not in mapping and self.request.retries < self.max_retries:
        raise self.retry(exc=Exception(f"SparrowSMS unknown error: {result}"), countdown=60)

    # Log errors but don't raise exceptions to avoid breaking task chains
    if result["code"] != 200:
        logger.error(f"SMS failed to {to_number} after {self.max_retries} retries: {result}")
        return {
            "code": result["code"],
            "status": "failed",
            "message": f"SMS failed: {result['message']}",
            "sms_code": result["sms_code"],
        }

    logger.info(f"SMS sent successfully to {to_number}")
    return result


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
