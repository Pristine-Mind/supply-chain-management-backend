import math
from datetime import datetime, timedelta

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from transport.services.auto_assignment import DeliveryAutoAssignmentService
from transport.services.reporting import DeliveryReportingService
from transport.utils import calculate_delivery_distance, calculate_distance

from .models import (
    Delivery,
    DeliveryRating,
    DeliveryTracking,
    Transporter,
    TransportStatus,
)
from .serializers import (
    AssignmentRequestSerializer,
    DeliveryCreateSerializer,
    DeliveryDashboardSerializer,
    DeliveryListSerializer,
    DeliveryRatingSerializer,
    DeliverySerializer,
    DeliveryStatusUpdateSerializer,
    DeliveryTrackingSerializer,
    DistanceCalculationSerializer,
    LocationUpdateSerializer,
    NearbyDeliverySerializer,
    ReportFilterSerializer,
    TransporterCreateSerializer,
    TransporterSerializer,
    TransporterStatsSerializer,
)


class IsTransporterOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow transporters to edit their own profile.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class TransporterProfileView(APIView):
    """
    Get or create transporter profile for authenticated user
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            transporter = request.user.transporter_profile
            serializer = TransporterSerializer(transporter)
            return Response(serializer.data)
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        try:
            transporter = request.user.transporter_profile
            return Response({"detail": "Transporter profile already exists"}, status=status.HTTP_400_BAD_REQUEST)
        except Transporter.DoesNotExist:
            serializer = TransporterCreateSerializer(data=request.data, context={"request": request})
            if serializer.is_valid():
                transporter = serializer.save()
                return Response(TransporterSerializer(transporter).data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        try:
            transporter = request.user.transporter_profile
            serializer = TransporterSerializer(transporter, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_404_NOT_FOUND)


class TransporterListView(generics.ListAPIView):
    """
    List all transporters (admin only)
    """

    queryset = Transporter.objects.all()
    serializer_class = TransporterSerializer
    permission_classes = [permissions.IsAdminUser]
    filterset_fields = ["vehicle_type", "is_available", "is_verified"]
    ordering_fields = ["rating", "total_deliveries", "created_at"]
    search_fields = ["user__first_name", "user__last_name", "license_number"]


class AvailableDeliveriesView(generics.ListAPIView):
    """
    List available deliveries for transporters
    """

    serializer_class = DeliveryListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            transporter = self.request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Delivery.objects.none()

        queryset = Delivery.objects.filter(
            status=TransportStatus.AVAILABLE, package_weight__lte=transporter.vehicle_capacity
        ).select_related("marketplace_sale", "marketplace_sale__product")

        priority = self.request.query_params.get("priority")
        weight_max = self.request.query_params.get("weight_max")
        distance_max = self.request.query_params.get("distance_max")
        pickup_date = self.request.query_params.get("pickup_date")

        if priority:
            queryset = queryset.filter(priority=priority)

        if weight_max:
            try:
                queryset = queryset.filter(package_weight__lte=float(weight_max))
            except ValueError:
                pass

        if distance_max:
            try:
                queryset = queryset.filter(distance_km__lte=float(distance_max))
            except ValueError:
                pass

        if pickup_date:
            try:
                date_obj = datetime.strptime(pickup_date, "%Y-%m-%d").date()
                queryset = queryset.filter(requested_pickup_date__date=date_obj)
            except ValueError:
                pass

        return queryset.order_by("priority", "requested_pickup_date")


class MyDeliveriesView(generics.ListAPIView):
    """
    List deliveries assigned to authenticated transporter
    """

    serializer_class = DeliveryListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            transporter = self.request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Delivery.objects.none()

        queryset = Delivery.objects.filter(transporter=transporter).select_related(
            "marketplace_sale", "marketplace_sale__product"
        )

        status_filter = self.request.query_params.get("status")
        if status_filter == "active":
            queryset = queryset.filter(
                status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
            )
        elif status_filter == "completed":
            queryset = queryset.filter(status=TransportStatus.DELIVERED)
        elif status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-updated_at")


class DeliveryDetailView(generics.RetrieveAPIView):
    """
    Get detailed information about a specific delivery
    """

    serializer_class = DeliverySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "delivery_id"

    def get_queryset(self):
        user = self.request.user

        if user.is_staff:
            return Delivery.objects.all()

        try:
            transporter = user.transporter_profile
            return Delivery.objects.filter(Q(status=TransportStatus.AVAILABLE) | Q(transporter=transporter))
        except Transporter.DoesNotExist:
            return Delivery.objects.filter(marketplace_sale__buyer=user)


class AcceptDeliveryView(APIView):
    """
    Accept an available delivery
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, delivery_id):
        try:
            transporter = request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_400_BAD_REQUEST)

        delivery = get_object_or_404(Delivery, delivery_id=delivery_id)

        if delivery.status != TransportStatus.AVAILABLE:
            return Response({"detail": "This delivery is no longer available"}, status=status.HTTP_400_BAD_REQUEST)

        if not transporter.is_available:
            return Response({"detail": "You are currently marked as unavailable"}, status=status.HTTP_400_BAD_REQUEST)

        if delivery.package_weight > transporter.vehicle_capacity:
            return Response({"detail": "Package weight exceeds your vehicle capacity"}, status=status.HTTP_400_BAD_REQUEST)

        delivery.assign_to_transporter(transporter)

        DeliveryTracking.objects.create(
            delivery=delivery,
            status=TransportStatus.ASSIGNED,
            notes=f"Delivery assigned to {transporter.user.get_full_name()}",
        )

        serializer = DeliverySerializer(delivery)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateDeliveryStatusView(APIView):
    """
    Update delivery status with tracking information
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, delivery_id):
        try:
            transporter = request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_400_BAD_REQUEST)

        delivery = get_object_or_404(Delivery, delivery_id=delivery_id)

        if delivery.transporter != transporter:
            return Response(
                {"detail": "You do not have permission to update this delivery"}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = DeliveryStatusUpdateSerializer(data=request.data, context={"delivery": delivery})

        if serializer.is_valid():
            new_status = serializer.validated_data["status"]
            notes = serializer.validated_data.get("notes", "")
            latitude = serializer.validated_data.get("latitude")
            longitude = serializer.validated_data.get("longitude")

            if new_status == TransportStatus.PICKED_UP:
                delivery.mark_picked_up()
            elif new_status == TransportStatus.IN_TRANSIT:
                delivery.mark_in_transit()
            elif new_status == TransportStatus.DELIVERED:
                delivery.mark_delivered()

            tracking_data = {
                "delivery": delivery,
                "status": new_status,
                "notes": notes,
            }

            if latitude and longitude:
                tracking_data["latitude"] = latitude
                tracking_data["longitude"] = longitude

            DeliveryTracking.objects.create(**tracking_data)

            return Response(DeliverySerializer(delivery).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeliveryTrackingView(generics.ListAPIView):
    """
    Get tracking updates for a specific delivery
    """

    serializer_class = DeliveryTrackingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        delivery_id = self.kwargs["delivery_id"]
        delivery = get_object_or_404(Delivery, delivery_id=delivery_id)

        user = self.request.user
        can_view = (
            user.is_staff
            or (hasattr(user, "transporter_profile") and delivery.transporter == user.transporter_profile)
            or delivery.marketplace_sale.buyer == user
        )

        if not can_view:
            return DeliveryTracking.objects.none()

        return delivery.tracking_updates.all().order_by("-timestamp")


class UpdateLocationView(APIView):
    """
    Update transporter's current location
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            transporter = request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = LocationUpdateSerializer(data=request.data)
        if serializer.is_valid():
            transporter.current_latitude = serializer.validated_data["latitude"]
            transporter.current_longitude = serializer.validated_data["longitude"]
            transporter.save()

            return Response({"detail": "Location updated successfully"})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ToggleAvailabilityView(APIView):
    """
    Toggle transporter availability status
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            transporter = request.user.transporter_profile
            transporter.is_available = not transporter.is_available
            transporter.save()

            return Response(
                {
                    "is_available": transporter.is_available,
                    "detail": f'You are now {"available" if transporter.is_available else "unavailable"}',
                }
            )
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_400_BAD_REQUEST)


class TransporterStatsView(APIView):
    """
    Get transporter statistics and earnings
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            transporter = request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Response({"detail": "Transporter profile not found"}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        completed_deliveries = Delivery.objects.filter(transporter=transporter, status=TransportStatus.DELIVERED)

        monthly_deliveries = completed_deliveries.filter(delivered_at__gte=start_of_month)

        active_deliveries = Delivery.objects.filter(
            transporter=transporter,
            status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT],
        ).count()

        total_earnings = completed_deliveries.aggregate(total=Sum("delivery_fee"))["total"] or 0

        monthly_earnings = monthly_deliveries.aggregate(total=Sum("delivery_fee"))["total"] or 0

        stats = {
            "total_deliveries": transporter.total_deliveries,
            "successful_deliveries": transporter.successful_deliveries,
            "success_rate": transporter.success_rate,
            "rating": transporter.rating,
            "total_earnings": total_earnings,
            "deliveries_this_month": monthly_deliveries.count(),
            "earnings_this_month": monthly_earnings,
            "active_deliveries": active_deliveries,
        }

        serializer = TransporterStatsSerializer(stats)
        return Response(serializer.data)


