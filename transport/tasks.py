import logging
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from .models import (
    Delivery,
    DeliveryPriority,
    DeliveryTracking,
    Transporter,
    TransporterStatus,
    TransportStatus,
)
from .utils import calculate_distance, send_delivery_notification

logger = logging.getLogger(__name__)


def send_delivery_reminders():
    """
    Send reminders for deliveries that are overdue or approaching deadline.
    Enhanced with priority handling and multiple notification types.
    """
    now = timezone.now()

    priority_thresholds = {
        DeliveryPriority.URGENT: {"overdue": timedelta(minutes=30), "approaching": timedelta(minutes=15)},
        DeliveryPriority.SAME_DAY: {"overdue": timedelta(hours=1), "approaching": timedelta(minutes=30)},
        DeliveryPriority.HIGH: {"overdue": timedelta(hours=2), "approaching": timedelta(hours=1)},
        DeliveryPriority.NORMAL: {"overdue": timedelta(hours=4), "approaching": timedelta(hours=2)},
        DeliveryPriority.LOW: {"overdue": timedelta(hours=8), "approaching": timedelta(hours=4)},
    }

    notification_counts = {"overdue_sent": 0, "reminder_sent": 0, "escalated": 0, "failed": 0}

    try:
        for priority, thresholds in priority_thresholds.items():
            overdue_threshold = now - thresholds["overdue"]
            approaching_threshold = now + thresholds["approaching"]

            overdue_deliveries = Delivery.objects.filter(
                Q(status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT])
                & Q(priority=priority)
                & (Q(requested_pickup_date__lt=overdue_threshold) | Q(requested_delivery_date__lt=now))
            ).select_related("transporter__user", "marketplace_sale")

            for delivery in overdue_deliveries:
                try:
                    if delivery.requested_delivery_date < now - timedelta(hours=24):
                        send_delivery_notification(delivery, "escalation", "admin")
                        notification_counts["escalated"] += 1

                        if delivery.priority in [
                            DeliveryPriority.URGENT,
                            DeliveryPriority.SAME_DAY,
                        ] and delivery.requested_delivery_date < now - timedelta(hours=48):
                            delivery.status = TransportStatus.FAILED
                            delivery.save()

                            DeliveryTracking.objects.create(
                                delivery=delivery,
                                status=TransportStatus.FAILED,
                                notes="Automatically marked as failed due to extended delay",
                            )
                    else:
                        send_delivery_notification(delivery, "overdue", "transporter")
                        send_delivery_notification(delivery, "overdue", "customer")
                        notification_counts["overdue_sent"] += 1

                except Exception as e:
                    logger.error(f"Failed to send overdue notification for delivery {delivery.tracking_number}: {e}")
                    notification_counts["failed"] += 1

            approaching_deliveries = Delivery.objects.filter(
                status=TransportStatus.ASSIGNED, priority=priority, requested_pickup_date__range=[now, approaching_threshold]
            ).select_related("transporter__user")

            for delivery in approaching_deliveries:
                try:
                    send_delivery_notification(delivery, "reminder", "transporter")
                    notification_counts["reminder_sent"] += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder for delivery {delivery.tracking_number}: {e}")
                    notification_counts["failed"] += 1

        logger.info(f"Delivery reminders completed: {notification_counts}")
        return notification_counts

    except Exception as e:
        logger.error(f"Error in send_delivery_reminders: {e}")
        return notification_counts


