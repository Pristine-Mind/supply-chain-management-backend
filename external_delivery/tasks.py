import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from transport.models import Delivery as TransportDelivery
from transport.models import TransportStatus

from .models import (
    APIUsageLog,
    ExternalDelivery,
    ExternalDeliveryStatus,
    RateLimitLog,
    WebhookEventType,
    WebhookLog,
)
from .utils import (
    format_webhook_delivery_data,
    send_webhook_notification,
    validate_delivery_data,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_external_delivery(self, delivery_id):
    """
    Process a new external delivery
    - Validate data
    - Create transport delivery
    - Send webhook notifications
    """
    try:
        delivery = ExternalDelivery.objects.get(id=delivery_id)

        # Validate delivery data
        errors = validate_delivery_data(
            {
                "package_value": delivery.package_value,
                "pickup_city": delivery.pickup_city,
                "delivery_city": delivery.delivery_city,
                "is_cod": delivery.is_cod,
                "cod_amount": delivery.cod_amount,
            },
            delivery.external_business,
        )

        if errors:
            delivery.status = ExternalDeliveryStatus.FAILED
            delivery.failure_reason = "; ".join(errors)
            delivery.save()

            # Send failure notification
            send_delivery_notifications.delay(delivery.id, ExternalDeliveryStatus.FAILED)
            return

        # Create corresponding transport delivery
        create_transport_delivery.delay(delivery_id)

        # Send creation notification
        send_delivery_notifications.delay(delivery.id, ExternalDeliveryStatus.PENDING)

        logger.info(f"Successfully processed external delivery {delivery.tracking_number}")

    except ExternalDelivery.DoesNotExist:
        logger.error(f"External delivery {delivery_id} not found")
    except Exception as exc:
        logger.error(f"Error processing external delivery {delivery_id}: {exc}")

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@shared_task(bind=True, max_retries=3)
def create_transport_delivery(self, external_delivery_id):
    """
    Create a transport delivery for external delivery
    """
    try:
        external_delivery = ExternalDelivery.objects.get(id=external_delivery_id)

        # Create transport delivery
        transport_delivery = TransportDelivery.objects.create(
            # Source relationship
            external_delivery=external_delivery,
            # Pickup information
            pickup_address=external_delivery.pickup_address,
            pickup_contact_name=external_delivery.pickup_name,
            pickup_contact_phone=external_delivery.pickup_phone,
            pickup_latitude=external_delivery.pickup_latitude,
            pickup_longitude=external_delivery.pickup_longitude,
            pickup_instructions=external_delivery.pickup_instructions or "",
            # Delivery information
            delivery_address=external_delivery.delivery_address,
            delivery_contact_name=external_delivery.delivery_name,
            delivery_contact_phone=external_delivery.delivery_phone,
            delivery_latitude=external_delivery.delivery_latitude,
            delivery_longitude=external_delivery.delivery_longitude,
            delivery_instructions=external_delivery.delivery_instructions or "",
            # Package information
            package_weight=external_delivery.package_weight,
            package_value=external_delivery.package_value or 0,
            # Scheduling
            requested_pickup_date=external_delivery.scheduled_pickup_time or timezone.now() + timezone.timedelta(hours=1),
            requested_delivery_date=external_delivery.scheduled_delivery_time or timezone.now() + timezone.timedelta(days=1),
            # Payment
            delivery_fee=external_delivery.delivery_fee,
            # Status
            status=TransportStatus.AVAILABLE,
        )

        logger.info(
            f"Created transport delivery {transport_delivery.id} for external delivery {external_delivery.tracking_number}"
        )

    except ExternalDelivery.DoesNotExist:
        logger.error(f"External delivery {external_delivery_id} not found")
    except Exception as exc:
        logger.error(f"Error creating transport delivery for {external_delivery_id}: {exc}")
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@shared_task(bind=True, max_retries=5)
def send_delivery_notifications(self, delivery_id, event_status):
    """
    Send webhook notifications for delivery status changes
    """
    try:
        delivery = ExternalDelivery.objects.get(id=delivery_id)
        business = delivery.external_business

        # Map status to event type
        event_type_mapping = {
            ExternalDeliveryStatus.PENDING: WebhookEventType.DELIVERY_CREATED,
            ExternalDeliveryStatus.ACCEPTED: WebhookEventType.DELIVERY_UPDATED,
            ExternalDeliveryStatus.PICKED_UP: WebhookEventType.DELIVERY_UPDATED,
            ExternalDeliveryStatus.IN_TRANSIT: WebhookEventType.DELIVERY_UPDATED,
            ExternalDeliveryStatus.DELIVERED: WebhookEventType.DELIVERY_DELIVERED,
            ExternalDeliveryStatus.CANCELLED: WebhookEventType.DELIVERY_CANCELLED,
            ExternalDeliveryStatus.FAILED: WebhookEventType.DELIVERY_FAILED,
        }

        event_type = event_type_mapping.get(event_status, WebhookEventType.DELIVERY_UPDATED)

        # Format delivery data for webhook
        webhook_data = format_webhook_delivery_data(delivery)

        # Send webhook notification
        result = send_webhook_notification(business=business, event_type=event_type, data=webhook_data, delivery=delivery)

        if result.get("success"):
            logger.info(f"Sent webhook notification for delivery {delivery.tracking_number}")
        else:
            logger.warning(f"Failed to send webhook notification: {result.get('error')}")

    except ExternalDelivery.DoesNotExist:
        logger.error(f"External delivery {delivery_id} not found for notifications")
    except Exception as exc:
        logger.error(f"Error sending notifications for delivery {delivery_id}: {exc}")

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@shared_task
def retry_failed_webhooks():
    """
    Retry failed webhook deliveries
    """
    now = timezone.now()

    # Get webhooks that need retry
    failed_webhooks = WebhookLog.objects.filter(success=False, retry_count__lt=3, next_retry_at__lte=now)

    for webhook_log in failed_webhooks:
        try:
            # Retry webhook
            result = send_webhook_notification(
                business=webhook_log.external_business,
                event_type=webhook_log.event_type,
                data=webhook_log.payload,
                webhook_url=webhook_log.webhook_url,
                delivery=webhook_log.delivery,
            )

            if result.get("success"):
                logger.info(f"Successfully retried webhook {webhook_log.id}")
            else:
                logger.warning(f"Retry failed for webhook {webhook_log.id}: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error retrying webhook {webhook_log.id}: {e}")


@shared_task
def sync_transport_delivery_status():
    """
    Sync status changes from transport deliveries to external deliveries
    """
    # Get transport deliveries with linked external deliveries
    transport_deliveries = TransportDelivery.objects.filter(external_delivery__isnull=False).select_related(
        "external_delivery"
    )

    status_mapping = {
        "available": ExternalDeliveryStatus.PENDING,
        "assigned": ExternalDeliveryStatus.ACCEPTED,
        "picked_up": ExternalDeliveryStatus.PICKED_UP,
        "in_transit": ExternalDeliveryStatus.IN_TRANSIT,
        "delivered": ExternalDeliveryStatus.DELIVERED,
        "cancelled": ExternalDeliveryStatus.CANCELLED,
        "failed": ExternalDeliveryStatus.FAILED,
    }

    for transport_delivery in transport_deliveries:
        external_delivery = transport_delivery.external_delivery

        # Map transport status to external status
        new_status = status_mapping.get(transport_delivery.status)

        if new_status and external_delivery.status != new_status:
            old_status = external_delivery.status

            # Update external delivery status
            external_delivery.update_status(
                new_status=new_status, reason=f"Updated from transport delivery {transport_delivery.id}"
            )

            # Send notification
            send_delivery_notifications.delay(external_delivery.id, new_status)

            logger.info(f"Synced status for {external_delivery.tracking_number}: " f"{old_status} -> {new_status}")


@shared_task
def cleanup_old_logs():
    """
    Clean up old logs to prevent database bloat
    """
    cutoff_date = timezone.now() - timezone.timedelta(days=90)

    # Clean up API usage logs older than 90 days
    deleted_api_logs = APIUsageLog.objects.filter(created_at__lt=cutoff_date).delete()

    # Clean up webhook logs older than 90 days (except failed ones)
    deleted_webhook_logs = WebhookLog.objects.filter(created_at__lt=cutoff_date, success=True).delete()

    # Clean up rate limit logs older than 30 days
    rate_limit_cutoff = timezone.now() - timezone.timedelta(days=30)
    deleted_rate_logs = RateLimitLog.objects.filter(created_at__lt=rate_limit_cutoff).delete()

    logger.info(
        f"Cleaned up logs: {deleted_api_logs[0]} API logs, "
        f"{deleted_webhook_logs[0]} webhook logs, "
        f"{deleted_rate_logs[0]} rate limit logs"
    )


@shared_task
def generate_daily_reports():
    """
    Generate daily reports for external business activity
    """
    from datetime import date

    from .models import ExternalBusiness

    today = date.today()

    for business in ExternalBusiness.objects.filter(status="approved"):
        # Get today's delivery stats
        today_deliveries = business.external_deliveries.filter(created_at__date=today)

        stats = {
            "business_name": business.business_name,
            "date": today.isoformat(),
            "total_deliveries": today_deliveries.count(),
            "successful_deliveries": today_deliveries.filter(status=ExternalDeliveryStatus.DELIVERED).count(),
            "failed_deliveries": today_deliveries.filter(status=ExternalDeliveryStatus.FAILED).count(),
            "revenue": sum(d.platform_commission or 0 for d in today_deliveries if d.platform_commission),
        }

        # Send daily report (implement as needed)
        logger.info(f"Daily report for {business.business_name}: {stats}")


@shared_task
def validate_webhook_endpoints():
    """
    Validate webhook endpoints for all businesses
    """
    from .models import ExternalBusiness

    for business in ExternalBusiness.objects.filter(status="approved", webhook_url__isnull=False).exclude(webhook_url=""):

        try:
            # Test webhook endpoint with ping
            result = send_webhook_notification(
                business=business,
                event_type="ping",
                data={"message": "Webhook validation test"},
                webhook_url=business.webhook_url,
            )

            if not result.get("success"):
                logger.warning(f"Webhook validation failed for {business.business_name}: " f"{result.get('error')}")

        except Exception as e:
            logger.error(f"Error validating webhook for {business.business_name}: {e}")


@shared_task(bind=True, max_retries=3)
def update_delivery_fees(self, delivery_id):
    """
    Update delivery fees based on current rates
    """
    try:
        delivery = ExternalDelivery.objects.get(id=delivery_id)

        # Recalculate fees
        fees = delivery.calculate_delivery_fee()
        delivery.delivery_fee = fees["delivery_fee"]
        delivery.platform_commission = fees["platform_commission"]
        delivery.transporter_earnings = fees["transporter_earnings"]
        delivery.save(update_fields=["delivery_fee", "platform_commission", "transporter_earnings"])

        logger.info(f"Updated fees for delivery {delivery.tracking_number}")

    except ExternalDelivery.DoesNotExist:
        logger.error(f"External delivery {delivery_id} not found for fee update")
    except Exception as exc:
        logger.error(f"Error updating fees for delivery {delivery_id}: {exc}")
        raise self.retry(exc=exc, countdown=2**self.request.retries)
