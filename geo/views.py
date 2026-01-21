from datetime import timedelta

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from producer.models import MarketplaceProduct
from producer.serializers import MarketplaceProductSerializer

from .models import GeographicZone, SaleRegion, UserLocationSnapshot
from .serializers import (
    DeliverabilityCheckSerializer,
    DeliveryEstimateSerializer,
    GeographicZoneSerializer,
    LocationInputSerializer,
    UserLocationSnapshotSerializer,
)
from .services import (
    GeoLocationService,
    GeoProductFilterService,
)


class GeographicZoneViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve geographic zones.
    Provides zone information for frontend.

    Endpoints:
        GET /api/geo/zones/ - List all zones
        GET /api/geo/zones/{id}/ - Get zone details
        POST /api/geo/zones/nearby/ - Get nearby zones
    """

    queryset = GeographicZone.objects.filter(is_active=True)
    serializer_class = GeographicZoneSerializer
    permission_classes = [AllowAny]
    filterset_fields = ["tier", "name"]
    ordering_fields = ["name", "tier", "created_at"]
    ordering = ["name"]

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def nearby(self, request):
        """
        Get zones nearby to coordinates.

        Request body:
        {
            "latitude": 27.7172,
            "longitude": 85.3240,
            "distance_km": 50
        }

        Response:
        {
            "zones": [
                {
                    "id": 1,
                    "name": "Kathmandu City",
                    "tier": "tier1",
                    "distance_km": 2.5
                }
            ]
        }
        """
        serializer = LocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        latitude = serializer.validated_data["latitude"]
        longitude = serializer.validated_data["longitude"]
        distance_km = request.data.get("distance_km", 50)

        service = GeoLocationService()
        zones = service.get_nearby_zones(latitude, longitude, distance_km)

        return Response(
            {
                "zones": GeographicZoneSerializer(zones, many=True).data,
                "count": len(zones),
            }
        )

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def detect_zone(self, request):
        """
        Detect which zone user is in based on coordinates.

        Request:
        {
            "latitude": 27.7172,
            "longitude": 85.3240
        }

        Response:
        {
            "zone": {
                "id": 1,
                "name": "Kathmandu City",
                "tier": "tier1"
            },
            "nearby_zones": [...]
        }
        """
        serializer = LocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        latitude = serializer.validated_data["latitude"]
        longitude = serializer.validated_data["longitude"]

        service = GeoLocationService()
        user_zone = service.get_user_zone(request.user if request.user.is_authenticated else None, latitude, longitude)
        nearby_zones = service.get_nearby_zones(latitude, longitude, distance_km=30)

        return Response(
            {
                "zone": GeographicZoneSerializer(user_zone).data if user_zone else None,
                "nearby_zones": GeographicZoneSerializer(nearby_zones, many=True).data,
            }
        )


class UserLocationViewSet(viewsets.ViewSet):
    """
    User location tracking and snapshot management.

    Endpoints:
        POST /api/geo/locations/ - Create location snapshot
        GET /api/geo/locations/ - List user's location snapshots
        POST /api/geo/locations/batch/ - Track multiple locations
    """

    permission_classes = [IsAuthenticated]

    def create(self, request):
        """
        Record user's current location.

        Request:
        {
            "latitude": 27.7172,
            "longitude": 85.3240,
            "accuracy_meters": 10,
            "session_id": "session_abc123"
        }
        """
        serializer = LocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = GeoLocationService()
        snapshot = service.create_location_snapshot(
            user=request.user,
            latitude=serializer.validated_data["latitude"],
            longitude=serializer.validated_data["longitude"],
            accuracy_meters=serializer.validated_data.get("accuracy_meters"),
            session_id=serializer.validated_data.get("session_id"),
        )

        return Response(UserLocationSnapshotSerializer(snapshot).data, status=status.HTTP_201_CREATED)

    def list(self, request):
        """List all location snapshots for authenticated user"""
        snapshots = UserLocationSnapshot.objects.filter(user=request.user).order_by("-created_at")[
            :100
        ]  # Last 100 snapshots

        serializer = UserLocationSnapshotSerializer(snapshots, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def batch(self, request):
        """
        Record multiple locations in batch.
        Useful for syncing buffered location data.

        Request:
        {
            "locations": [
                {"latitude": 27.7172, "longitude": 85.3240, "timestamp": "2024-01-01T12:00:00Z"},
                {"latitude": 27.7173, "longitude": 85.3241, "timestamp": "2024-01-01T12:01:00Z"}
            ]
        }
        """
        locations = request.data.get("locations", [])

        if not isinstance(locations, list):
            return Response({"error": _("locations must be a list")}, status=status.HTTP_400_BAD_REQUEST)

        service = GeoLocationService()
        created_snapshots = []

        for loc in locations:
            try:
                snapshot = service.create_location_snapshot(
                    user=request.user,
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    accuracy_meters=loc.get("accuracy_meters"),
                    session_id=loc.get("session_id"),
                )
                created_snapshots.append(snapshot)
            except Exception as e:
                pass  # Continue with other locations

        return Response(
            {
                "created": len(created_snapshots),
                "snapshots": UserLocationSnapshotSerializer(created_snapshots, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ProductDeliverabilityViewSet(viewsets.ViewSet):
    """
    Check product deliverability and delivery estimates.

    Endpoints:
        POST /api/geo/deliverability/check/ - Check if product is deliverable
        POST /api/geo/deliverability/estimate/ - Get delivery estimate
        POST /api/geo/deliverability/filter-products/ - Filter products by location
    """

    permission_classes = [AllowAny]

    @action(detail=False, methods=["post"])
    def check(self, request):
        """
        Check if specific product can be delivered to location.

        Request:
        {
            "product_id": 123,
            "latitude": 27.7172,
            "longitude": 85.3240
        }

        Response:
        {
            "is_deliverable": true,
            "reason": null,
            "estimated_days": 1,
            "shipping_cost": "0.00",
            "zone": "Kathmandu City"
        }
        """
        from producer.models import MarketplaceProduct

        serializer = DeliverabilityCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = get_object_or_404(MarketplaceProduct, id=serializer.validated_data["product_id"])

        service = GeoProductFilterService()
        can_deliver, reason = service.can_deliver_to_location(
            product,
            serializer.validated_data["latitude"],
            serializer.validated_data["longitude"],
            seller_latitude=product.product.producer.location.y if product.product.producer.location else None,
            seller_longitude=product.product.producer.location.x if product.product.producer.location else None,
        )

        delivery_estimate = service.get_delivery_estimate(
            product,
            serializer.validated_data["latitude"],
            serializer.validated_data["longitude"],
            seller_latitude=product.product.producer.location.y if product.product.producer.location else None,
            seller_longitude=product.product.producer.location.x if product.product.producer.location else None,
        )

        return Response(
            {
                "is_deliverable": can_deliver,
                "reason": reason,
                "estimated_days": delivery_estimate["estimated_days"],
                "shipping_cost": delivery_estimate["shipping_cost"],
                "zone": delivery_estimate["zone"],
            }
        )

    @action(detail=False, methods=["post"])
    def estimate(self, request):
        """
        Get delivery estimate for product to location.

        Request:
        {
            "product_id": 123,
            "latitude": 27.7172,
            "longitude": 85.3240
        }

        Response:
        {
            "estimated_days": 1,
            "shipping_cost": "0.00",
            "zone": "Kathmandu City",
            "is_same_day": true
        }
        """
        from producer.models import MarketplaceProduct

        serializer = DeliveryEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = get_object_or_404(MarketplaceProduct, id=serializer.validated_data["product_id"])

        service = GeoProductFilterService()
        estimate = service.get_delivery_estimate(
            product,
            serializer.validated_data["latitude"],
            serializer.validated_data["longitude"],
            seller_latitude=product.producer.location.y if product.producer.location else None,
            seller_longitude=product.producer.location.x if product.producer.location else None,
        )

        return Response(estimate)

    @action(detail=False, methods=["post"])
    def filter_products(self, request):
        """
        Get all products that can be delivered to location.

        Request:
        {
            "latitude": 27.7172,
            "longitude": 85.3240,
            "max_distance_km": 50
        }

        Response:
        {
            "count": 45,
            "latitude": 27.7172,
            "longitude": 85.3240,
            "zone": "Kathmandu City",
            "products": [...]
        }
        """
        from producer.models import MarketplaceProduct
        from producer.serializers import MarketplaceProductSerializer

        serializer = LocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        latitude = serializer.validated_data["latitude"]
        longitude = serializer.validated_data["longitude"]

        service = GeoProductFilterService()
        location_service = GeoLocationService()

        # Get user's zone
        user_zone = location_service.get_user_zone(
            request.user if request.user.is_authenticated else None, latitude, longitude
        )

        # Get all active products
        products = MarketplaceProduct.objects.filter(is_active=True)

        # Filter by deliverability
        deliverable_ids = []
        for product in products:
            can_deliver, _ = service.can_deliver_to_location(
                product,
                latitude,
                longitude,
                seller_latitude=product.producer.location.y if product.producer.location else None,
                seller_longitude=product.producer.location.x if product.producer.location else None,
            )
            if can_deliver:
                deliverable_ids.append(product.id)

        deliverable_products = products.filter(id__in=deliverable_ids)[:50]

        return Response(
            {
                "count": len(deliverable_ids),
                "latitude": latitude,
                "longitude": longitude,
                "zone": user_zone.name if user_zone else None,
                "products": MarketplaceProductSerializer(deliverable_products, many=True).data,
            }
        )


class ProductsGeoViewSet(viewsets.ViewSet):
    """
    Geographic product filtering and discovery.

    Endpoints:
        GET /api/products-geo/ - List products near location
        POST /api/products-geo/bulk_check_deliverability/ - Check multiple products
        POST /api/products-geo/estimate_delivery/ - Get delivery estimate
    """

    permission_classes = [AllowAny]

    def list(self, request):
        """
        List products available near user location.

        Query params:
            latitude (required): User latitude
            longitude (required): User longitude
            max_distance_km (optional): Filter by distance, default 50
            distance_km (optional): Same as max_distance_km

        Response:
        {
            "count": 150,
            "latitude": 27.7172,
            "longitude": 85.3240,
            "distance_km": 50,
            "zone": "Kathmandu City",
            "results": [
                {
                    "id": 1,
                    "product": 10,
                    "listed_price": "2999.00",
                    "distance_km": 2.5,
                    "user_zone": {...},
                    "is_deliverable_to_user": true
                }
            ]
        }
        """
        latitude = request.query_params.get("latitude")
        longitude = request.query_params.get("longitude")
        max_distance_km = request.query_params.get("max_distance_km", request.query_params.get("distance_km", 50))

        if not latitude or not longitude:
            return Response(
                {"error": "latitude and longitude are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
            max_distance_km = float(max_distance_km) if max_distance_km else 50
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid coordinate format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate coordinates
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return Response(
                {"error": "Invalid coordinates"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = GeoProductFilterService()
        location_service = GeoLocationService()
        user_point = Point(longitude, latitude, srid=4326)

        # Get user's zone
        user_zone = location_service.get_user_zone(None, latitude, longitude)

        # Get all active products with seller location
        products = MarketplaceProduct.objects.filter(is_active=True, seller_geo_point__isnull=False).select_related(
            "product", "product__producer"
        )

        # Filter by distance
        annotated_products = products.annotate(distance=Distance("seller_geo_point", user_point)).filter(
            distance__lte=max_distance_km * 1000
        )  # Convert to meters

        results = []
        for product in annotated_products:
            # Check deliverability
            can_deliver, reason = service.can_deliver_to_location(
                product,
                latitude,
                longitude,
                seller_latitude=product.seller_location_lat,
                seller_longitude=product.seller_location_lon,
            )

            # Get delivery estimate
            estimate = service.get_delivery_estimate(
                product,
                latitude,
                longitude,
                seller_latitude=product.seller_location_lat,
                seller_longitude=product.seller_location_lon,
            )

            distance_km = product.distance.km if product.distance else 0

            results.append(
                {
                    "id": product.id,
                    "product": product.product.id,
                    "product_name": product.product.name,
                    "listed_price": str(product.listed_price),
                    "distance_km": round(distance_km, 2),
                    "is_deliverable_to_user": can_deliver,
                    "delivery_reason_if_not": reason,
                    "user_zone": (
                        {
                            "id": user_zone.id,
                            "name": user_zone.name,
                            "tier": user_zone.tier,
                            "shipping_cost": str(user_zone.shipping_cost),
                            "estimated_delivery_days": user_zone.estimated_delivery_days,
                        }
                        if user_zone
                        else None
                    ),
                    "estimated_delivery": estimate,
                }
            )

        # Sort by distance
        results.sort(key=lambda x: x["distance_km"])

        return Response(
            {
                "count": len(results),
                "latitude": latitude,
                "longitude": longitude,
                "distance_km": max_distance_km,
                "zone": user_zone.name if user_zone else "Unknown",
                "results": results,
            }
        )

    @action(detail=False, methods=["post"])
    def bulk_check_deliverability(self, request):
        """
        Check deliverability for multiple products at once.

        Request:
        {
            "latitude": 27.7172,
            "longitude": 85.3240,
            "product_ids": [1, 2, 3, 4, 5]
        }

        Response:
        {
            "user_location": {"latitude": 27.7172, "longitude": 85.3240},
            "products": [
                {
                    "product_id": 1,
                    "is_deliverable": true,
                    "distance_km": 2.5,
                    "shipping_cost": "0.00",
                    "estimated_days": 1
                }
            ]
        }
        """
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        product_ids = request.data.get("product_ids", [])

        if not latitude or not longitude:
            return Response(
                {"error": "latitude and longitude are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not product_ids:
            return Response(
                {"error": "product_ids is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid coordinate format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = GeoProductFilterService()
        user_point = Point(longitude, latitude, srid=4326)

        products = MarketplaceProduct.objects.filter(id__in=product_ids, is_active=True).annotate(
            distance=Distance("seller_geo_point", user_point)
        )

        results = []
        for product in products:
            can_deliver, reason = service.can_deliver_to_location(
                product,
                latitude,
                longitude,
                seller_latitude=product.seller_location_lat,
                seller_longitude=product.seller_location_lon,
            )

            estimate = service.get_delivery_estimate(
                product,
                latitude,
                longitude,
                seller_latitude=product.seller_location_lat,
                seller_longitude=product.seller_location_lon,
            )

            distance_km = product.distance.km if product.distance else 0

            results.append(
                {
                    "product_id": product.id,
                    "is_deliverable": can_deliver,
                    "distance_km": round(distance_km, 2),
                    "shipping_cost": str(estimate["shipping_cost"]),
                    "estimated_days": estimate["estimated_days"],
                    "zone": estimate["zone"],
                }
            )

        return Response(
            {
                "user_location": {"latitude": latitude, "longitude": longitude},
                "count": len(results),
                "products": results,
            }
        )

    @action(detail=False, methods=["post"])
    def estimate_delivery(self, request):
        """
        Get delivery estimate for a specific product.

        Request:
        {
            "product_id": 123,
            "latitude": 27.7172,
            "longitude": 85.3240
        }

        Response:
        {
            "product_id": 123,
            "is_deliverable": true,
            "distance_km": 2.5,
            "shipping_cost": "0.00",
            "estimated_days": 1,
            "estimated_delivery_date": "2026-01-22",
            "zone": "Kathmandu City"
        }
        """
        product_id = request.data.get("product_id")
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")

        if not all([product_id, latitude, longitude]):
            return Response(
                {"error": "product_id, latitude, and longitude are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = MarketplaceProduct.objects.get(id=product_id, is_active=True)
            latitude = float(latitude)
            longitude = float(longitude)
        except MarketplaceProduct.DoesNotExist:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid coordinate format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = GeoProductFilterService()
        user_point = Point(longitude, latitude, srid=4326)

        can_deliver, reason = service.can_deliver_to_location(
            product,
            latitude,
            longitude,
            seller_latitude=product.seller_location_lat,
            seller_longitude=product.seller_location_lon,
        )

        estimate = service.get_delivery_estimate(
            product,
            latitude,
            longitude,
            seller_latitude=product.seller_location_lat,
            seller_longitude=product.seller_location_lon,
        )

        # Calculate estimated delivery date
        estimated_date = (timezone.now() + timedelta(days=estimate["estimated_days"])).date()

        if product.seller_geo_point:
            distance_km = product.seller_geo_point.distance(user_point) / 1000
        else:
            distance_km = 0

        return Response(
            {
                "product_id": product_id,
                "is_deliverable": can_deliver,
                "delivery_reason_if_not": reason,
                "distance_km": round(distance_km, 2),
                "shipping_cost": str(estimate["shipping_cost"]),
                "estimated_days": estimate["estimated_days"],
                "estimated_delivery_date": estimated_date.isoformat(),
                "zone": estimate["zone"],
                "is_same_day": estimate["is_same_day"],
            }
        )
