from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CommandPaletteView, ERPHealthDashboardView, RFMReportViewSet

router = DefaultRouter()
router.register(r"rfm", RFMReportViewSet, basename="rfm-report")

urlpatterns = [
    path("palette/", CommandPaletteView.as_view(), name="command-palette"),
    path("health/", ERPHealthDashboardView.as_view(), name="erp-health"),
    path("", include(router.urls)),
]
