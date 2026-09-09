from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .risk_views import (
    AlertThresholdViewSet,
    RiskCategoryViewSet,
    SupplierScorecardViewSet,
    SupplyChainAlertViewSet,
    SupplyChainKPIViewSet,
)
from .views import DailyProductStatsView
# Initialize the router for risk management ViewSets
router = DefaultRouter()
router.register(r"supplier-scorecards", SupplierScorecardViewSet, basename="supplier-scorecard")
router.register(r"kpis", SupplyChainKPIViewSet, basename="kpi")
router.register(r"alerts", SupplyChainAlertViewSet, basename="alert")
router.register(r"alert-thresholds", AlertThresholdViewSet, basename="alert-threshold")
router.register(r"risk-categories", RiskCategoryViewSet, basename="risk-category")

urlpatterns = [
    path("daily-product-stats/", DailyProductStatsView.as_view(), name="daily-product-stats"),
    path("", include(router.urls)),
]
