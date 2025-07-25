from datetime import timedelta

from django.utils import timezone

from .models import Delivery, TransportStatus
from .utils import calculate_distance, send_delivery_notification


def send_delivery_reminders():
    """
    Send reminders for deliveries that are overdue or approaching deadline.
    """

    now = timezone.now()
    overdue_threshold = now - timedelta(hours=2)
    approaching_threshold = now + timedelta(hours=1)

    # Find overdue deliveries
    overdue_deliveries = Delivery.objects.filter(
        status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP], requested_pickup_date__lt=overdue_threshold
    )

    for delivery in overdue_deliveries:
        send_delivery_notification(delivery, "overdue", "transporter")

    # Find deliveries approaching deadline
    approaching_deliveries = Delivery.objects.filter(
        status=TransportStatus.ASSIGNED, requested_pickup_date__lt=approaching_threshold, requested_pickup_date__gt=now
    )

    for delivery in approaching_deliveries:
        send_delivery_notification(delivery, "reminder", "transporter")


def cleanup_expired_deliveries():
    """
    Clean up deliveries that have been pending for too long.
    """

    # Mark deliveries as expired if they've been available for more than 24 hours
    # and the pickup date has passed
    now = timezone.now()
    expiry_threshold = now - timedelta(hours=24)

    expired_deliveries = Delivery.objects.filter(
        status=TransportStatus.AVAILABLE, created_at__lt=expiry_threshold, requested_pickup_date__lt=now
    )

    expired_count = expired_deliveries.update(status=TransportStatus.CANCELLED)

    # Log the cleanup
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Cleaned up {expired_count} expired deliveries")

    return expired_count


def update_delivery_estimates():
    """
    Update estimated delivery times for in-transit deliveries.
    """

    in_transit_deliveries = Delivery.objects.filter(
        status=TransportStatus.IN_TRANSIT,
        transporter__current_latitude__isnull=False,
        transporter__current_longitude__isnull=False,
        delivery_latitude__isnull=False,
        delivery_longitude__isnull=False,
    )

    updated_count = 0

    for delivery in in_transit_deliveries:
        # Calculate remaining distance
        distance = calculate_distance(
            float(delivery.transporter.current_latitude),
            float(delivery.transporter.current_longitude),
            float(delivery.delivery_latitude),
            float(delivery.delivery_longitude),
        )

        # Estimate time based on average speed (30 km/h in city)
        estimated_hours = distance / 30
        estimated_time = timezone.now() + timedelta(hours=estimated_hours)

        delivery.estimated_delivery_time = estimated_time
        delivery.save(update_fields=["estimated_delivery_time"])
        updated_count += 1

    return updated_count
