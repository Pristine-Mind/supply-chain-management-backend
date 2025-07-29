from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db import models
from django.db.models import (
    Avg,
    Case,
    Count,
    F,
    IntegerField,
    Max,
    Min,
    Q,
    Sum,
    Value,
    When,
)
from django.utils import timezone

from transport.models import (
    Delivery,
    DeliveryPriority,
    DeliveryRating,
    DeliveryRoute,
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

        if filters:
            if filters.get("status"):
                deliveries = deliveries.filter(status=filters["status"])
            if filters.get("priority"):
                deliveries = deliveries.filter(priority=filters["priority"])
            if filters.get("transporter_id"):
                deliveries = deliveries.filter(transporter_id=filters["transporter_id"])
            if filters.get("vehicle_type"):
                deliveries = deliveries.filter(transporter__vehicle_type=filters["vehicle_type"])
            if filters.get("fragile"):
                deliveries = deliveries.filter(fragile=filters["fragile"])

        status_counts = deliveries.values("status").annotate(count=Count("id")).order_by("status")

        priority_counts = deliveries.values("priority").annotate(count=Count("id")).order_by("priority")

        vehicle_type_counts = (
            deliveries.filter(transporter__isnull=False)
            .values("transporter__vehicle_type")
            .annotate(count=Count("id"))
            .order_by("transporter__vehicle_type")
        )

        total_completed = deliveries.filter(
            status__in=[
                TransportStatus.DELIVERED,
                TransportStatus.CANCELLED,
                TransportStatus.RETURNED,
                TransportStatus.FAILED,
            ]
        ).count()
        successful = deliveries.filter(status=TransportStatus.DELIVERED).count()
        success_rate = (successful / total_completed * 100) if total_completed > 0 else 0

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

        attempt_stats = deliveries.aggregate(
            avg_attempts=Avg("delivery_attempts"),
            max_attempts=Max("delivery_attempts"),
            failed_deliveries=Count("id", filter=Q(status=TransportStatus.FAILED)),
        )

        revenue_metrics = deliveries.aggregate(
            total_revenue=Sum("delivery_fee"),
            avg_delivery_fee=Avg("delivery_fee"),
            total_fuel_surcharge=Sum("fuel_surcharge"),
            total_distance=Sum("distance_km"),
            avg_distance=Avg("distance_km"),
            min_distance=Min("distance_km"),
            max_distance=Max("distance_km"),
            total_package_value=Sum("package_value"),
            avg_package_weight=Avg("package_weight"),
        )

        special_packages = {
            "fragile_count": deliveries.filter(fragile=True).count(),
            "signature_required_count": deliveries.filter(requires_signature=True).count(),
            "high_value_count": deliveries.filter(package_value__gte=1000).count(),
        }

        on_time_deliveries = deliveries.filter(
            status=TransportStatus.DELIVERED, delivered_at__lte=F("requested_delivery_date")
        ).count()
        total_delivered = deliveries.filter(status=TransportStatus.DELIVERED).count()
        on_time_rate = (on_time_deliveries / total_delivered * 100) if total_delivered > 0 else 0

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "filters_applied": filters or {},
            "overview": {
                "total_deliveries": deliveries.count(),
                "successful_deliveries": successful,
                "cancelled_deliveries": deliveries.filter(status=TransportStatus.CANCELLED).count(),
                "failed_deliveries": attempt_stats["failed_deliveries"],
                "pending_deliveries": deliveries.filter(status=TransportStatus.AVAILABLE).count(),
                "in_progress_deliveries": deliveries.filter(
                    status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
                ).count(),
                "success_rate": round(success_rate, 2),
                "on_time_delivery_rate": round(on_time_rate, 2),
                "avg_delivery_time_hours": round(avg_delivery_time, 2) if avg_delivery_time else None,
                "avg_delivery_attempts": round(attempt_stats["avg_attempts"], 2) if attempt_stats["avg_attempts"] else 0,
            },
            "status_breakdown": list(status_counts),
            "priority_breakdown": list(priority_counts),
            "vehicle_type_breakdown": list(vehicle_type_counts),
            "revenue_metrics": revenue_metrics,
            "special_packages": special_packages,
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

            total_assigned = deliveries.count()
            delivered = deliveries.filter(status=TransportStatus.DELIVERED).count()
            cancelled = deliveries.filter(status=TransportStatus.CANCELLED).count()
            failed = deliveries.filter(status=TransportStatus.FAILED).count()
            on_time = deliveries.filter(
                status=TransportStatus.DELIVERED, delivered_at__lte=F("requested_delivery_date")
            ).count()
            on_time_rate = (on_time / delivered * 100) if delivered > 0 else 0

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

            revenue_data = deliveries.aggregate(
                total_revenue=Sum("delivery_fee"),
                total_distance=Sum("distance_km"),
                avg_delivery_fee=Avg("delivery_fee"),
            )

            total_earnings = 0
            if revenue_data["total_revenue"]:
                commission_rate = transporter.commission_rate / 100
                total_earnings = revenue_data["total_revenue"] * (1 - commission_rate)

            ratings = DeliveryRating.objects.filter(transporter=transporter, created_at__range=[start_date, end_date])

            period_rating_stats = ratings.aggregate(
                count=Count("id"),
                avg_overall=Avg("overall_rating"),
                avg_punctuality=Avg("punctuality_rating"),
                avg_communication=Avg("communication_rating"),
                avg_handling=Avg("package_handling_rating"),
            )

            vehicle_capacity = transporter.vehicle_capacity
            total_weight_carried = deliveries.aggregate(total_weight=Sum("package_weight"))["total_weight"] or 0
            capacity_utilization = (
                (total_weight_carried / (vehicle_capacity * total_assigned) * 100)
                if total_assigned > 0 and vehicle_capacity > 0
                else 0
            )
            documents_expired = transporter.is_documents_expired()

            performance_data.append(
                {
                    "transporter": {
                        "id": transporter.id,
                        "name": transporter.user.get_full_name() or transporter.user.username,
                        "business_name": transporter.business_name,
                        "vehicle_type": transporter.vehicle_type,
                        "vehicle_capacity": float(transporter.vehicle_capacity),
                        "overall_rating": float(transporter.rating),
                        "is_verified": transporter.is_verified,
                        "status": transporter.status,
                        "documents_expired": documents_expired,
                        "service_radius": transporter.service_radius,
                    },
                    "period_metrics": {
                        "total_assigned": total_assigned,
                        "delivered": delivered,
                        "cancelled": cancelled,
                        "failed": failed,
                        "on_time_deliveries": on_time,
                        "success_rate": round((delivered / total_assigned * 100) if total_assigned > 0 else 0, 2),
                        "on_time_rate": round(on_time_rate, 2),
                        "cancellation_rate": round((cancelled / total_assigned * 100) if total_assigned > 0 else 0, 2),
                        "avg_delivery_time_hours": round(avg_delivery_time, 2) if avg_delivery_time else None,
                        "total_revenue": revenue_data["total_revenue"] or 0,
                        "total_earnings": round(total_earnings, 2),
                        "avg_delivery_fee": revenue_data["avg_delivery_fee"] or 0,
                        "total_distance": revenue_data["total_distance"] or 0,
                        "capacity_utilization": round(capacity_utilization, 2),
                        "period_ratings": {
                            "count": period_rating_stats["count"],
                            "avg_overall": round(period_rating_stats["avg_overall"] or 0, 2),
                            "avg_punctuality": round(period_rating_stats["avg_punctuality"] or 0, 2),
                            "avg_communication": round(period_rating_stats["avg_communication"] or 0, 2),
                            "avg_handling": round(period_rating_stats["avg_handling"] or 0, 2),
                        },
                    },
                    "lifetime_stats": {
                        "total_deliveries": transporter.total_deliveries,
                        "successful_deliveries": transporter.successful_deliveries,
                        "cancelled_deliveries": transporter.cancelled_deliveries,
                        "lifetime_success_rate": transporter.success_rate,
                        "cancellation_rate": transporter.cancellation_rate,
                        "total_earnings": float(transporter.earnings_total),
                    },
                }
            )

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

        distance_stats = deliveries.aggregate(
            avg_distance=Avg("distance_km"),
            min_distance=Min("distance_km"),
            max_distance=Max("distance_km"),
            total_distance=Sum("distance_km"),
        )

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
                avg_fee = deliveries.filter(distance_km__gte=min_dist).aggregate(avg_fee=Avg("delivery_fee"))["avg_fee"]
            else:
                count = deliveries.filter(distance_km__gte=min_dist, distance_km__lt=max_dist).count()
                avg_fee = deliveries.filter(distance_km__gte=min_dist, distance_km__lt=max_dist).aggregate(
                    avg_fee=Avg("delivery_fee")
                )["avg_fee"]

            distance_breakdown.append(
                {
                    "range": range_name,
                    "count": count,
                    "percentage": round((count / deliveries.count() * 100) if deliveries.count() > 0 else 0, 2),
                    "avg_delivery_fee": round(avg_fee, 2) if avg_fee else 0,
                }
            )

        transporter_coverage = Transporter.objects.aggregate(
            avg_service_radius=Avg("service_radius"),
            min_service_radius=Min("service_radius"),
            max_service_radius=Max("service_radius"),
        )

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "distance_statistics": distance_stats,
            "distance_breakdown": distance_breakdown,
            "transporter_coverage": transporter_coverage,
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

        daily_counts = (
            deliveries.extra(select={"day": "DATE(created_at)"})
            .values("day")
            .annotate(
                count=Count("id"),
                delivered=Count("id", filter=Q(status=TransportStatus.DELIVERED)),
                cancelled=Count("id", filter=Q(status=TransportStatus.CANCELLED)),
                avg_fee=Avg("delivery_fee"),
            )
            .order_by("day")
        )

        hourly_patterns = (
            deliveries.extra(select={"hour": "EXTRACT(hour FROM created_at)"})
            .values("hour")
            .annotate(
                count=Count("id"),
                avg_priority=Avg(
                    Case(
                        When(priority=DeliveryPriority.LOW, then=Value(1)),
                        When(priority=DeliveryPriority.NORMAL, then=Value(2)),
                        When(priority=DeliveryPriority.HIGH, then=Value(3)),
                        When(priority=DeliveryPriority.URGENT, then=Value(4)),
                        When(priority=DeliveryPriority.SAME_DAY, then=Value(5)),
                        output_field=IntegerField(),
                    )
                ),
            )
            .order_by("hour")
        )

        weekly_patterns = (
            deliveries.extra(select={"dow": "EXTRACT(dow FROM created_at)"})
            .values("dow")
            .annotate(
                count=Count("id"),
                delivered=Count("id", filter=Q(status=TransportStatus.DELIVERED)),
                avg_delivery_time=Avg(
                    Case(
                        When(
                            status=TransportStatus.DELIVERED,
                            picked_up_at__isnull=False,
                            delivered_at__isnull=False,
                            then=F("delivered_at") - F("picked_up_at"),
                        ),
                        output_field=models.DurationField(),
                    )
                ),
            )
            .order_by("dow")
        )

        peak_hours = list(hourly_patterns)
        peak_hours.sort(key=lambda x: x["count"], reverse=True)

        priority_trends = (
            deliveries.values("priority")
            .annotate(
                count=Count("id"),
                avg_delivery_time=Avg(
                    Case(
                        When(
                            status=TransportStatus.DELIVERED,
                            picked_up_at__isnull=False,
                            delivered_at__isnull=False,
                            then=F("delivered_at") - F("picked_up_at"),
                        ),
                        output_field=models.DurationField(),
                    )
                ),
                success_rate=Avg(
                    Case(
                        When(status=TransportStatus.DELIVERED, then=Value(100)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                ),
            )
            .order_by("priority")
        )

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "daily_trends": list(daily_counts),
            "hourly_patterns": list(hourly_patterns),
            "weekly_patterns": list(weekly_patterns),
            "priority_trends": list(priority_trends),
            "peak_hours": peak_hours[:3],
        }

    def get_route_optimization_analysis(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Analyze route optimization and efficiency metrics.
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        routes = DeliveryRoute.objects.filter(created_at__range=[start_date, end_date])

        route_stats = routes.aggregate(
            total_routes=Count("id"),
            completed_routes=Count("id", filter=Q(completed_at__isnull=False)),
            avg_estimated_distance=Avg("estimated_distance"),
            total_estimated_distance=Sum("estimated_distance"),
        )

        route_efficiency = []
        for route in routes.filter(completed_at__isnull=False):
            deliveries_in_route = route.deliveries.all()
            total_actual_distance = deliveries_in_route.aggregate(total=Sum("distance_km"))["total"] or 0
            estimated_distance = route.estimated_distance or 0

            efficiency = (estimated_distance / total_actual_distance * 100) if total_actual_distance > 0 else 0

            route_efficiency.append(
                {
                    "route_id": route.id,
                    "route_name": route.name,
                    "estimated_distance": float(estimated_distance),
                    "actual_distance": float(total_actual_distance),
                    "efficiency_percentage": round(efficiency, 2),
                    "delivery_count": deliveries_in_route.count(),
                    "transporter": route.transporter.user.get_full_name(),
                }
            )

        avg_deliveries_per_route = (
            routes.annotate(delivery_count=Count("deliveries")).aggregate(avg_deliveries=Avg("delivery_count"))[
                "avg_deliveries"
            ]
            or 0
        )

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "route_statistics": route_stats,
            "avg_deliveries_per_route": round(avg_deliveries_per_route, 2),
            "route_efficiency_details": route_efficiency,
            "completion_rate": round(
                (
                    (route_stats["completed_routes"] / route_stats["total_routes"] * 100)
                    if route_stats["total_routes"] > 0
                    else 0
                ),
                2,
            ),
        }

    def get_rating_analysis(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive analysis of delivery ratings and feedback.
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        ratings = DeliveryRating.objects.filter(created_at__range=[start_date, end_date])

        rating_stats = ratings.aggregate(
            total_ratings=Count("id"),
            avg_overall=Avg("overall_rating"),
            avg_punctuality=Avg("punctuality_rating"),
            avg_communication=Avg("communication_rating"),
            avg_handling=Avg("package_handling_rating"),
            anonymous_count=Count("id", filter=Q(is_anonymous=True)),
        )

        rating_distribution = []
        for i in range(1, 6):
            count = ratings.filter(overall_rating=i).count()
            rating_distribution.append(
                {
                    "rating": i,
                    "count": count,
                    "percentage": round((count / ratings.count() * 100) if ratings.count() > 0 else 0, 2),
                }
            )

        category_comparison = {
            "overall": rating_stats["avg_overall"] or 0,
            "punctuality": rating_stats["avg_punctuality"] or 0,
            "communication": rating_stats["avg_communication"] or 0,
            "package_handling": rating_stats["avg_handling"] or 0,
        }

        transporter_ratings = (
            ratings.values("transporter__user__first_name", "transporter__user__last_name", "transporter_id")
            .annotate(
                avg_rating=Avg("overall_rating"),
                rating_count=Count("id"),
                transporter_name=F("transporter__user__first_name"),
            )
            .filter(rating_count__gte=3)
            .order_by("-avg_rating")
        )

        return {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "rating_statistics": rating_stats,
            "rating_distribution": rating_distribution,
            "category_comparison": category_comparison,
            "top_performers": list(transporter_ratings[:10]),
            "anonymity_rate": round(
                (
                    (rating_stats["anonymous_count"] / rating_stats["total_ratings"] * 100)
                    if rating_stats["total_ratings"] > 0
                    else 0
                ),
                2,
            ),
        }

    def generate_comprehensive_report(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive report combining all analytics.
        """
        return {
            "metadata": {
                "generated_at": timezone.now().isoformat(),
                "period": {
                    "start_date": (start_date or timezone.now() - timedelta(days=30)).isoformat(),
                    "end_date": (end_date or timezone.now()).isoformat(),
                },
                "filters_applied": filters or {},
            },
            "overview": self.get_delivery_overview(start_date, end_date, filters),
            "transporter_performance": self.get_transporter_performance(start_date, end_date),
            "geographic_analysis": self.get_geographic_analysis(start_date, end_date),
            "time_analysis": self.get_time_based_analysis(start_date, end_date),
            "route_optimization": self.get_route_optimization_analysis(start_date, end_date),
            "rating_analysis": self.get_rating_analysis(start_date, end_date),
        }
