import logging

from django.conf import settings
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .middleware.auth import ExternalAPIAuthentication

from .models import (
    ExternalBusiness,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
    ExternalDeliveryStatusHistory,
)
from .permissions import IsExternalBusinessOwner, IsInternalStaff
from .serializers import (
    ExternalBusinessSerializer,
    ExternalBusinessStatsSerializer,
    ExternalDeliveryCreateSerializer,
    ExternalDeliveryListSerializer,
    ExternalDeliverySerializer,
    ExternalDeliveryStatusHistorySerializer,
    ExternalDeliveryTrackingSerializer,
    ExternalDeliveryUpdateStatusSerializer,
    WebhookTestSerializer,
)
from .utils import calculate_delivery_stats, send_webhook_notification

# Import tasks only when needed to avoid circular imports
# from .tasks import process_external_delivery, send_delivery_notifications

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ExternalBusinessViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing external business registrations
    Only internal staff can access all businesses
    """

    queryset = ExternalBusiness.objects.all()
    serializer_class = ExternalBusinessSerializer
    permission_classes = [IsAuthenticated, IsInternalStaff]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by plan
        plan_filter = self.request.query_params.get("plan")
        if plan_filter:
            queryset = queryset.filter(plan=plan_filter)

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(business_name__icontains=search)
                | Q(business_email__icontains=search)
                | Q(contact_person__icontains=search)
            )

        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve an external business"""
        business = self.get_object()

        if business.status != ExternalBusinessStatus.PENDING:
            return Response({"error": "Only pending businesses can be approved"}, status=status.HTTP_400_BAD_REQUEST)

        business.status = ExternalBusinessStatus.APPROVED
        business.approved_by = request.user
        business.approved_at = timezone.now()
        business.save()

        return Response({"message": "Business approved successfully", "data": self.get_serializer(business).data})

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        """Suspend an external business"""
        business = self.get_object()

        if business.status == ExternalBusinessStatus.SUSPENDED:
            return Response({"error": "Business is already suspended"}, status=status.HTTP_400_BAD_REQUEST)

        business.status = ExternalBusinessStatus.SUSPENDED
        business.save()

        return Response({"message": "Business suspended successfully", "data": self.get_serializer(business).data})

    @action(detail=True, methods=["post"])
    def regenerate_keys(self, request, pk=None):
        """Regenerate API keys for external business"""
        business = self.get_object()

        business.api_key = business.generate_api_key()
        business.webhook_secret = business.generate_webhook_secret()
        business.save(update_fields=["api_key", "webhook_secret"])

        return Response(
            {
                "message": "API keys regenerated successfully",
                "api_key": business.api_key,
                "webhook_secret": business.webhook_secret,
            }
        )

    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        """Get detailed statistics for external business"""
        business = self.get_object()
        stats = calculate_delivery_stats(business)

        serializer = ExternalBusinessStatsSerializer(stats)
        return Response(serializer.data)


class ExternalDeliveryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for external API delivery management
    Uses external API key authentication for external businesses
    """

    serializer_class = ExternalDeliverySerializer
    authentication_classes = [ExternalAPIAuthentication]
    permission_classes = [IsAuthenticated, IsExternalBusinessOwner]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # External API request - filter by external business
        return ExternalDelivery.objects.filter(external_business=self.request.external_business).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return ExternalDeliveryCreateSerializer
        elif self.action == "list":
            return ExternalDeliveryListSerializer
        elif self.action == "update_status":
            return ExternalDeliveryUpdateStatusSerializer
        return ExternalDeliverySerializer

    def create(self, request, *args, **kwargs):
        """Create new external delivery"""
        # Check if external business can create delivery
        can_create, message = request.external_business.can_create_delivery()
        if not can_create:
            return Response({"error": message}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Set the external business
        delivery = serializer.save(external_business=request.external_business)

        # Return the created delivery
        response_serializer = ExternalDeliverySerializer(delivery)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsExternalBusinessOwner])
    def update_status(self, request, pk=None):
        """Update delivery status"""
        delivery = self.get_object()
        serializer = ExternalDeliveryUpdateStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        notes = serializer.validated_data.get("notes", "")

        # Update delivery status
        delivery.status = new_status
        delivery.save()

        # Create status history
        ExternalDeliveryStatusHistory.objects.create(
            delivery=delivery,
            status=new_status,
            notes=notes,
            updated_by_business=request.external_business,
        )

        return Response({"message": "Status updated successfully"})

    @action(detail=True, methods=["get"])
    def tracking(self, request, pk=None):
        """Get delivery tracking information"""
        delivery = self.get_object()
        serializer = ExternalDeliveryTrackingSerializer(delivery)
        return Response(serializer.data)


class InternalExternalDeliveryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for internal staff delivery management
    Uses standard Django authentication for internal staff
    """

    serializer_class = ExternalDeliverySerializer
    permission_classes = [IsAuthenticated, IsInternalStaff]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Internal request - show all deliveries
        return ExternalDelivery.objects.all().order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return ExternalDeliveryCreateSerializer
        elif self.action == "list":
            return ExternalDeliveryListSerializer
        elif self.action == "update_status":
            return ExternalDeliveryUpdateStatusSerializer
        return ExternalDeliverySerializer

    def create(self, request, *args, **kwargs):
        """Create new external delivery - for internal staff"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery = serializer.save()

        # Process delivery asynchronously
        from .tasks import process_external_delivery

        process_external_delivery.delay(delivery.id)

        return Response(ExternalDeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):
        """Update delivery status"""
        delivery = self.get_object()
        serializer = ExternalDeliveryUpdateStatusSerializer(data=request.data, context={"delivery": delivery})
        serializer.is_valid(raise_exception=True)

        try:
            delivery.update_status(
                new_status=serializer.validated_data["status"],
                reason=serializer.validated_data.get("reason"),
                user=request.user,
            )

            # Send notifications
            from .tasks import send_delivery_notifications

            send_delivery_notifications.delay(delivery.id, delivery.status)

            return Response({"message": "Status updated successfully", "data": ExternalDeliverySerializer(delivery).data})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel delivery"""
        delivery = self.get_object()

        if not delivery.can_cancel():
            return Response({"error": "Delivery cannot be cancelled in current status"}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("reason", "")
        delivery.update_status(new_status=ExternalDeliveryStatus.CANCELLED, reason=reason, user=request.user)

        return Response({"message": "Delivery cancelled successfully", "data": ExternalDeliverySerializer(delivery).data})

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Get delivery status history"""
        delivery = self.get_object()
        history = delivery.status_history.all().order_by("-changed_at")

        serializer = ExternalDeliveryStatusHistorySerializer(history, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by cities
        pickup_city = self.request.query_params.get("pickup_city")
        if pickup_city:
            queryset = queryset.filter(pickup_city__icontains=pickup_city)

        delivery_city = self.request.query_params.get("delivery_city")
        if delivery_city:
            queryset = queryset.filter(delivery_city__icontains=delivery_city)

        # Date range filter
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        # Search by tracking number or external ID
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(tracking_number__icontains=search)
                | Q(external_delivery_id__icontains=search)
                | Q(delivery_name__icontains=search)
                | Q(delivery_phone__icontains=search)
            )

        return queryset


@api_view(["GET"])
@permission_classes([])
def track_delivery(request, tracking_number):
    """
    Public endpoint for tracking deliveries
    No authentication required
    """
    try:
        delivery = ExternalDelivery.objects.get(tracking_number=tracking_number)
        serializer = ExternalDeliveryTrackingSerializer(delivery)
        return Response(serializer.data)
    except ExternalDelivery.DoesNotExist:
        return Response({"error": "Delivery not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([])
def register_external_business(request):
    """
    Public endpoint for external business registration
    """
    serializer = ExternalBusinessSerializer(data=request.data)
    if serializer.is_valid():
        business = serializer.save()

        return Response(
            {
                "message": "Registration submitted successfully. You will receive API credentials once approved.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExternalDashboardView(APIView):
    """
    Dashboard view for external businesses
    """

    authentication_classes = [ExternalAPIAuthentication]
    permission_classes = [IsAuthenticated, IsExternalBusinessOwner]

    def get(self, request):
        business = request.external_business

        # Get basic stats
        deliveries = business.external_deliveries.all()
        total_deliveries = deliveries.count()

        # Status breakdown
        status_counts = deliveries.values("status").annotate(count=Count("status"))

        # Recent deliveries
        recent_deliveries = deliveries.order_by("-created_at")[:10]

        # Monthly stats
        now = timezone.now()
        current_month_deliveries = deliveries.filter(created_at__month=now.month, created_at__year=now.year)

        return Response(
            {
                "business_info": ExternalBusinessSerializer(business).data,
                "total_deliveries": total_deliveries,
                "current_month_deliveries": current_month_deliveries.count(),
                "status_breakdown": list(status_counts),
                "recent_deliveries": ExternalDeliveryListSerializer(recent_deliveries, many=True).data,
                "usage_stats": business.get_usage_stats(),
            }
        )


class InternalDashboardView(APIView):
    """
    Internal dashboard for admin users
    """

    permission_classes = [IsAuthenticated, IsInternalStaff]

    def get(self, request):
        # Business stats
        total_businesses = ExternalBusiness.objects.count()
        approved_businesses = ExternalBusiness.objects.filter(status=ExternalBusinessStatus.APPROVED).count()
        pending_businesses = ExternalBusiness.objects.filter(status=ExternalBusinessStatus.PENDING).count()

        # Delivery stats
        total_deliveries = ExternalDelivery.objects.count()
        pending_deliveries = ExternalDelivery.objects.filter(status=ExternalDeliveryStatus.PENDING).count()
        delivered_count = ExternalDelivery.objects.filter(status=ExternalDeliveryStatus.DELIVERED).count()

        # Revenue stats
        total_revenue = ExternalDelivery.objects.aggregate(total=Sum("platform_commission"))["total"] or 0

        # Monthly growth
        now = timezone.now()
        current_month_deliveries = ExternalDelivery.objects.filter(
            created_at__month=now.month, created_at__year=now.year
        ).count()

        return Response(
            {
                "business_stats": {
                    "total_businesses": total_businesses,
                    "approved_businesses": approved_businesses,
                    "pending_businesses": pending_businesses,
                },
                "delivery_stats": {
                    "total_deliveries": total_deliveries,
                    "pending_deliveries": pending_deliveries,
                    "delivered_count": delivered_count,
                    "success_rate": (delivered_count / total_deliveries * 100) if total_deliveries > 0 else 0,
                },
                "revenue_stats": {
                    "total_revenue": float(total_revenue),
                    "current_month_deliveries": current_month_deliveries,
                },
            }
        )


@api_view(["POST"])
@authentication_classes([ExternalAPIAuthentication])
@permission_classes([IsAuthenticated, IsExternalBusinessOwner])
def test_webhook(request):
    """
    Test webhook endpoint for external businesses
    """
    serializer = WebhookTestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    webhook_url = serializer.validated_data["webhook_url"]
    event_type = serializer.validated_data["event_type"]
    test_data = serializer.validated_data.get("test_data", {})

    try:
        result = send_webhook_notification(
            business=request.external_business, event_type=event_type, data=test_data, webhook_url=webhook_url
        )

        return Response(
            {
                "success": True,
                "message": "Webhook test successful",
                "response_status": result.get("response_status"),
                "response_time": result.get("response_time"),
            }
        )
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


def external_delivery_docs(request):
    """
    Serve API documentation page
    """
    from django.shortcuts import render

    return render(request, "external_delivery/docs.html")
