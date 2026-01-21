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

"""
Example URL patterns generated:

GET  /api/geo/zones/                          - List all zones
GET  /api/geo/zones/{id}/                     - Get zone details
POST /api/geo/zones/nearby/                   - Get nearby zones
POST /api/geo/zones/detect-zone/              - Detect current zone

POST /api/geo/locations/                      - Create location snapshot
GET  /api/geo/locations/                      - List user's locations
POST /api/geo/locations/batch/                - Batch create locations

POST /api/geo/deliverability/check/           - Check deliverability
POST /api/geo/deliverability/estimate/        - Get delivery estimate
POST /api/geo/deliverability/filter-products/ - Filter products by location
"""
