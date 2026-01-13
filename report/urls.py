from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CommandPaletteView,
    ERPHealthDashboardView,
    LostSalesView,
    RFMReportViewSet,
    WeeklyDigestViewSet,
)

router = DefaultRouter()
router.register(r"rfm-segments", RFMReportViewSet, basename="rfm-report")
router.register(r"weekly-digests", WeeklyDigestViewSet, basename="weekly-digest")


urlpatterns = [
    path("palette/", CommandPaletteView.as_view(), name="command-palette"),
    path("health/", ERPHealthDashboardView.as_view(), name="erp-health"),
    path("lost-sales/", LostSalesView.as_view(), name="lost-sales-report"),
    path("", include(router.urls)),
]