def cleanup_expired_deliveries():
    """
    Clean up deliveries that have been pending for too long.
    Enhanced with priority-based expiry and better logging.
    """
    now = timezone.now()
    cleanup_counts = {"expired": 0, "unassigned_cancelled": 0, "stuck_assignments": 0}

    try:
        with transaction.atomic():
            priority_expiry_hours = {
                DeliveryPriority.URGENT: 2,
                DeliveryPriority.SAME_DAY: 6,
                DeliveryPriority.HIGH: 12,
                DeliveryPriority.NORMAL: 24,
                DeliveryPriority.LOW: 48,
            }

            for priority, hours in priority_expiry_hours.items():
                expiry_threshold = now - timedelta(hours=hours)

                expired_deliveries = Delivery.objects.filter(
                    status=TransportStatus.AVAILABLE,
                    priority=priority,
                    created_at__lt=expiry_threshold,
                    requested_pickup_date__lt=now,
                )

                expired_count = expired_deliveries.update(
                    status=TransportStatus.CANCELLED,
                    cancelled_at=now,
                    cancellation_reason="Automatically cancelled - no transporter assigned within time limit",
                )
                cleanup_counts["expired"] += expired_count

                for delivery in expired_deliveries:
                    DeliveryTracking.objects.create(
                        delivery=delivery,
                        status=TransportStatus.CANCELLED,
                        notes="Auto-cancelled: No assignment within time limit",
                    )

            unassigned_overdue = Delivery.objects.filter(
                status=TransportStatus.AVAILABLE, requested_pickup_date__lt=now - timedelta(hours=4)
            ).update(
                status=TransportStatus.CANCELLED,
                cancelled_at=now,
                cancellation_reason="Pickup time passed without assignment",
            )
            cleanup_counts["unassigned_cancelled"] = unassigned_overdue

            stuck_threshold = now - timedelta(hours=6)
            stuck_deliveries = Delivery.objects.filter(
                status=TransportStatus.ASSIGNED,
                assigned_at__lt=stuck_threshold,
                requested_pickup_date__lt=now - timedelta(hours=2),
            )

            for delivery in stuck_deliveries:
                if delivery.transporter:
                    delivery.transporter.cancelled_deliveries += 1
                    delivery.transporter.save(update_fields=["cancelled_deliveries"])

                delivery.status = TransportStatus.AVAILABLE
                delivery.transporter = None
                delivery.assigned_at = None
                delivery.save()

                DeliveryTracking.objects.create(
                    delivery=delivery,
                    status=TransportStatus.AVAILABLE,
                    notes="Assignment released due to inactivity - made available again",
                )
                cleanup_counts["stuck_assignments"] += 1

        logger.info(f"Cleanup completed: {cleanup_counts}")
        return cleanup_counts

    except Exception as e:
        logger.error(f"Error in cleanup_expired_deliveries: {e}")
        return cleanup_counts


def update_delivery_estimates():
    """
    Update estimated delivery times for in-transit deliveries.
    Enhanced with dynamic speed calculation and route optimization.
    """
    updated_counts = {"estimates_updated": 0, "routes_optimized": 0, "stale_locations": 0}

    try:
        in_transit_deliveries = Delivery.objects.filter(
            status__in=[TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT],
            transporter__current_latitude__isnull=False,
            transporter__current_longitude__isnull=False,
            delivery_latitude__isnull=False,
            delivery_longitude__isnull=False,
        ).select_related("transporter")

        for delivery in in_transit_deliveries:
            try:
                transporter = delivery.transporter

                if transporter.last_location_update and transporter.last_location_update < timezone.now() - timedelta(
                    minutes=30
                ):
                    updated_counts["stale_locations"] += 1
                    continue

                distance = calculate_distance(
                    float(transporter.current_latitude),
                    float(transporter.current_longitude),
                    float(delivery.delivery_latitude),
                    float(delivery.delivery_longitude),
                )

                speed = calculate_dynamic_speed(transporter.vehicle_type, timezone.now())

                base_time_hours = distance / speed

                if delivery.priority == DeliveryPriority.URGENT:
                    buffer_multiplier = 1.1
                elif delivery.priority == DeliveryPriority.SAME_DAY:
                    buffer_multiplier = 1.2
                else:
                    buffer_multiplier = 1.3

                if distance > 50:
                    buffer_multiplier += 0.2

                estimated_hours = base_time_hours * buffer_multiplier
                estimated_time = timezone.now() + timedelta(hours=estimated_hours)

                delivery.estimated_delivery_time = estimated_time
                delivery.distance_km = Decimal(str(round(distance, 2)))
                delivery.save(update_fields=["estimated_delivery_time", "distance_km"])

                updated_counts["estimates_updated"] += 1

                if delivery.requested_delivery_date < timezone.now():
                    delay_hours = (timezone.now() - delivery.requested_delivery_date).total_seconds() / 3600
                    if delay_hours > 2:
                        DeliveryTracking.objects.create(
                            delivery=delivery,
                            status=delivery.status,
                            latitude=transporter.current_latitude,
                            longitude=transporter.current_longitude,
                            notes=f"Delivery delayed by {delay_hours:.1f} hours. New ETA: {estimated_time.strftime('%H:%M')}",
                        )

            except Exception as e:
                logger.error(f"Failed to update estimate for delivery {delivery.tracking_number}: {e}")

        updated_counts["routes_optimized"] = optimize_transporter_routes()

        logger.info(f"Delivery estimates updated: {updated_counts}")
        return updated_counts

    except Exception as e:
        logger.error(f"Error in update_delivery_estimates: {e}")
        return updated_counts


