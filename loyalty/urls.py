from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    LoyaltyTierViewSet,
    UserLoyaltyViewSet,
)

app_name = "loyalty"

router = DefaultRouter()
router.register(r"tiers", LoyaltyTierViewSet, basename="tier")
router.register(r"user", UserLoyaltyViewSet, basename="user-loyalty")

urlpatterns = [
    path("", include(router.urls)),
]
