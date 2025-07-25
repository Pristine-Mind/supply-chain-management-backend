import math

from datetime import datetime

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Delivery,
    DeliveryRating,
    DeliveryTracking,
    Transporter,
    TransportStatus,
)
from .serializers import (
    DeliveryCreateSerializer,
    DeliveryDashboardSerializer,
    DeliveryListSerializer,
    DeliveryRatingSerializer,
    DeliverySerializer,
    DeliveryStatusUpdateSerializer,
    DeliveryTrackingSerializer,
    LocationUpdateSerializer,
    NearbyDeliverySerializer,
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