def calculate_dynamic_speed(vehicle_type: str, current_time) -> float:
    """Calculate dynamic speed based on vehicle type and time of day."""
    base_speeds = {
        "bike": 35,
        "bicycle": 15,
        "car": 40,
        "van": 35,
        "truck": 30,
        "other": 30,
    }

    base_speed = base_speeds.get(vehicle_type, 30)

    hour = current_time.hour
    if 7 <= hour <= 9 or 17 <= hour <= 19:
        speed_multiplier = 0.6
    elif 22 <= hour or hour <= 6:
        speed_multiplier = 1.2
    else:
        speed_multiplier = 1.0

    return base_speed * speed_multiplier


def optimize_transporter_routes():
    """Optimize routes for transporters with multiple assigned deliveries."""
    optimized_count = 0

    try:
        transporters_with_multiple = Transporter.objects.annotate(
            delivery_count=Count(
                "assigned_deliveries",
                filter=Q(assigned_deliveries__status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP]),
            )
        ).filter(delivery_count__gt=1)

        for transporter in transporters_with_multiple:
            deliveries = transporter.assigned_deliveries.filter(
                status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP]
            ).order_by("priority", "requested_pickup_date")

            if deliveries.count() > 1:
                optimized_count += 1
                DeliveryTracking.objects.create(
                    delivery=deliveries.first(),
                    status=deliveries.first().status,
                    notes=f"Route optimized for {deliveries.count()} deliveries",
                )

        return optimized_count

    except Exception as e:
        logger.error(f"Error in optimize_transporter_routes: {e}")
        return 0


def update_transporter_performance_metrics():
    """
    Update performance metrics for all active transporters.
    """
    updated_count = 0

    try:
        active_transporters = Transporter.objects.filter(status=TransporterStatus.ACTIVE)

        for transporter in active_transporters:
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_deliveries = transporter.assigned_deliveries.filter(created_at__gte=thirty_days_ago)

            if recent_deliveries.exists():
                total_recent = recent_deliveries.count()
                successful_recent = recent_deliveries.filter(status=TransportStatus.DELIVERED).count()

                recent_success_rate = (successful_recent / total_recent) * 100 if total_recent > 0 else 0

                completed_deliveries = recent_deliveries.filter(
                    status=TransportStatus.DELIVERED, picked_up_at__isnull=False, delivered_at__isnull=False
                )

                if completed_deliveries.exists():
                    avg_delivery_time = completed_deliveries.aggregate(avg_time=Avg(F("delivered_at") - F("picked_up_at")))[
                        "avg_time"
                    ]

                    cache.set(
                        f"transporter_metrics_{transporter.id}",
                        {
                            "recent_success_rate": recent_success_rate,
                            "avg_delivery_time_hours": avg_delivery_time.total_seconds() / 3600 if avg_delivery_time else 0,
                            "last_updated": timezone.now().isoformat(),
                        },
                        timeout=3600,
                    )

                updated_count += 1

        logger.info(f"Updated performance metrics for {updated_count} transporters")
        return updated_count

    except Exception as e:
        logger.error(f"Error in update_transporter_performance_metrics: {e}")
        return 0


