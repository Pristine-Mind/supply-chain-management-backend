import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Count, Q
from django.utils import timezone

from transport.models import (
    Delivery,
    DeliveryPriority,
    DeliveryTracking,
    Transporter,
    TransportStatus,
)
from transport.utils import calculate_delivery_distance, calculate_distance


class DeliveryAutoAssignmentService:
    """
    Service for automatically assigning deliveries to transporters based on various criteria.
    """

    def __init__(self):
        self.priority_weights = {
            DeliveryPriority.URGENT: 4.0,
            DeliveryPriority.HIGH: 3.0,
            DeliveryPriority.NORMAL: 2.0,
            DeliveryPriority.LOW: 1.0,
        }

        self.vehicle_capacity_multiplier = {
            "bike": 0.8,
            "car": 1.0,
            "van": 1.2,
            "truck": 1.5,
        }

    def get_available_transporters(self, delivery: Delivery) -> List[Transporter]:
        """
        Get list of available transporters who can handle the delivery.
        """
        # Base query for available transporters
        transporters = Transporter.objects.filter(
            is_available=True, is_verified=True, vehicle_capacity__gte=delivery.package_weight
        )

        # Filter by current active deliveries (max 3 active deliveries)
        transporters = transporters.annotate(
            active_deliveries=Count(
                "assigned_deliveries",
                filter=Q(
                    assigned_deliveries__status__in=[
                        TransportStatus.ASSIGNED,
                        TransportStatus.PICKED_UP,
                        TransportStatus.IN_TRANSIT,
                    ]
                ),
            )
        ).filter(active_deliveries__lt=3)

        return list(transporters)

    def calculate_transporter_score(self, transporter: Transporter, delivery: Delivery) -> Dict[str, Any]:
        """
        Calculate a score for each transporter based on multiple factors.

        Returns:
            Dictionary with score and breakdown of factors
        """
        score_breakdown = {}
        total_score = 0.0

        # 1. Distance factor (40% weight) - closer is better
        if (
            transporter.current_latitude
            and transporter.current_longitude
            and delivery.pickup_latitude
            and delivery.pickup_longitude
        ):

            distance = calculate_distance(
                float(transporter.current_latitude),
                float(transporter.current_longitude),
                float(delivery.pickup_latitude),
                float(delivery.pickup_longitude),
            )

            # Score decreases with distance (max 40 points for 0km, 0 points for 50km+)
            distance_score = max(0, 40 - (distance * 0.8))
            score_breakdown["distance"] = distance_score
            score_breakdown["distance_km"] = distance
            total_score += distance_score
        else:
            score_breakdown["distance"] = 0
            score_breakdown["distance_km"] = None

        # 2. Rating factor (25% weight)
        rating_score = float(transporter.rating) * 5  # Convert 0-5 rating to 0-25 points
        score_breakdown["rating"] = rating_score
        total_score += rating_score

        # 3. Success rate factor (20% weight)
        success_rate_score = transporter.success_rate * 0.2
        score_breakdown["success_rate"] = success_rate_score
        total_score += success_rate_score

        # 4. Workload factor (10% weight) - fewer active deliveries is better
        active_deliveries = transporter.assigned_deliveries.filter(
            status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
        ).count()
        workload_score = max(0, 10 - (active_deliveries * 3))
        score_breakdown["workload"] = workload_score
        score_breakdown["active_deliveries"] = active_deliveries
        total_score += workload_score

        # 5. Vehicle suitability factor (5% weight)
        vehicle_score = self.vehicle_capacity_multiplier.get(transporter.vehicle_type, 1.0) * 5
        score_breakdown["vehicle_suitability"] = vehicle_score
        total_score += vehicle_score

        return {"transporter": transporter, "total_score": total_score, "breakdown": score_breakdown}

    def assign_delivery(self, delivery_id: int) -> Dict[str, Any]:
        """
        Auto-assign a delivery to the best available transporter.

        Returns:
            Dictionary with assignment result and details
        """
        try:
            delivery = Delivery.objects.get(id=delivery_id, status=TransportStatus.AVAILABLE)
        except Delivery.DoesNotExist:
            return {"success": False, "error": "Delivery not found or not available for assignment"}

        # Get available transporters
        available_transporters = self.get_available_transporters(delivery)

        if not available_transporters:
            return {"success": False, "error": "No available transporters found for this delivery"}

        # Calculate scores for all available transporters
        transporter_scores = []
        for transporter in available_transporters:
            score_data = self.calculate_transporter_score(transporter, delivery)
            transporter_scores.append(score_data)

        # Sort by score (highest first)
        transporter_scores.sort(key=lambda x: x["total_score"], reverse=True)

        # Assign to the best transporter
        best_transporter = transporter_scores[0]["transporter"]

        # Update delivery distance if not already calculated
        if not delivery.distance_km:
            distance = calculate_delivery_distance(delivery)
            if distance:
                delivery.distance_km = distance

        # Assign the delivery
        delivery.assign_to_transporter(best_transporter)

        # Create tracking entry
        DeliveryTracking.objects.create(
            delivery=delivery,
            status=TransportStatus.ASSIGNED,
            notes=f"Auto-assigned to {best_transporter.user.get_full_name()}",
        )

        # Calculate estimated delivery time
        if delivery.distance_km:
            # Estimate 30 km/h average speed + 30 minutes for pickup/delivery
            estimated_travel_time = (delivery.distance_km / 30) * 60  # minutes
            estimated_total_time = estimated_travel_time + 30  # add 30 minutes buffer
            delivery.estimated_delivery_time = timezone.now() + timedelta(minutes=estimated_total_time)
            delivery.save()

        return {
            "success": True,
            "assigned_transporter": best_transporter,
            "delivery": delivery,
            "score_details": transporter_scores[0]["breakdown"],
            "alternatives": [
                {
                    "transporter_id": score["transporter"].id,
                    "transporter_name": score["transporter"].user.get_full_name(),
                    "score": score["total_score"],
                    "breakdown": score["breakdown"],
                }
                for score in transporter_scores[1:6]
            ],
            "distance_km": delivery.distance_km,
            "estimated_delivery_time": delivery.estimated_delivery_time,
            "message": f"Delivery assigned to {best_transporter.user.get_full_name()}",
        }

    def bulk_assign_deliveries(self, priority_filter: Optional[str] = None, max_assignments: int = 50) -> Dict[str, Any]:
        """
        Bulk assign multiple available deliveries.
        """
        start_time = time.time()

        # Get available deliveries
        deliveries = Delivery.objects.filter(status=TransportStatus.AVAILABLE)[:max_assignments]

        if priority_filter:
            deliveries = deliveries.filter(priority=priority_filter)

        # Sort by priority and requested pickup date
        deliveries = deliveries.order_by("priority", "requested_pickup_date")

        results = {"total_deliveries": deliveries.count(), "assigned": 0, "failed": 0, "assignments": [], "failures": []}

        for delivery in deliveries:
            assignment_result = self.assign_delivery(delivery.id)

            if assignment_result["success"]:
                results["assigned"] += 1
                results["assignments"].append(
                    {
                        "delivery_id": delivery.id,
                        "delivery_uuid": str(delivery.delivery_id),
                        "transporter_id": assignment_result["assigned_transporter"].id,
                        "transporter_name": assignment_result["assigned_transporter"].user.get_full_name(),
                        "distance_km": assignment_result.get("distance_km"),
                        "estimated_delivery": assignment_result.get("estimated_delivery_time"),
                        "score": assignment_result["score_details"],
                    }
                )
            else:
                results["failed"] += 1
                results["failures"].append(
                    {
                        "delivery_id": delivery.id,
                        "delivery_uuid": str(delivery.delivery_id),
                        "error": assignment_result["error"],
                    }
                )

        results["execution_time_seconds"] = round(time.time() - start_time, 2)
        return results
