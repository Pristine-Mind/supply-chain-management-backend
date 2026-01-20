import logging
from datetime import timedelta

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    AlertThreshold,
    RiskCategory,
    RiskDrillDown,
    SupplierScorecard,
    SupplierScoreHistory,
    SupplyChainAlert,
    SupplyChainKPI,
)
from .serializers import (
    AlertThresholdSerializer,
    RiskCategorySerializer,
    RiskDrillDownSerializer,
    SupplierScorecardSerializer,
    SupplierScoreHistorySerializer,
    SupplyChainAlertSerializer,
    SupplyChainKPISerializer,
)

logger = logging.getLogger(__name__)


class SupplierScorecardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Supplier health scorecard API.

    Endpoints:
    - GET /api/v1/supplier-scorecards/ - List all scorecards
    - GET /api/v1/supplier-scorecards/{id}/ - Get specific scorecard
    - GET /api/v1/supplier-scorecards/current/ - Get current user's scorecard
    - GET /api/v1/supplier-scorecards/{id}/history/ - Get 90-day history
    """

    queryset = SupplierScorecard.objects.all()
    serializer_class = SupplierScorecardSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["health_status", "supplier__name"]
    ordering = ["-health_score"]

    def get_queryset(self):
        """Filter scorecards based on user type."""
        user = self.request.user

        # Admins and staff see all scorecards
        if user.is_staff or user.is_superuser:
            return SupplierScorecard.objects.all()

        # Suppliers see only their own scorecard
        if hasattr(user, "producer"):
            return SupplierScorecard.objects.filter(supplier=user.producer)

        # Other users see nothing
        return SupplierScorecard.objects.none()

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current scorecard for authenticated user's supplier."""
        user = request.user
        try:
            if hasattr(user, "producer"):
                scorecard = SupplierScorecard.objects.filter(supplier=user.producer).first()
                if scorecard:
                    serializer = self.get_serializer(scorecard)
                    return Response(serializer.data)

            return Response({"detail": "No scorecard found for your supplier"}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"Error fetching current scorecard: {e}")
            return Response({"error": "Error fetching scorecard"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Get 90-day score history for a supplier."""
        try:
            scorecard = self.get_object()
            history = SupplierScoreHistory.objects.filter(supplier=scorecard.supplier).order_by("-recorded_at")[:90]

            serializer = SupplierScoreHistorySerializer(history, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error fetching scorecard history: {e}")
            return Response({"error": "Error fetching history"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"])
    def comparison(self, request):
        """Compare multiple suppliers' scores."""
        try:
            supplier_ids = request.query_params.getlist("supplier_ids")

            if not supplier_ids:
                scorecards = SupplierScorecard.objects.all()[:10]
            else:
                scorecards = SupplierScorecard.objects.filter(supplier__id__in=supplier_ids)

            serializer = self.get_serializer(scorecards, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error in scorecard comparison: {e}")
            return Response({"error": "Error comparing scorecards"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SupplyChainKPIViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Key Performance Indicator dashboard API.

    Endpoints:
    - GET /api/v1/kpis/ - List KPI snapshots
    - GET /api/v1/kpis/{id}/ - Get specific KPI
    - GET /api/v1/kpis/current/ - Get latest KPI snapshot
    - GET /api/v1/kpis/trends/ - Get 30-day trends
    """

    queryset = SupplyChainKPI.objects.all()
    serializer_class = SupplyChainKPISerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["supplier__name", "snapshot_date"]
    ordering = ["-snapshot_date"]

    def get_queryset(self):
        """Filter KPIs based on user type."""
        user = self.request.user

        # Admins and staff see all KPIs
        if user.is_staff or user.is_superuser:
            return SupplyChainKPI.objects.all()

        # Suppliers see only their own KPIs
        if hasattr(user, "producer"):
            return SupplyChainKPI.objects.filter(supplier=user.producer)

        # Other users see nothing
        return SupplyChainKPI.objects.none()

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get latest KPI snapshot.
        
        For admins: Returns the most recent KPI snapshot across all suppliers.
        For suppliers: Returns their own latest KPI snapshot.
        """
        try:
            user = request.user
            kpi = None

            # Admins see the latest KPI across all suppliers
            if user.is_staff or user.is_superuser:
                kpi = SupplyChainKPI.objects.all().order_by("-snapshot_date").first()
            # Suppliers see their own latest KPI
            elif hasattr(user, "producer"):
                kpi = SupplyChainKPI.objects.filter(supplier=user.producer).order_by("-snapshot_date").first()

            if kpi:
                serializer = self.get_serializer(kpi)
                return Response(serializer.data)

            return Response({"detail": "No KPI data available yet"}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"Error fetching current KPI: {e}")
            return Response({"error": "Error fetching KPI"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"])
    def trends(self, request):
        """Get 30-day KPI trends.
        
        For admins: Returns trend data for all suppliers or specific supplier if supplier_id provided.
        For suppliers: Returns their own 30-day trend data.
        
        Query Parameters:
        - supplier_id (optional, admin only): Filter by specific supplier ID
        """
        try:
            user = request.user
            today = timezone.now().date()
            period_30 = today - timedelta(days=30)
            kpis = None

            # Admins can view all KPI trends or filter by supplier_id
            if user.is_staff or user.is_superuser:
                supplier_id = request.query_params.get("supplier_id")
                if supplier_id:
                    kpis = SupplyChainKPI.objects.filter(
                        supplier_id=supplier_id, snapshot_date__gte=period_30
                    ).order_by("snapshot_date")
                else:
                    kpis = SupplyChainKPI.objects.filter(snapshot_date__gte=period_30).order_by("snapshot_date")
            # Suppliers see their own 30-day trends
            elif hasattr(user, "producer"):
                kpis = SupplyChainKPI.objects.filter(
                    supplier=user.producer, snapshot_date__gte=period_30
                ).order_by("snapshot_date")

            if kpis and kpis.exists():
                serializer = self.get_serializer(kpis, many=True)
                return Response(serializer.data)

            return Response({"detail": "No trend data available yet"}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"Error fetching KPI trends: {e}")
            return Response({"error": "Error fetching trends"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SupplyChainAlertViewSet(viewsets.ModelViewSet):
    """
    Supply chain alert management API.

    Endpoints:
    - GET /api/v1/alerts/ - List alerts
    - POST /api/v1/alerts/ - Create alert (admin only)
    - GET /api/v1/alerts/{id}/ - Get alert details
    - POST /api/v1/alerts/{id}/acknowledge/ - Acknowledge alert
    - POST /api/v1/alerts/{id}/resolve/ - Resolve alert
    - GET /api/v1/alerts/active/ - Get active alerts
    - GET /api/v1/alerts/statistics/ - Get alert statistics
    """

    queryset = SupplyChainAlert.objects.all()
    serializer_class = SupplyChainAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["alert_type", "severity", "status", "supplier__name"]
    ordering = ["-triggered_at"]
    search_fields = ["title", "description"]

    def get_queryset(self):
        """Filter alerts by user's supplier."""
        user = self.request.user

        if user.is_staff:
            return SupplyChainAlert.objects.all()

        if hasattr(user, "producer"):
            return SupplyChainAlert.objects.filter(supplier=user.producer)

        return SupplyChainAlert.objects.none()

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert."""
        try:
            alert = self.get_object()
            alert.acknowledge(request.user)
            serializer = self.get_serializer(alert)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error acknowledging alert: {e}")
            return Response({"error": "Error acknowledging alert"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Manually resolve an alert."""
        try:
            alert = self.get_object()
            alert.resolve(request.user)
            serializer = self.get_serializer(alert)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error resolving alert: {e}")
            return Response({"error": "Error resolving alert"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get all active alerts."""
        try:
            alerts = self.get_queryset().filter(status__in=["active", "acknowledged"]).order_by("-triggered_at")

            page = self.paginate_queryset(alerts)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(alerts, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error fetching active alerts: {e}")
            return Response({"error": "Error fetching alerts"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """Get alert statistics."""
        try:
            queryset = self.get_queryset()

            stats = {
                "total_alerts": queryset.count(),
                "active": queryset.filter(status="active").count(),
                "acknowledged": queryset.filter(status="acknowledged").count(),
                "resolved": queryset.filter(status__in=["resolved", "auto_resolved"]).count(),
                "by_severity": {
                    "critical": queryset.filter(severity="critical").count(),
                    "warning": queryset.filter(severity="warning").count(),
                    "info": queryset.filter(severity="info").count(),
                },
                "by_type": {
                    alert_type: queryset.filter(alert_type=alert_type).count()
                    for alert_type, _ in SupplyChainAlert.ALERT_TYPE_CHOICES
                },
                "last_7_days": queryset.filter(triggered_at__gte=timezone.now() - timedelta(days=7)).count(),
            }

            return Response(stats)

        except Exception as e:
            logger.error(f"Error calculating alert statistics: {e}")
            return Response({"error": "Error calculating statistics"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AlertThresholdViewSet(viewsets.ModelViewSet):
    """
    Alert threshold configuration API (admin only).

    Endpoints:
    - GET /api/v1/alert-thresholds/ - List thresholds
    - PUT /api/v1/alert-thresholds/{id}/ - Update threshold
    """

    queryset = AlertThreshold.objects.all()
    serializer_class = AlertThresholdSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["alert_type"]

    def get_queryset(self):
        """Only admins can view thresholds."""
        if self.request.user.is_staff:
            return AlertThreshold.objects.all()
        return AlertThreshold.objects.none()


class RiskCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Risk category dashboard API.

    Endpoints:
    - GET /api/v1/risk-categories/ - List risk categories
    - GET /api/v1/risk-categories/current/ - Get latest risk assessment
    - GET /api/v1/risk-categories/{id}/drill-downs/ - Get risk details
    - GET /api/v1/risk-categories/summary/ - Get dashboard summary
    """

    queryset = RiskCategory.objects.all()
    serializer_class = RiskCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["supplier__name", "overall_risk_level"]
    ordering = ["-snapshot_date"]

    def get_queryset(self):
        """Filter risk categories based on user type."""
        user = self.request.user

        # Admins and staff see all risk categories
        if user.is_staff or user.is_superuser:
            return RiskCategory.objects.all()

        # Suppliers see only their own risk categories
        if hasattr(user, "producer"):
            return RiskCategory.objects.filter(supplier=user.producer)

        # Other users see nothing
        return RiskCategory.objects.none()

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current risk assessment."""
        try:
            today = timezone.now().date()
            user = request.user

            if user.is_staff:
                # Admins see global risk
                risk = RiskCategory.objects.filter(supplier__isnull=True, snapshot_date=today).first()
            elif hasattr(user, "producer"):
                # Suppliers see their own risk
                risk = RiskCategory.objects.filter(supplier=user.producer, snapshot_date=today).first()
            else:
                return Response({"detail": "No risk data found"}, status=status.HTTP_404_NOT_FOUND)

            if risk:
                serializer = self.get_serializer(risk)
                return Response(serializer.data)

            return Response({"detail": "No risk assessment found for today"}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"Error fetching current risk assessment: {e}")
            return Response({"error": "Error fetching risk assessment"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["get"])
    def drill_downs(self, request, pk=None):
        """Get detailed list for a risk category."""
        try:
            risk = self.get_object()
            drill_downs = RiskDrillDown.objects.filter(risk_category=risk).order_by("-created_at")

            page = self.paginate_queryset(drill_downs)
            if page is not None:
                serializer = RiskDrillDownSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = RiskDrillDownSerializer(drill_downs, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error fetching drill-down details: {e}")
            return Response({"error": "Error fetching details"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get comprehensive risk dashboard summary."""
        try:
            today = timezone.now().date()
            user = request.user

            # Get risk category
            if user.is_staff:
                risk = RiskCategory.objects.filter(supplier__isnull=True, snapshot_date=today).first()
            elif hasattr(user, "producer"):
                risk = RiskCategory.objects.filter(supplier=user.producer, snapshot_date=today).first()
            else:
                return Response({"detail": "No data found"}, status=status.HTTP_404_NOT_FOUND)

            # Get supplier scorecard
            scorecard = None
            if hasattr(user, "producer"):
                scorecard = SupplierScorecard.objects.filter(supplier=user.producer).first()

            # Get latest KPI
            kpi = None
            if hasattr(user, "producer"):
                kpi = SupplyChainKPI.objects.filter(supplier=user.producer).order_by("-snapshot_date").first()

            # Get active alerts
            if user.is_staff:
                active_alerts = SupplyChainAlert.objects.filter(status__in=["active", "acknowledged"])
            elif hasattr(user, "producer"):
                active_alerts = SupplyChainAlert.objects.filter(
                    supplier=user.producer, status__in=["active", "acknowledged"]
                )
            else:
                active_alerts = SupplyChainAlert.objects.none()

            summary_data = {
                "timestamp": timezone.now(),
                "supplier_scorecard": SupplierScorecardSerializer(scorecard).data if scorecard else None,
                "kpis": SupplyChainKPISerializer(kpi).data if kpi else None,
                "critical_alerts": active_alerts.filter(severity="critical").count(),
                "warning_alerts": active_alerts.filter(severity="warning").count(),
                "info_alerts": active_alerts.filter(severity="info").count(),
                "total_alerts": active_alerts.count(),
                "risk_overview": RiskCategorySerializer(risk).data if risk else None,
            }

            return Response(summary_data)

        except Exception as e:
            logger.error(f"Error generating risk summary: {e}")
            return Response({"error": "Error generating summary"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
