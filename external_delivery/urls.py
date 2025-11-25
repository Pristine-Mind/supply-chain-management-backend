from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ExternalBusinessViewSet,
    ExternalDashboardView,
    ExternalDeliveryViewSet,
    InternalDashboardView,
    external_delivery_docs,
    register_external_business,
    test_webhook,
    track_delivery,
)

# Create router for viewsets
router = DefaultRouter()
router.register(r"businesses", ExternalBusinessViewSet)
router.register(r"deliveries", ExternalDeliveryViewSet, basename="external-delivery")

# API URLs
urlpatterns = [
    # External API endpoints (for external businesses)
    path(
        "api/external/",
        include(
            [
                path("", include(router.urls)),
                path("dashboard/", ExternalDashboardView.as_view(), name="external-dashboard"),
                path("webhook/test/", test_webhook, name="test-webhook"),
            ]
        ),
    ),
    # Internal API endpoints (for internal staff)
    path(
        "api/internal/external-delivery/",
        include(
            [
                path("", include(router.urls)),
                path("dashboard/", InternalDashboardView.as_view(), name="internal-external-dashboard"),
            ]
        ),
    ),
    # Public endpoints
    path(
        "api/public/external-delivery/",
        include(
            [
                path("register/", register_external_business, name="register-external-business"),
                path("track/<str:tracking_number>/", track_delivery, name="track-external-delivery"),
                path("docs/", external_delivery_docs, name="external-delivery-docs"),
            ]
        ),
    ),
    # Webhook endpoints
    path(
        "webhooks/external/",
        include(
            [
                # Add webhook receiver endpoints as needed
            ]
        ),
    ),
]
