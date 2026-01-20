from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertThresholdViewSet,
    RiskCategoryViewSet,
    SupplierScorecardViewSet,
    SupplyChainAlertViewSet,
    SupplyChainKPIViewSet,
)

router = DefaultRouter()

router.register(r"supplier-scorecards", SupplierScorecardViewSet, basename="supplier-scorecard")
router.register(r"kpis", SupplyChainKPIViewSet, basename="kpi")
router.register(r"alerts", SupplyChainAlertViewSet, basename="alert")
router.register(r"alert-thresholds", AlertThresholdViewSet, basename="alert-threshold")
router.register(r"risk-categories", RiskCategoryViewSet, basename="risk-category")

urlpatterns = [
    path("", include(router.urls)),
]