class NearbyDeliveriesView(generics.ListAPIView):
    """
    Get deliveries near transporter's current location
    """

    serializer_class = NearbyDeliverySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            transporter = self.request.user.transporter_profile
        except Transporter.DoesNotExist:
            return Delivery.objects.none()

        if not transporter.current_latitude or not transporter.current_longitude:
            return Delivery.objects.none()

        radius = float(self.request.query_params.get("radius", 10))

        queryset = Delivery.objects.filter(
            status=TransportStatus.AVAILABLE,
            package_weight__lte=transporter.vehicle_capacity,
            pickup_latitude__isnull=False,
            pickup_longitude__isnull=False,
        )

        nearby_deliveries = []
        for delivery in queryset:
            distance = self.calculate_distance(
                float(transporter.current_latitude),
                float(transporter.current_longitude),
                float(delivery.pickup_latitude),
                float(delivery.pickup_longitude),
            )

            if distance <= radius:
                delivery.distance = distance
                nearby_deliveries.append(delivery)

        nearby_deliveries.sort(key=lambda x: x.distance)
        return nearby_deliveries

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points using Haversine formula"""
        R = 6371

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(
            dlon / 2
        ) * math.sin(dlon / 2)

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        return distance


class DeliveryRatingListCreateView(generics.ListCreateAPIView):
    """
    List and create delivery ratings
    """

    serializer_class = DeliveryRatingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        delivery_id = self.kwargs.get("delivery_id")
        if delivery_id:
            return DeliveryRating.objects.filter(delivery__delivery_id=delivery_id)
        return DeliveryRating.objects.all()

    def perform_create(self, serializer):
        delivery = get_object_or_404(Delivery, delivery_id=self.kwargs["delivery_id"])

        user = self.request.user
        can_rate = delivery.marketplace_sale.buyer == user or delivery.marketplace_sale.seller == user

        if not can_rate:
            raise PermissionError("You can only rate deliveries you're involved in")

        serializer.save(rated_by=user, delivery=delivery, transporter=delivery.transporter)


class DeliveryListCreateView(generics.ListCreateAPIView):
    """
    List all deliveries and create new ones (Admin only)
    """

    queryset = Delivery.objects.all().select_related("marketplace_sale", "transporter__user")
    permission_classes = [permissions.IsAdminUser]
    filterset_fields = ["status", "priority", "transporter"]
    ordering_fields = ["created_at", "requested_pickup_date", "delivered_at"]
    search_fields = ["delivery_id", "pickup_address", "delivery_address"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DeliveryCreateSerializer
        return DeliveryListSerializer


class DeliveryUpdateView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete delivery (Admin only)
    """

    queryset = Delivery.objects.all()
    serializer_class = DeliverySerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = "delivery_id"