def check_transporter_availability():
    """
    Check and update transporter availability based on location updates and document expiry.
    """
    updates = {"set_offline": 0, "documents_expired": 0, "reactivated": 0}

    try:
        now = timezone.now()

        stale_location_threshold = now - timedelta(hours=2)
        offline_count = Transporter.objects.filter(
            status=TransporterStatus.ACTIVE, last_location_update__lt=stale_location_threshold
        ).update(status=TransporterStatus.OFFLINE)

        updates["set_offline"] = offline_count

        expired_docs_count = Transporter.objects.filter(
            Q(insurance_expiry__lte=now.date()) | Q(license_expiry__lte=now.date()),
            status__in=[TransporterStatus.ACTIVE, TransporterStatus.OFFLINE],
        ).update(status=TransporterStatus.SUSPENDED, is_available=False)

        updates["documents_expired"] = expired_docs_count

        recent_threshold = now - timedelta(minutes=30)
        reactivated_count = Transporter.objects.filter(
            status=TransporterStatus.OFFLINE,
            last_location_update__gte=recent_threshold,
            insurance_expiry__gt=now.date(),
            license_expiry__gt=now.date(),
        ).update(status=TransporterStatus.ACTIVE)

        updates["reactivated"] = reactivated_count

        logger.info(f"Transporter availability check completed: {updates}")
        return updates

    except Exception as e:
        logger.error(f"Error in check_transporter_availability: {e}")
        return updates


def generate_delivery_analytics():
    """
    Generate delivery analytics and insights.
    """
    now = timezone.now()
    analytics = {}

    try:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        analytics["daily"] = {
            "total_deliveries": Delivery.objects.filter(created_at__gte=today_start).count(),
            "completed_deliveries": Delivery.objects.filter(delivered_at__gte=today_start).count(),
            "pending_deliveries": Delivery.objects.filter(
                status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
            ).count(),
            "cancelled_deliveries": Delivery.objects.filter(cancelled_at__gte=today_start).count(),
        }

        completed_today = Delivery.objects.filter(delivered_at__gte=today_start, picked_up_at__isnull=False)

        if completed_today.exists():
            avg_delivery_time = completed_today.aggregate(avg_time=Avg(F("delivered_at") - F("picked_up_at")))["avg_time"]

            analytics["performance"] = {
                "avg_delivery_time_hours": avg_delivery_time.total_seconds() / 3600 if avg_delivery_time else 0,
                "on_time_rate": calculate_on_time_delivery_rate(completed_today),
            }

        cache.set("delivery_analytics", analytics, timeout=300)

        logger.info("Delivery analytics generated successfully")
        return analytics

    except Exception as e:
        logger.error(f"Error in generate_delivery_analytics: {e}")
        return {}


def calculate_on_time_delivery_rate(deliveries):
    """Calculate the percentage of deliveries completed on time."""
    if not deliveries.exists():
        return 0

    on_time_count = 0
    total_count = deliveries.count()

    for delivery in deliveries:
        if delivery.delivered_at and delivery.requested_delivery_date:
            if delivery.delivered_at <= delivery.requested_delivery_date:
                on_time_count += 1

    return round((on_time_count / total_count) * 100, 2) if total_count > 0 else 0


def run_periodic_tasks():
    """
    Main function to run all periodic tasks.
    This can be called by a cron job or Celery beat.
    """
    task_results = {}

    logger.info("Starting periodic transport tasks...")

    try:
        task_results["reminders"] = send_delivery_reminders()
        task_results["cleanup"] = cleanup_expired_deliveries()
        task_results["estimates"] = update_delivery_estimates()
        task_results["performance"] = update_transporter_performance_metrics()
        task_results["availability"] = check_transporter_availability()
        task_results["analytics"] = generate_delivery_analytics()

        logger.info("All periodic transport tasks completed successfully")

    except Exception as e:
        logger.error(f"Error in run_periodic_tasks: {e}")
        task_results["error"] = str(e)

    return task_results
