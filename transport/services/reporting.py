from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

from transport.models import (
    Delivery,
    DeliveryRating,
    Transporter,
    TransportStatus,
)


class DeliveryReportingService:
    """
    Comprehensive reporting service for delivery analytics and insights.
    """

    def get_delivery_overview(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Get overall delivery statistics for a given period.
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        deliveries = Delivery.objects.filter(created_at__range=[start_date, end_date])

        # Apply additional filters
        if filters:
            if filters.get("status"):
                deliveries = deliveries.filter(status=filters["status"])
            if filters.get("priority"):
                deliveries = deliveries.filter(priority=filters["priority"])
            if filters.get("transporter_id"):
                deliveries = deliveries.filter(transporter_id=filters["transporter_id"])

        # Status breakdown
        status_counts = deliveries.values("status").annotate(count=Count("id")).order_by("status")

        # Priority breakdown
        priority_counts = deliveries.values("priority").annotate(count=Count("id")).order_by("priority")

        # Calculate success rate
        total_completed = deliveries.filter(
            status__in=[TransportStatus.DELIVERED, TransportStatus.CANCELLED, TransportStatus.RETURNED]
        ).count()
        successful = deliveries.filter(status=TransportStatus.DELIVERED).count()
        success_rate = (successful / total_completed * 100) if total_completed > 0 else 0

        # Average delivery time for completed deliveries
        completed_deliveries = deliveries.filter(
            status=TransportStatus.DELIVERED, picked_up_at__isnull=False, delivered_at__isnull=False
        )

        avg_delivery_time = None
        if completed_deliveries.exists():
            delivery_times = []
            for delivery in completed_deliveries:
                time_diff = delivery.delivered_at - delivery.picked_up_at
                delivery_times.append(time_diff.total_seconds() / 3600)  # Convert to hours
            avg_delivery_time = sum(delivery_times) / len(delivery_times)

        # Revenue metrics
        revenue_metrics = deliveries.aggregate(
            total_revenue=Sum("delivery_fee"),
            avg_delivery_fee=Avg("delivery_fee"),
            total_distance=Sum("distance_km"),
            avg_distance=Avg("distance_km"),
            min_distance=Min("distance_km"),
            max_distance=Max("distance_km"),
        )

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "filters_applied": filters or {},
            "overview": {
                "total_deliveries": deliveries.count(),
                "successful_deliveries": successful,
                "cancelled_deliveries": deliveries.filter(status=TransportStatus.CANCELLED).count(),
                "pending_deliveries": deliveries.filter(status=TransportStatus.AVAILABLE).count(),
                "in_progress_deliveries": deliveries.filter(
                    status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
                ).count(),
                "success_rate": round(success_rate, 2),
                "avg_delivery_time_hours": round(avg_delivery_time, 2) if avg_delivery_time else None,
            },
            "status_breakdown": list(status_counts),
            "priority_breakdown": list(priority_counts),
            "revenue_metrics": revenue_metrics,
        }

    def get_transporter_performance(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get performance metrics for all transporters.
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        transporters = Transporter.objects.filter(assigned_deliveries__created_at__range=[start_date, end_date]).distinct()

        performance_data = []

        for transporter in transporters:
            deliveries = transporter.assigned_deliveries.filter(created_at__range=[start_date, end_date])

            # Basic metrics
            total_assigned = deliveries.count()
            delivered = deliveries.filter(status=TransportStatus.DELIVERED).count()
            cancelled = deliveries.filter(status=TransportStatus.CANCELLED).count()

            # Calculate average delivery time
            completed_deliveries = deliveries.filter(
                status=TransportStatus.DELIVERED, picked_up_at__isnull=False, delivered_at__isnull=False
            )

            avg_delivery_time = None
            if completed_deliveries.exists():
                delivery_times = []
                for delivery in completed_deliveries:
                    time_diff = delivery.delivered_at - delivery.picked_up_at
                    delivery_times.append(time_diff.total_seconds() / 3600)
                avg_delivery_time = sum(delivery_times) / len(delivery_times)

            # Revenue metrics
            revenue_data = deliveries.aggregate(total_revenue=Sum("delivery_fee"), total_distance=Sum("distance_km"))

            # Rating metrics
            ratings = DeliveryRating.objects.filter(transporter=transporter, created_at__range=[start_date, end_date])

            performance_data.append(
                {
                    "transporter": {
                        "id": transporter.id,
                        "name": transporter.user.get_full_name(),
                        "vehicle_type": transporter.vehicle_type,
                        "overall_rating": float(transporter.rating),
                    },
                    "period_metrics": {
                        "total_assigned": total_assigned,
                        "delivered": delivered,
                        "cancelled": cancelled,
                        "success_rate": round((delivered / total_assigned * 100) if total_assigned > 0 else 0, 2),
                        "avg_delivery_time_hours": round(avg_delivery_time, 2) if avg_delivery_time else None,
                        "total_revenue": revenue_data["total_revenue"] or 0,
                        "total_distance": revenue_data["total_distance"] or 0,
                        "period_ratings_count": ratings.count(),
                        "period_avg_rating": round(ratings.aggregate(avg=Avg("rating"))["avg"] or 0, 2),
                    },
                }
            )

        # Sort by success rate and total deliveries
        performance_data.sort(
            key=lambda x: (x["period_metrics"]["success_rate"], x["period_metrics"]["delivered"]), reverse=True
        )

        return performance_data

    def get_geographic_analysis(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Analyze delivery patterns by geographic areas.
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        deliveries = Delivery.objects.filter(
            created_at__range=[start_date, end_date],
            pickup_latitude__isnull=False,
            pickup_longitude__isnull=False,
            delivery_latitude__isnull=False,
            delivery_longitude__isnull=False,
        )

        # Calculate distance statistics
        distance_stats = deliveries.aggregate(
            avg_distance=Avg("distance_km"),
            min_distance=Min("distance_km"),
            max_distance=Max("distance_km"),
            total_distance=Sum("distance_km"),
        )

        # Group deliveries by distance ranges
        distance_ranges = [
            ("0-5km", 0, 5),
            ("5-10km", 5, 10),
            ("10-20km", 10, 20),
            ("20-50km", 20, 50),
            ("50km+", 50, float("inf")),
        ]

        distance_breakdown = []
        for range_name, min_dist, max_dist in distance_ranges:
            if max_dist == float("inf"):
                count = deliveries.filter(distance_km__gte=min_dist).count()
            else:
                count = deliveries.filter(distance_km__gte=min_dist, distance_km__lt=max_dist).count()

            distance_breakdown.append(
                {
                    "range": range_name,
                    "count": count,
                    "percentage": round((count / deliveries.count() * 100) if deliveries.count() > 0 else 0, 2),
                }
            )

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "distance_statistics": distance_stats,
            "distance_breakdown": distance_breakdown,
            "total_analyzed_deliveries": deliveries.count(),
        }

    def get_time_based_analysis(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Analyze delivery patterns over time.
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        deliveries = Delivery.objects.filter(created_at__range=[start_date, end_date])

        # Daily delivery counts
        daily_counts = (
            deliveries.extra(select={"day": "DATE(created_at)"})
            .values("day")
            .annotate(count=Count("id"), delivered=Count("id", filter=Q(status=TransportStatus.DELIVERED)))
            .order_by("day")
        )

        # Hourly patterns
        hourly_patterns = (
            deliveries.extra(select={"hour": "EXTRACT(hour FROM created_at)"})
            .values("hour")
            .annotate(count=Count("id"))
            .order_by("hour")
        )

        # Day of week patterns
        weekly_patterns = (
            deliveries.extra(select={"dow": "EXTRACT(dow FROM created_at)"})
            .values("dow")
            .annotate(count=Count("id"))
            .order_by("dow")
        )

        # Peak time analysis
        peak_hours = list(hourly_patterns)
        peak_hours.sort(key=lambda x: x["count"], reverse=True)

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "daily_trends": list(daily_counts),
            "hourly_patterns": list(hourly_patterns),
            "weekly_patterns": list(weekly_patterns),
            "peak_hours": peak_hours[:3],  # Top 3 busiest hours
        }

    def generate_comprehensive_report(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive report combining all analytics.
        """
        return {
            "overview": self.get_delivery_overview(start_date, end_date, filters),
            "transporter_performance": self.get_transporter_performance(start_date, end_date),
            "geographic_analysis": self.get_geographic_analysis(start_date, end_date),
            "time_analysis": self.get_time_based_analysis(start_date, end_date),
            "generated_at": timezone.now().isoformat(),
        }