class DashboardStatsView(APIView):
    """
    Get dashboard statistics for admin panel
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        total_deliveries = Delivery.objects.count()
        pending_deliveries = Delivery.objects.filter(status=TransportStatus.AVAILABLE).count()
        assigned_deliveries = Delivery.objects.filter(status=TransportStatus.ASSIGNED).count()
        in_transit_deliveries = Delivery.objects.filter(status=TransportStatus.IN_TRANSIT).count()
        completed_deliveries = Delivery.objects.filter(status=TransportStatus.DELIVERED).count()

        total_transporters = Transporter.objects.count()
        active_transporters = Transporter.objects.filter(is_available=True).count()

        completed_with_times = Delivery.objects.filter(
            status=TransportStatus.DELIVERED, assigned_at__isnull=False, delivered_at__isnull=False
        )

        total_time = 0
        count = 0
        for delivery in completed_with_times:
            if delivery.assigned_at and delivery.delivered_at:
                time_diff = delivery.delivered_at - delivery.assigned_at
                total_time += time_diff.total_seconds() / 3600
                count += 1

        average_delivery_time = total_time / count if count > 0 else 0

        total_revenue = (
            Delivery.objects.filter(status=TransportStatus.DELIVERED).aggregate(total=Sum("delivery_fee"))["total"] or 0
        )

        stats = {
            "total_deliveries": total_deliveries,
            "pending_deliveries": pending_deliveries,
            "assigned_deliveries": assigned_deliveries,
            "in_transit_deliveries": in_transit_deliveries,
            "completed_deliveries": completed_deliveries,
            "total_transporters": total_transporters,
            "active_transporters": active_transporters,
            "average_delivery_time": round(average_delivery_time, 2),
            "total_revenue": total_revenue,
        }

        serializer = DeliveryDashboardSerializer(stats)
        return Response(serializer.data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def delivery_history(request):
    """
    Get delivery history for authenticated transporter with date filtering
    """
    try:
        transporter = request.user.transporter_profile
    except Transporter.DoesNotExist:
        return Response({"detail": "Transporter profile not found"}, status=status.HTTP_400_BAD_REQUEST)

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    deliveries = Delivery.objects.filter(transporter=transporter, status=TransportStatus.DELIVERED).select_related(
        "marketplace_sale", "marketplace_sale__product"
    )

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
            deliveries = deliveries.filter(delivered_at__date__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
            deliveries = deliveries.filter(delivered_at__date__lte=date_to_obj)
        except ValueError:
            pass

    deliveries = deliveries.order_by("-delivered_at")

    total_earnings = deliveries.aggregate(total=Sum("delivery_fee"))["total"] or 0
    total_deliveries_count = deliveries.count()

    paginator = PageNumberPagination()
    paginator.page_size = 20
    page = paginator.paginate_queryset(deliveries, request)

    serializer = DeliveryListSerializer(page, many=True)

    response_data = {
        "results": serializer.data,
        "total_earnings": total_earnings,
        "total_deliveries": total_deliveries_count,
        "pagination": {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
        },
    }

    return Response(response_data)


class AutoAssignmentAPIView(APIView):
    """
    API for auto-assignment functionality.

    POST /api/auto-assign/
    - Assign specific delivery: {"delivery_id": 123}
    - Bulk assign: {"priority_filter": "high", "max_assignments": 20}
    """

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def __init__(self):
        super().__init__()
        self.assignment_service = DeliveryAutoAssignmentService()

    def post(self, request):
        serializer = AssignmentRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            if "delivery_id" in data:
                result = self.assignment_service.assign_delivery(data["delivery_id"])

                if result["success"]:
                    response_data = {
                        "success": result["success"],
                        "message": result["message"],
                        "delivery_id": result["delivery"].id,
                        "delivery_uuid": str(result["delivery"].delivery_id),
                        "assigned_transporter": {
                            "id": result["assigned_transporter"].id,
                            "name": result["assigned_transporter"].user.get_full_name(),
                            "vehicle_type": result["assigned_transporter"].vehicle_type,
                            "rating": float(result["assigned_transporter"].rating),
                        },
                        "score_details": result["score_details"],
                        "alternatives": result["alternatives"],
                        "distance_km": result["distance_km"],
                        "estimated_delivery_time": result["estimated_delivery_time"],
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                else:
                    return Response(result, status=status.HTTP_400_BAD_REQUEST)
            else:
                result = self.assignment_service.bulk_assign_deliveries(
                    priority_filter=data.get("priority_filter"), max_assignments=data.get("max_assignments", 50)
                )
                return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"success": False, "error": f"Assignment failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeliveryReportingAPIView(APIView):
    """
    API for delivery reporting and analytics.

    GET /api/reports/?start_date=2024-01-01&end_date=2024-01-31&report_type=comprehensive
    """

    permission_classes = [permissions.IsAuthenticated]

    def __init__(self):
        super().__init__()
        self.reporting_service = DeliveryReportingService()

    def get(self, request):
        serializer = ReportFilterSerializer(data=request.GET)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        filters = serializer.validated_data
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        report_type = filters.get("report_type", "comprehensive")

        report_filters = {}
        if filters.get("transporter_id"):
            report_filters["transporter_id"] = filters["transporter_id"]
        if filters.get("status"):
            report_filters["status"] = filters["status"]
        if filters.get("priority"):
            report_filters["priority"] = filters["priority"]

        try:
            if report_type == "overview":
                data = self.reporting_service.get_delivery_overview(start_date, end_date, report_filters)
            elif report_type == "performance":
                data = self.reporting_service.get_transporter_performance(start_date, end_date)
            elif report_type == "geographic":
                data = self.reporting_service.get_geographic_analysis(start_date, end_date)
            elif report_type == "time":
                data = self.reporting_service.get_time_based_analysis(start_date, end_date)
            else:
                data = self.reporting_service.generate_comprehensive_report(start_date, end_date, report_filters)

            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Report generation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DistanceCalculationAPIView(APIView):
    """
    API for distance calculations using Haversine formula.

    POST /api/distance/
    {
        "pickup_latitude": 40.7128,
        "pickup_longitude": -74.0060,
        "delivery_latitude": 40.7589,
        "delivery_longitude": -73.9851
    }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DistanceCalculationSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            distance = calculate_distance(
                float(data["pickup_latitude"]),
                float(data["pickup_longitude"]),
                float(data["delivery_latitude"]),
                float(data["delivery_longitude"]),
            )

            return Response(
                {
                    "distance_km": round(distance, 2),
                    "distance_miles": round(distance * 0.621371, 2),
                    "coordinates": {
                        "pickup": {"latitude": data["pickup_latitude"], "longitude": data["pickup_longitude"]},
                        "delivery": {"latitude": data["delivery_latitude"], "longitude": data["delivery_longitude"]},
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Distance calculation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeliveryDistanceUpdateAPIView(APIView):
    """
    API to update delivery distance for existing deliveries.

    POST /api/deliveries/{delivery_id}/update-distance/
    """

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, delivery_id):
        try:
            delivery = Delivery.objects.get(delivery_id=delivery_id)
        except Delivery.DoesNotExist:
            return Response({"error": "Delivery not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            distance = calculate_delivery_distance(delivery)

            if distance is None:
                return Response(
                    {"error": "Cannot calculate distance - missing coordinates"}, status=status.HTTP_400_BAD_REQUEST
                )

            delivery.distance_km = distance
            delivery.save()

            return Response(
                {
                    "delivery_id": str(delivery.delivery_id),
                    "distance_km": round(distance, 2),
                    "message": "Distance updated successfully",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response({"error": f"Distance update failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OptimalTransporterAPIView(APIView):
    """
    API to find optimal transporters for a delivery without assigning.

    GET /api/deliveries/{delivery_id}/optimal-transporters/
    """

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def __init__(self):
        super().__init__()
        self.assignment_service = DeliveryAutoAssignmentService()

    def get(self, request, delivery_id):
        try:
            delivery = Delivery.objects.get(delivery_id=delivery_id)
        except Delivery.DoesNotExist:
            return Response({"error": "Delivery not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            available_transporters = self.assignment_service.get_available_transporters(delivery)

            if not available_transporters:
                return Response(
                    {
                        "delivery_id": str(delivery.delivery_id),
                        "available_transporters": [],
                        "message": "No available transporters found",
                    },
                    status=status.HTTP_200_OK,
                )

            transporter_scores = []
            for transporter in available_transporters:
                score_data = self.assignment_service.calculate_transporter_score(transporter, delivery)
                transporter_scores.append(
                    {
                        "transporter": {
                            "id": transporter.id,
                            "name": transporter.user.get_full_name(),
                            "vehicle_type": transporter.vehicle_type,
                            "vehicle_capacity": float(transporter.vehicle_capacity),
                            "rating": float(transporter.rating),
                            "success_rate": transporter.success_rate,
                            "current_location": {
                                "latitude": float(transporter.current_latitude) if transporter.current_latitude else None,
                                "longitude": float(transporter.current_longitude) if transporter.current_longitude else None,
                            },
                        },
                        "score": score_data["total_score"],
                        "breakdown": score_data["breakdown"],
                    }
                )

            transporter_scores.sort(key=lambda x: x["score"], reverse=True)

            return Response(
                {
                    "delivery_id": str(delivery.delivery_id),
                    "delivery_details": {
                        "pickup_address": delivery.pickup_address,
                        "delivery_address": delivery.delivery_address,
                        "package_weight": float(delivery.package_weight),
                        "priority": delivery.priority,
                    },
                    "available_transporters": transporter_scores,
                    "total_found": len(transporter_scores),
                    "best_match": transporter_scores[0] if transporter_scores else None,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Optimal transporter search failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeliveryAnalyticsAPIView(APIView):
    """
    API for specific delivery analytics and insights.

    GET /api/analytics/delivery-trends/?period=30
    GET /api/analytics/transporter-rankings/?limit=10
    GET /api/analytics/efficiency-metrics/
    """

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def __init__(self):
        super().__init__()
        self.reporting_service = DeliveryReportingService()

    def get(self, request):
        endpoint = request.path.split("/")[-2]

        try:
            if endpoint == "delivery-trends":
                return self._get_delivery_trends(request)
            elif endpoint == "transporter-rankings":
                return self._get_transporter_rankings(request)
            elif endpoint == "efficiency-metrics":
                return self._get_efficiency_metrics(request)
            else:
                return Response({"error": "Invalid analytics endpoint"}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": f"Analytics request failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_delivery_trends(self, request):
        """Get delivery trends over specified period"""
        period_days = int(request.GET.get("period", 30))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=period_days)

        time_analysis = self.reporting_service.get_time_based_analysis(start_date, end_date)
        overview = self.reporting_service.get_delivery_overview(start_date, end_date)

        return Response(
            {
                "period_days": period_days,
                "trends": time_analysis,
                "summary": overview["overview"],
                "generated_at": timezone.now().isoformat(),
            }
        )

    def _get_transporter_rankings(self, request):
        """Get top performing transporters"""
        limit = int(request.GET.get("limit", 10))
        period_days = int(request.GET.get("period", 30))

        end_date = timezone.now()
        start_date = end_date - timedelta(days=period_days)

        performance_data = self.reporting_service.get_transporter_performance(start_date, end_date)

        return Response(
            {
                "period_days": period_days,
                "top_transporters": performance_data[:limit],
                "total_transporters": len(performance_data),
                "ranking_criteria": ["Success Rate", "Total Deliveries", "Average Rating", "Revenue Generated"],
                "generated_at": timezone.now().isoformat(),
            }
        )

    def _get_efficiency_metrics(self, request):
        """Get system efficiency metrics"""
        period_days = int(request.GET.get("period", 30))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=period_days)

        overview = self.reporting_service.get_delivery_overview(start_date, end_date)
        geographic = self.reporting_service.get_geographic_analysis(start_date, end_date)
        performance = self.reporting_service.get_transporter_performance(start_date, end_date)

        total_deliveries = overview["overview"]["total_deliveries"]
        success_rate = overview["overview"]["success_rate"]
        avg_delivery_time = overview["overview"]["avg_delivery_time_hours"]

        total_transporters = len(performance)
        active_transporters = len([t for t in performance if t["period_metrics"]["total_assigned"] > 0])
        utilization_rate = (active_transporters / total_transporters * 100) if total_transporters > 0 else 0

        avg_distance = geographic["distance_statistics"]["avg_distance"]
        total_distance = geographic["distance_statistics"]["total_distance"]

        efficiency_score = 0
        if success_rate and avg_delivery_time and utilization_rate:
            efficiency_score = min(
                100, (success_rate * 0.4) + (utilization_rate * 0.3) + (max(0, 100 - (avg_delivery_time * 10)) * 0.3)
            )

        return Response(
            {
                "period_days": period_days,
                "efficiency_metrics": {
                    "overall_efficiency_score": round(efficiency_score, 2),
                    "delivery_success_rate": success_rate,
                    "average_delivery_time_hours": avg_delivery_time,
                    "transporter_utilization_rate": round(utilization_rate, 2),
                    "average_distance_per_delivery": avg_distance,
                    "total_distance_covered": total_distance,
                    "deliveries_per_day": round(total_deliveries / period_days, 2) if period_days > 0 else 0,
                },
                "recommendations": self._generate_efficiency_recommendations(
                    success_rate, avg_delivery_time, utilization_rate, avg_distance
                ),
                "generated_at": timezone.now().isoformat(),
            }
        )

    def _generate_efficiency_recommendations(self, success_rate, avg_time, utilization, avg_distance):
        """Generate efficiency improvement recommendations"""
        recommendations = []

        if success_rate < 90:
            recommendations.append(
                {
                    "area": "Success Rate",
                    "issue": f"Success rate is {success_rate}%, below optimal 90%+",
                    "suggestion": "Review failed deliveries and improve transporter training",
                }
            )

        if avg_time and avg_time > 4:
            recommendations.append(
                {
                    "area": "Delivery Time",
                    "issue": f"Average delivery time is {avg_time:.1f} hours",
                    "suggestion": "Optimize routing and improve auto-assignment algorithm",
                }
            )

        if utilization < 70:
            recommendations.append(
                {
                    "area": "Transporter Utilization",
                    "issue": f"Only {utilization:.1f}% of transporters are active",
                    "suggestion": "Improve transporter engagement and workload distribution",
                }
            )

        if avg_distance and avg_distance > 20:
            recommendations.append(
                {
                    "area": "Distance Optimization",
                    "issue": f"Average delivery distance is {avg_distance:.1f}km",
                    "suggestion": "Consider regional hubs or improve pickup location optimization",
                }
            )

        if not recommendations:
            recommendations.append(
                {
                    "area": "Overall",
                    "issue": "System performing well",
                    "suggestion": "Continue monitoring and consider expanding capacity",
                }
            )

        return recommendations


class BulkDeliveryOperationsAPIView(APIView):
    """
    API for bulk operations on deliveries.

    POST /api/deliveries/bulk-operations/
    {
        "operation": "update_distances",  // or "auto_assign", "cancel", "reassign"
        "delivery_ids": [1, 2, 3],
        "filters": {"status": "available", "priority": "high"},  // alternative to delivery_ids
        "parameters": {...}  // operation-specific parameters
    }
    """

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def __init__(self):
        super().__init__()
        self.assignment_service = DeliveryAutoAssignmentService()

    def post(self, request):
        operation = request.data.get("operation")
        delivery_ids = request.data.get("delivery_ids", [])
        filters = request.data.get("filters", {})
        parameters = request.data.get("parameters", {})

        if not operation:
            return Response({"error": "Operation type is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if delivery_ids:
                deliveries = Delivery.objects.filter(id__in=delivery_ids)
            else:
                deliveries = Delivery.objects.all()
                if filters.get("status"):
                    deliveries = deliveries.filter(status=filters["status"])
                if filters.get("priority"):
                    deliveries = deliveries.filter(priority=filters["priority"])
                if filters.get("transporter_id"):
                    deliveries = deliveries.filter(transporter_id=filters["transporter_id"])

            if operation == "update_distances":
                return self._bulk_update_distances(deliveries)
            elif operation == "auto_assign":
                return self._bulk_auto_assign(deliveries, parameters)
            elif operation == "cancel":
                return self._bulk_cancel(deliveries, parameters)
            elif operation == "reassign":
                return self._bulk_reassign(deliveries, parameters)
            else:
                return Response({"error": f"Unknown operation: {operation}"}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": f"Bulk operation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _bulk_update_distances(self, deliveries):
        """Update distances for multiple deliveries"""
        updated = 0
        failed = 0
        results = []

        for delivery in deliveries:
            try:
                distance = calculate_delivery_distance(delivery)
                if distance is not None:
                    delivery.distance_km = distance
                    delivery.save()
                    updated += 1
                    results.append(
                        {"delivery_id": str(delivery.delivery_id), "distance_km": round(distance, 2), "status": "updated"}
                    )
                else:
                    failed += 1
                    results.append(
                        {"delivery_id": str(delivery.delivery_id), "status": "failed", "error": "Missing coordinates"}
                    )
            except Exception as e:
                failed += 1
                results.append({"delivery_id": str(delivery.delivery_id), "status": "failed", "error": str(e)})

        return Response(
            {
                "operation": "update_distances",
                "total_processed": deliveries.count(),
                "updated": updated,
                "failed": failed,
                "results": results,
            }
        )

    def _bulk_auto_assign(self, deliveries, parameters):
        """Auto-assign multiple deliveries"""
        max_assignments = parameters.get("max_assignments", 50)
        available_deliveries = deliveries.filter(status=TransportStatus.AVAILABLE)[:max_assignments]

        results = {
            "operation": "auto_assign",
            "total_eligible": available_deliveries.count(),
            "assigned": 0,
            "failed": 0,
            "assignments": [],
            "failures": [],
        }

        for delivery in available_deliveries:
            assignment_result = self.assignment_service.assign_delivery(delivery.id)

            if assignment_result["success"]:
                results["assigned"] += 1
                results["assignments"].append(
                    {
                        "delivery_id": str(delivery.delivery_id),
                        "transporter_name": assignment_result["assigned_transporter"].user.get_full_name(),
                        "score": assignment_result["score_details"],
                    }
                )
            else:
                results["failed"] += 1
                results["failures"].append({"delivery_id": str(delivery.delivery_id), "error": assignment_result["error"]})

        return Response(results)

    def _bulk_cancel(self, deliveries, parameters):
        """Cancel multiple deliveries"""
        reason = parameters.get("reason", "Bulk cancellation")
        cancelled = 0
        failed = 0
        results = []

        for delivery in deliveries:
            try:
                if delivery.status in [TransportStatus.AVAILABLE, TransportStatus.ASSIGNED]:
                    delivery.status = TransportStatus.CANCELLED
                    delivery.save()

                    DeliveryTracking.objects.create(delivery=delivery, status=TransportStatus.CANCELLED, notes=reason)

                    cancelled += 1
                    results.append({"delivery_id": str(delivery.delivery_id), "status": "cancelled"})
                else:
                    failed += 1
                    results.append(
                        {
                            "delivery_id": str(delivery.delivery_id),
                            "status": "failed",
                            "error": f"Cannot cancel delivery with status: {delivery.status}",
                        }
                    )
            except Exception as e:
                failed += 1
                results.append({"delivery_id": str(delivery.delivery_id), "status": "failed", "error": str(e)})

        return Response(
            {
                "operation": "cancel",
                "total_processed": deliveries.count(),
                "cancelled": cancelled,
                "failed": failed,
                "results": results,
            }
        )

    def _bulk_reassign(self, deliveries, parameters):
        """Reassign multiple deliveries"""
        new_transporter_id = parameters.get("transporter_id")

        if not new_transporter_id:
            return Response(
                {"error": "transporter_id parameter is required for reassignment"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            new_transporter = Transporter.objects.get(id=new_transporter_id)
        except Transporter.DoesNotExist:
            return Response({"error": "Transporter not found"}, status=status.HTTP_404_NOT_FOUND)

        reassigned = 0
        failed = 0
        results = []

        for delivery in deliveries:
            try:
                if (
                    delivery.status == TransportStatus.ASSIGNED
                    and delivery.package_weight <= new_transporter.vehicle_capacity
                ):
                    old_transporter = delivery.transporter
                    delivery.assign_to_transporter(new_transporter)

                    DeliveryTracking.objects.create(
                        delivery=delivery,
                        status=TransportStatus.ASSIGNED,
                        notes=f"Reassigned from {old_transporter.user.get_full_name() if old_transporter else 'Unknown'} to \
                            {new_transporter.user.get_full_name()}",
                    )

                    reassigned += 1
                    results.append(
                        {
                            "delivery_id": str(delivery.delivery_id),
                            "status": "reassigned",
                            "new_transporter": new_transporter.user.get_full_name(),
                        }
                    )
                else:
                    failed += 1
                    results.append(
                        {
                            "delivery_id": str(delivery.delivery_id),
                            "status": "failed",
                            "error": "Delivery not eligible for reassignment or capacity exceeded",
                        }
                    )
            except Exception as e:
                failed += 1
                results.append({"delivery_id": str(delivery.delivery_id), "status": "failed", "error": str(e)})

        return Response(
            {
                "operation": "reassign",
                "total_processed": deliveries.count(),
                "reassigned": reassigned,
                "failed": failed,
                "new_transporter": new_transporter.user.get_full_name(),
                "results": results,
            }
        )
