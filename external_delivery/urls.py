from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import (
    ExternalBusinessLoginView,
    ExternalBusinessLogoutView,
    ExternalBusinessRefreshView,
    change_password,
    profile,
    reset_password,
    setup_account,
)
from .views import (
    ExternalBusinessViewSet,
    ExternalDashboardView,
    ExternalDeliveryViewSet,
    InternalExternalDeliveryViewSet,
    InternalDashboardView,
    external_delivery_docs,
    register_external_business,
    test_webhook,
    track_delivery,
)

# Create routers for different endpoints
external_router = DefaultRouter()
external_router.register(r"deliveries", ExternalDeliveryViewSet, basename="external-delivery")

internal_router = DefaultRouter()
internal_router.register(r"businesses", ExternalBusinessViewSet)
internal_router.register(r"deliveries", InternalExternalDeliveryViewSet, basename="internal-external-delivery")

# API URLs
urlpatterns = [
    # External API endpoints (for external businesses)
    path(
        "api/external/",
        include(
            [
                path("", include(external_router.urls)),
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
                path("", include(internal_router.urls)),
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
                # Authentication endpoints
                path("auth/login/", ExternalBusinessLoginView.as_view(), name="external-login"),
                path("auth/logout/", ExternalBusinessLogoutView.as_view(), name="external-logout"),
                path("auth/refresh/", ExternalBusinessRefreshView.as_view(), name="external-refresh"),
                path("auth/setup/", setup_account, name="external-setup-account"),
                path("auth/reset-password/", reset_password, name="external-reset-password"),
                path("auth/profile/", profile, name="external-profile"),
                path("auth/change-password/", change_password, name="external-change-password"),
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
