import math
from datetime import timedelta
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Delivery, TransportStatus


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the distance between two points on Earth using the Haversine formula.
    Returns distance in kilometers.
    """
    R = 6371  # Earth's radius in kilometers

    # Convert degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def calculate_delivery_distance(delivery: Delivery) -> Optional[float]:
    """
    Calculate distance for a delivery from pickup to delivery location.

    Args:
        delivery: Delivery model instance

    Returns:
        Distance in kilometers or None if coordinates are missing
    """
    if all([delivery.pickup_latitude, delivery.pickup_longitude, delivery.delivery_latitude, delivery.delivery_longitude]):
        return calculate_distance(
            float(delivery.pickup_latitude),
            float(delivery.pickup_longitude),
            float(delivery.delivery_latitude),
            float(delivery.delivery_longitude),
        )
    return None


def send_delivery_notification(delivery: Delivery, event_type: str, recipient: str = "all"):
    """
    Send email notifications for delivery events.

    Args:
        delivery: Delivery instance
        event_type: Type of event ('assigned', 'picked_up', 'delivered', etc.)
        recipient: 'buyer', 'seller', 'transporter', or 'all'
    """
    try:
        subject_map = {
            "assigned": "Delivery Assigned - Order #{order_number}",
            "picked_up": "Package Picked Up - Order #{order_number}",
            "in_transit": "Package In Transit - Order #{order_number}",
            "delivered": "Package Delivered - Order #{order_number}",
            "cancelled": "Delivery Cancelled - Order #{order_number}",
        }

        subject = subject_map.get(event_type, "Delivery Update - Order #{order_number}")
        subject = subject.format(order_number=delivery.marketplace_sale.order_number)

        context = {
            "delivery": delivery,
            "event_type": event_type,
            "order": delivery.marketplace_sale,
        }

        # Prepare recipient list
        recipients = []

        if recipient in ["buyer", "all"] and delivery.marketplace_sale.buyer:
            recipients.append(delivery.marketplace_sale.buyer.email)

        if recipient in ["seller", "all"] and delivery.marketplace_sale.seller:
            recipients.append(delivery.marketplace_sale.seller.email)

        if recipient in ["transporter", "all"] and delivery.transporter:
            recipients.append(delivery.transporter.user.email)

        # Filter out empty emails
        recipients = [email for email in recipients if email]

        if recipients:
            html_message = render_to_string("transport/emails/delivery_notification.html", context)
            text_message = render_to_string("transport/emails/delivery_notification.txt", context)

            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                html_message=html_message,
                fail_silently=True,
            )

    except Exception as e:
        # Log the error but don't raise it to avoid breaking the main flow
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send delivery notification: {str(e)}")


def get_delivery_statistics() -> Dict[str, Any]:
    """
    Get comprehensive delivery statistics for dashboard.
    """

    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    stats = {}

    # Basic counts
    stats["total_deliveries"] = Delivery.objects.count()
    stats["pending_deliveries"] = Delivery.objects.filter(status=TransportStatus.AVAILABLE).count()
    stats["active_deliveries"] = Delivery.objects.filter(
        status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
    ).count()
    stats["completed_deliveries"] = Delivery.objects.filter(status=TransportStatus.DELIVERED).count()

    # Recent stats (last 30 days)
    stats["recent_deliveries"] = Delivery.objects.filter(created_at__gte=last_30_days).count()
    stats["recent_completed"] = Delivery.objects.filter(
        status=TransportStatus.DELIVERED, delivered_at__gte=last_30_days
    ).count()

    # Revenue stats
    stats["total_revenue"] = (
        Delivery.objects.filter(status=TransportStatus.DELIVERED).aggregate(total=Sum("delivery_fee"))["total"] or 0
    )

    stats["recent_revenue"] = (
        Delivery.objects.filter(status=TransportStatus.DELIVERED, delivered_at__gte=last_30_days).aggregate(
            total=Sum("delivery_fee")
        )["total"]
        or 0
    )

    # Average delivery time (in hours)
    completed_deliveries = Delivery.objects.filter(
        status=TransportStatus.DELIVERED, assigned_at__isnull=False, delivered_at__isnull=False
    )

    total_time = 0
    count = 0
    for delivery in completed_deliveries:
        if delivery.assigned_at and delivery.delivered_at:
            time_diff = delivery.delivered_at - delivery.assigned_at
            total_time += time_diff.total_seconds() / 3600  # Convert to hours
            count += 1

    stats["avg_delivery_time"] = round(total_time / count, 2) if count > 0 else 0

    # Transporter stats
    from .models import Transporter

    stats["total_transporters"] = Transporter.objects.count()
    stats["active_transporters"] = Transporter.objects.filter(is_available=True).count()
    stats["verified_transporters"] = Transporter.objects.filter(is_verified=True).count()

    # Performance by priority
    stats["priority_breakdown"] = Delivery.objects.values("priority").annotate(count=Count("id")).order_by("priority")

    # Status breakdown
    stats["status_breakdown"] = Delivery.objects.values("status").annotate(count=Count("id")).order_by("status")

    return stats


def find_nearby_transporters(latitude, longitude, radius=10, vehicle_capacity=None):
    """
    Find transporters within a specified radius of given coordinates.

    Args:
        latitude: Pickup latitude
        longitude: Pickup longitude
        radius: Search radius in kilometers (default: 10)
        vehicle_capacity: Minimum vehicle capacity required

    Returns:
        QuerySet of nearby available transporters
    """
    from .models import Transporter

    # Start with available and verified transporters
    transporters = Transporter.objects.filter(
        is_available=True, is_verified=True, current_latitude__isnull=False, current_longitude__isnull=False
    )

    # Filter by vehicle capacity if specified
    if vehicle_capacity:
        transporters = transporters.filter(vehicle_capacity__gte=vehicle_capacity)

    # Calculate distance for each transporter and filter by radius
    nearby_transporters = []
    for transporter in transporters:
        distance = calculate_distance(
            latitude, longitude, float(transporter.current_latitude), float(transporter.current_longitude)
        )

        if distance <= radius:
            transporter.distance = distance
            nearby_transporters.append(transporter)

    # Sort by distance and rating
    nearby_transporters.sort(key=lambda x: (x.distance, -float(x.rating)))

    return nearby_transporters


def auto_assign_delivery(delivery):
    """
    Automatically assign a delivery to the best available transporter.

    Args:
        delivery: Delivery instance to assign

    Returns:
        Transporter instance if assigned, None otherwise
    """
    if not delivery.pickup_latitude or not delivery.pickup_longitude:
        return None

    # Find nearby transporters
    nearby_transporters = find_nearby_transporters(
        delivery.pickup_latitude,
        delivery.pickup_longitude,
        radius=15,  # 15km radius
        vehicle_capacity=delivery.package_weight,
    )

    if nearby_transporters:
        # Assign to the best transporter (closest with highest rating)
        best_transporter = nearby_transporters[0]
        delivery.assign_to_transporter(best_transporter)

        # Send notification
        send_delivery_notification(delivery, "assigned", "all")

        return best_transporter

    return None


def generate_delivery_report(date_from=None, date_to=None, transporter=None):
    """
    Generate a comprehensive delivery report.

    Args:
        date_from: Start date for the report
        date_to: End date for the report
        transporter: Specific transporter to report on

    Returns:
        Dictionary containing report data
    """

    # Set default date range if not provided
    if not date_to:
        date_to = timezone.now()
    if not date_from:
        date_from = date_to - timedelta(days=30)

    # Base queryset
    queryset = Delivery.objects.filter(created_at__range=[date_from, date_to])

    if transporter:
        queryset = queryset.filter(transporter=transporter)

    # Basic metrics
    report = {
        "period": {"from": date_from, "to": date_to},
        "total_deliveries": queryset.count(),
        "completed_deliveries": queryset.filter(status=TransportStatus.DELIVERED).count(),
        "cancelled_deliveries": queryset.filter(status=TransportStatus.CANCELLED).count(),
        "pending_deliveries": queryset.filter(status=TransportStatus.AVAILABLE).count(),
    }

    # Calculate completion rate
    if report["total_deliveries"] > 0:
        report["completion_rate"] = round((report["completed_deliveries"] / report["total_deliveries"]) * 100, 2)
    else:
        report["completion_rate"] = 0

    # Revenue metrics
    completed_deliveries = queryset.filter(status=TransportStatus.DELIVERED)
    report["total_revenue"] = completed_deliveries.aggregate(total=Sum("delivery_fee"))["total"] or 0

    if completed_deliveries.count() > 0:
        report["avg_delivery_fee"] = completed_deliveries.aggregate(avg=Avg("delivery_fee"))["avg"] or 0
    else:
        report["avg_delivery_fee"] = 0

    # Performance metrics
    report["avg_package_weight"] = queryset.aggregate(avg=Avg("package_weight"))["avg"] or 0

    report["avg_distance"] = queryset.filter(distance_km__isnull=False).aggregate(avg=Avg("distance_km"))["avg"] or 0

    # Breakdown by status
    report["status_breakdown"] = list(queryset.values("status").annotate(count=Count("id")).order_by("status"))

    # Breakdown by priority
    report["priority_breakdown"] = list(queryset.values("priority").annotate(count=Count("id")).order_by("priority"))

    # Top transporters (if not filtering by specific transporter)
    if not transporter:
        report["top_transporters"] = list(
            queryset.filter(transporter__isnull=False)
            .values("transporter__user__first_name", "transporter__user__last_name")
            .annotate(delivery_count=Count("id"), total_revenue=Sum("delivery_fee"))
            .order_by("-delivery_count")[:10]
        )

    # Daily breakdown
    report["daily_breakdown"] = list(
        queryset.annotate(date=TruncDate("created_at")).values("date").annotate(count=Count("id")).order_by("date")
    )

    return report
