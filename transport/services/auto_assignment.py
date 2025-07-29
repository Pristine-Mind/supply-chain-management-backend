import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import F, Q
from django.utils import timezone

from transport.models import (
    Delivery,
    DeliveryPriority,
    Transporter,
    TransporterStatus,
    TransportStatus,
    VehicleType,
)
from transport.utils import calculate_delivery_distance, calculate_distance


class DeliveryAutoAssignmentService:
    """
    Enhanced service for automatically assigning deliveries to transporters based on various criteria.
    """

    def __init__(self):
        self.priority_weights = {
            DeliveryPriority.SAME_DAY: 5.0,
            DeliveryPriority.URGENT: 4.0,
            DeliveryPriority.HIGH: 3.0,
            DeliveryPriority.NORMAL: 2.0,
            DeliveryPriority.LOW: 1.0,
        }

        self.vehicle_capacity_multiplier = {
            VehicleType.BICYCLE: 0.6,
            VehicleType.BIKE: 0.8,
            VehicleType.CAR: 1.0,
            VehicleType.VAN: 1.2,
            VehicleType.TRUCK: 1.5,
            VehicleType.OTHER: 0.9,
        }

        self.vehicle_speeds = {
            VehicleType.BICYCLE: 15,
            VehicleType.BIKE: 35,
            VehicleType.CAR: 40,
            VehicleType.VAN: 35,
            VehicleType.TRUCK: 30,
            VehicleType.OTHER: 30,
        }

        self.max_active_deliveries = {
            VehicleType.BICYCLE: 2,
            VehicleType.BIKE: 3,
            VehicleType.CAR: 4,
            VehicleType.VAN: 6,
            VehicleType.TRUCK: 8,
            VehicleType.OTHER: 3,
        }

    def get_available_transporters(self, delivery: Delivery) -> List[Transporter]:
        """
        Get list of available transporters who can handle the delivery.
        """
        transporters = Transporter.objects.filter(
            is_available=True,
            is_verified=True,
            status=TransporterStatus.ACTIVE,
            vehicle_capacity__gte=delivery.package_weight,
        )

        current_date = timezone.now().date()
        transporters = transporters.exclude(Q(insurance_expiry__lte=current_date) | Q(license_expiry__lte=current_date))

        if delivery.pickup_latitude and delivery.pickup_longitude:
            eligible_transporters = []
            for transporter in transporters:
                if transporter.current_latitude and transporter.current_longitude:
                    distance = calculate_distance(
                        float(transporter.current_latitude),
                        float(transporter.current_longitude),
                        float(delivery.pickup_latitude),
                        float(delivery.pickup_longitude),
                    )
                    if distance <= transporter.service_radius:
                        eligible_transporters.append(transporter)
            transporters = eligible_transporters
        else:
            transporters = list(transporters)

        filtered_transporters = []
        for transporter in transporters:
            max_deliveries = self.max_active_deliveries.get(transporter.vehicle_type, 3)
            active_count = transporter.get_current_deliveries().count()
            if active_count < max_deliveries:
                filtered_transporters.append(transporter)

        return filtered_transporters

    def calculate_transporter_score(self, transporter: Transporter, delivery: Delivery) -> Dict[str, Any]:
        """
        Calculate a comprehensive score for each transporter based on multiple factors.

        Returns:
            Dictionary with score and breakdown of factors
        """
        score_breakdown = {}
        total_score = 0.0

        distance_score = 0
        distance_km = None

        if (
            transporter.current_latitude
            and transporter.current_longitude
            and delivery.pickup_latitude
            and delivery.pickup_longitude
        ):
            distance_km = calculate_distance(
                float(transporter.current_latitude),
                float(transporter.current_longitude),
                float(delivery.pickup_latitude),
                float(delivery.pickup_longitude),
            )

            max_distance = transporter.service_radius
            distance_score = max(0, 35 * (1 - (distance_km / max_distance)))

        score_breakdown["distance"] = distance_score
        score_breakdown["distance_km"] = distance_km
        total_score += distance_score

        rating_score = float(transporter.rating) * 5
        score_breakdown["rating"] = rating_score
        total_score += rating_score
        success_rate_score = transporter.success_rate * 0.15
        score_breakdown["success_rate"] = success_rate_score
        total_score += success_rate_score

        active_deliveries = transporter.get_current_deliveries().count()
        max_allowed = self.max_active_deliveries.get(transporter.vehicle_type, 3)
        workload_score = max(0, 10 * (1 - (active_deliveries / max_allowed)))
        score_breakdown["workload"] = workload_score
        score_breakdown["active_deliveries"] = active_deliveries
        total_score += workload_score

        vehicle_score = self.vehicle_capacity_multiplier.get(transporter.vehicle_type, 1.0) * 8
        score_breakdown["vehicle_suitability"] = vehicle_score
        total_score += vehicle_score
        priority_score = 0
        if delivery.priority in [DeliveryPriority.URGENT, DeliveryPriority.SAME_DAY]:
            if transporter.vehicle_type in [VehicleType.BIKE, VehicleType.CAR]:
                priority_score = 5
            elif transporter.vehicle_type == VehicleType.VAN:
                priority_score = 3
        else:
            priority_score = 2

        score_breakdown["priority_match"] = priority_score
        total_score += priority_score

        special_score = 0
        if delivery.fragile and transporter.vehicle_type in [VehicleType.CAR, VehicleType.VAN]:
            special_score += 1
        if delivery.package_value and delivery.package_value > 1000:
            if transporter.rating >= 4.0:
                special_score += 1

        score_breakdown["special_requirements"] = special_score
        total_score += special_score

        recent_performance_score = 0
        recent_deliveries = transporter.assigned_deliveries.filter(
            created_at__gte=timezone.now() - timedelta(days=7), status=TransportStatus.DELIVERED
        )

        if recent_deliveries.exists():
            on_time_count = recent_deliveries.filter(delivered_at__lte=F("requested_delivery_date")).count()
            on_time_rate = on_time_count / recent_deliveries.count()

            if on_time_rate >= 0.9:
                recent_performance_score = 3
            elif on_time_rate < 0.7:
                recent_performance_score = -2

        score_breakdown["recent_performance"] = recent_performance_score
        total_score += recent_performance_score

        return {"transporter": transporter, "total_score": total_score, "breakdown": score_breakdown}

    def estimate_delivery_time(self, transporter: Transporter, delivery: Delivery) -> Optional[timezone.datetime]:
        """
        Estimate delivery completion time based on distance and vehicle type.
        """
        if not delivery.distance_km:
            return None

        avg_speed = self.vehicle_speeds.get(transporter.vehicle_type, 30)

        travel_time_hours = float(delivery.distance_km) / avg_speed

        buffer_minutes = 30

        if delivery.fragile:
            buffer_minutes += 15
        if delivery.requires_signature:
            buffer_minutes += 10
        if delivery.package_weight > 10:
            buffer_minutes += 10

        pickup_travel_time = 0
        if (
            transporter.current_latitude
            and transporter.current_longitude
            and delivery.pickup_latitude
            and delivery.pickup_longitude
        ):
            pickup_distance = calculate_distance(
                float(transporter.current_latitude),
                float(transporter.current_longitude),
                float(delivery.pickup_latitude),
                float(delivery.pickup_longitude),
            )
            pickup_travel_time = pickup_distance / avg_speed

        total_time_hours = travel_time_hours + pickup_travel_time + (buffer_minutes / 60)

        return timezone.now() + timedelta(hours=total_time_hours)

    def assign_delivery(self, delivery_id: int, manual_transporter_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Auto-assign a delivery to the best available transporter or manually assign to specific transporter.

        Args:
            delivery_id: ID of the delivery to assign
            manual_transporter_id: Optional ID to manually assign to specific transporter

        Returns:
            Dictionary with assignment result and details
        """
        try:
            delivery = Delivery.objects.get(id=delivery_id, status=TransportStatus.AVAILABLE)
        except Delivery.DoesNotExist:
            return {"success": False, "error": "Delivery not found or not available for assignment"}

        if manual_transporter_id:
            try:
                transporter = Transporter.objects.get(
                    id=manual_transporter_id,
                    is_available=True,
                    is_verified=True,
                    status=TransporterStatus.ACTIVE,
                    vehicle_capacity__gte=delivery.package_weight,
                )

                current_deliveries = transporter.get_current_deliveries().count()
                max_allowed = self.max_active_deliveries.get(transporter.vehicle_type, 3)

                if current_deliveries >= max_allowed:
                    return {
                        "success": False,
                        "error": f"Transporter has reached maximum capacity ({max_allowed} deliveries)",
                    }

            except Transporter.DoesNotExist:
                return {"success": False, "error": "Transporter not found or not available"}
        else:
            available_transporters = self.get_available_transporters(delivery)

            if not available_transporters:
                return {"success": False, "error": "No available transporters found for this delivery"}
            transporter_scores = []
            for transporter in available_transporters:
                score_data = self.calculate_transporter_score(transporter, delivery)
                transporter_scores.append(score_data)

            transporter_scores.sort(key=lambda x: x["total_score"], reverse=True)
            transporter = transporter_scores[0]["transporter"]

        if not delivery.distance_km:
            distance = calculate_delivery_distance(delivery)
            if distance:
                delivery.distance_km = distance

        delivery.assign_to_transporter(transporter)

        estimated_time = self.estimate_delivery_time(transporter, delivery)
        if estimated_time:
            delivery.estimated_delivery_time = estimated_time
            delivery.save()

        response = {
            "success": True,
            "assigned_transporter": {
                "id": transporter.id,
                "name": transporter.user.get_full_name() or transporter.user.username,
                "business_name": transporter.business_name,
                "vehicle_type": transporter.vehicle_type,
                "vehicle_number": transporter.vehicle_number,
                "rating": float(transporter.rating),
                "phone": str(transporter.phone),
            },
            "delivery": {
                "id": delivery.id,
                "tracking_number": delivery.tracking_number,
                "status": delivery.status,
                "distance_km": float(delivery.distance_km) if delivery.distance_km else None,
                "estimated_delivery_time": (
                    delivery.estimated_delivery_time.isoformat() if delivery.estimated_delivery_time else None
                ),
            },
            "assignment_type": "manual" if manual_transporter_id else "automatic",
            "message": f"Delivery assigned to {transporter.user.get_full_name() or transporter.user.username}",
        }

        if not manual_transporter_id:
            response.update(
                {
                    "score_details": transporter_scores[0]["breakdown"],
                    "alternatives": [
                        {
                            "transporter_id": score["transporter"].id,
                            "transporter_name": score["transporter"].user.get_full_name()
                            or score["transporter"].user.username,
                            "score": round(score["total_score"], 2),
                            "breakdown": score["breakdown"],
                        }
                        for score in transporter_scores[1:5]
                    ],
                }
            )

        return response

    def bulk_assign_deliveries(
        self,
        priority_filter: Optional[str] = None,
        vehicle_type_filter: Optional[str] = None,
        max_assignments: int = 50,
        time_range_hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Bulk assign multiple available deliveries with enhanced filtering.

        Args:
            priority_filter: Filter by delivery priority
            vehicle_type_filter: Prefer specific vehicle type
            max_assignments: Maximum number of deliveries to assign
            time_range_hours: Only assign deliveries requested within X hours from now
        """
        start_time = time.time()

        deliveries = Delivery.objects.filter(status=TransportStatus.AVAILABLE)

        if priority_filter:
            deliveries = deliveries.filter(priority=priority_filter)

        if time_range_hours:
            cutoff_time = timezone.now() + timedelta(hours=time_range_hours)
            deliveries = deliveries.filter(requested_pickup_date__lte=cutoff_time)

        priority_order = {
            DeliveryPriority.SAME_DAY: 1,
            DeliveryPriority.URGENT: 2,
            DeliveryPriority.HIGH: 3,
            DeliveryPriority.NORMAL: 4,
            DeliveryPriority.LOW: 5,
        }

        deliveries = sorted(
            deliveries[:max_assignments], key=lambda d: (priority_order.get(d.priority, 6), d.requested_pickup_date)
        )

        results = {
            "total_deliveries": len(deliveries),
            "assigned": 0,
            "failed": 0,
            "assignments": [],
            "failures": [],
            "filters_applied": {
                "priority": priority_filter,
                "vehicle_type": vehicle_type_filter,
                "time_range_hours": time_range_hours,
                "max_assignments": max_assignments,
            },
        }

        for delivery in deliveries:
            assignment_result = self.assign_delivery(delivery.id)

            if assignment_result["success"]:
                results["assigned"] += 1

                assigned_transporter = assignment_result["assigned_transporter"]
                if vehicle_type_filter and assigned_transporter.get("vehicle_type") != vehicle_type_filter:
                    alternatives = assignment_result.get("alternatives", [])
                    for alt in alternatives:
                        alt_transporter = Transporter.objects.get(id=alt["transporter_id"])
                        if alt_transporter.vehicle_type == vehicle_type_filter:
                            if alt["score"] >= assignment_result["score_details"].get("total_score", 0) * 0.8:
                                delivery.status = TransportStatus.AVAILABLE
                                delivery.transporter = None
                                delivery.assigned_at = None
                                delivery.save()

                                new_assignment = self.assign_delivery(delivery.id, alt_transporter.id)
                                if new_assignment["success"]:
                                    assignment_result = new_assignment
                                break

                results["assignments"].append(
                    {
                        "delivery_id": delivery.id,
                        "delivery_uuid": str(delivery.delivery_id),
                        "tracking_number": delivery.tracking_number,
                        "transporter": assignment_result["assigned_transporter"],
                        "distance_km": assignment_result["delivery"].get("distance_km"),
                        "estimated_delivery": assignment_result["delivery"].get("estimated_delivery_time"),
                        "priority": delivery.priority,
                        "assignment_type": assignment_result.get("assignment_type", "automatic"),
                    }
                )
            else:
                results["failed"] += 1
                results["failures"].append(
                    {
                        "delivery_id": delivery.id,
                        "delivery_uuid": str(delivery.delivery_id),
                        "tracking_number": delivery.tracking_number,
                        "priority": delivery.priority,
                        "error": assignment_result["error"],
                    }
                )

        results["execution_time_seconds"] = round(time.time() - start_time, 2)
        results["success_rate"] = round(
            (results["assigned"] / results["total_deliveries"] * 100) if results["total_deliveries"] > 0 else 0, 2
        )

        return results

    def get_assignment_recommendations(self, delivery_id: int, limit: int = 10) -> Dict[str, Any]:
        """
        Get ranked recommendations for transporter assignment without actually assigning.

        Args:
            delivery_id: ID of the delivery
            limit: Maximum number of recommendations to return

        Returns:
            Dictionary with ranked transporter recommendations
        """
        try:
            delivery = Delivery.objects.get(id=delivery_id, status=TransportStatus.AVAILABLE)
        except Delivery.DoesNotExist:
            return {"success": False, "error": "Delivery not found or not available for assignment"}

        available_transporters = self.get_available_transporters(delivery)

        if not available_transporters:
            return {"success": False, "error": "No available transporters found"}

        recommendations = []
        for transporter in available_transporters:
            score_data = self.calculate_transporter_score(transporter, delivery)

            estimated_time = self.estimate_delivery_time(transporter, delivery)

            recommendations.append(
                {
                    "transporter": {
                        "id": transporter.id,
                        "name": transporter.user.get_full_name() or transporter.user.username,
                        "business_name": transporter.business_name,
                        "vehicle_type": transporter.vehicle_type,
                        "vehicle_capacity": float(transporter.vehicle_capacity),
                        "rating": float(transporter.rating),
                        "success_rate": transporter.success_rate,
                        "active_deliveries": transporter.get_current_deliveries().count(),
                        "phone": str(transporter.phone),
                    },
                    "score": round(score_data["total_score"], 2),
                    "score_breakdown": score_data["breakdown"],
                    "estimated_delivery_time": estimated_time.isoformat() if estimated_time else None,
                    "suitability_reasons": self._get_suitability_reasons(transporter, delivery, score_data["breakdown"]),
                }
            )

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        recommendations = recommendations[:limit]

        return {
            "success": True,
            "delivery": {
                "id": delivery.id,
                "tracking_number": delivery.tracking_number,
                "priority": delivery.priority,
                "package_weight": float(delivery.package_weight),
                "fragile": delivery.fragile,
                "requires_signature": delivery.requires_signature,
            },
            "recommendations": recommendations,
            "total_available": len(available_transporters),
        }

    def _get_suitability_reasons(self, transporter: Transporter, delivery: Delivery, score_breakdown: Dict) -> List[str]:
        """
        Generate human-readable reasons why a transporter is suitable for a delivery.
        """
        reasons = []

        if score_breakdown.get("distance", 0) > 25:
            reasons.append("Very close to pickup location")
        elif score_breakdown.get("distance", 0) > 15:
            reasons.append("Close to pickup location")

        if transporter.rating >= 4.5:
            reasons.append("Excellent customer rating")
        elif transporter.rating >= 4.0:
            reasons.append("High customer rating")

        if transporter.success_rate >= 95:
            reasons.append("Outstanding delivery success rate")
        elif transporter.success_rate >= 90:
            reasons.append("High delivery success rate")

        if score_breakdown.get("workload", 0) >= 7:
            reasons.append("Low current workload")

        if delivery.fragile and transporter.vehicle_type in [VehicleType.CAR, VehicleType.VAN]:
            reasons.append("Suitable vehicle for fragile items")

        if delivery.priority in [DeliveryPriority.URGENT, DeliveryPriority.SAME_DAY] and transporter.vehicle_type in [
            VehicleType.BIKE,
            VehicleType.CAR,
        ]:
            reasons.append("Fast vehicle for urgent delivery")

        if score_breakdown.get("recent_performance", 0) > 0:
            reasons.append("Excellent recent performance")

        return reasons
