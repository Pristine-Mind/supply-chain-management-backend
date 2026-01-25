from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    GeographicZoneViewSet,
    ProductDeliverabilityViewSet,
    ProductsGeoViewSet,
    UserLocationViewSet,
)

router = DefaultRouter()
router.register(r"zones", GeographicZoneViewSet, basename="zone")
router.register(r"locations", UserLocationViewSet, basename="location")
router.register(r"deliverability", ProductDeliverabilityViewSet, basename="deliverability")
router.register(r"products-geo", ProductsGeoViewSet, basename="products-geo")

urlpatterns = [
    path("", include(router.urls)),
]
