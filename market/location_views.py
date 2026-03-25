from decimal import Decimal
from typing import Dict, List, Optional, Type, Union
from venv import logger

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db import models
from django.db.models import F, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from geo.models import GeographicZone
from geo.services import GeoLocationService, GeoProductFilterService
from market.models import MarketplaceProduct, MarketplaceUserProduct
from producer.models import Producer

from .additional_edge_cases import (
    ConnectivityMode,
    CrossBorderDeliveryHandler,
    EmergencyMode,
    EmergencyModeManager,
    GDPRLocationComplianceManager,
    MobileConnectivityHandler,
    SeasonalAvailabilityManager,
    TimezoneDeliveryCalculator,
)
from .advanced_caching import GeographicCacheManager
from .circuit_breakers import get_circuit_breaker
from .geographic_edge_cases import (
    DistanceCalculationHandler,
    GeographicDataIntegrityManager,
    GeographicEdgeCaseHandler,
)
from .graceful_degradation import GracefulDegradationManager
from .location_utils import (
    GeoServiceErrorHandler,
    LocationAPIErrorHandler,
    LocationValidationError,
    LocationValidator,
    handle_location_errors,
)
from .serializers import (
    DeliveryTimeEstimateSerializer,
    EnhancedMarketplaceProductSerializer,
    EnhancedMarketplaceUserProductSerializer,
    LocationFilteredProductListSerializer,
    LocationSearchRequestSerializer,
)


class LocationBasedProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for location-based product filtering and discovery.

    Supports both MarketplaceProduct and MarketplaceUserProduct with:
    - Distance-based filtering
    - Geographic zone detection
    - Delivery cost estimation
    - Performance optimization
    """

    permission_classes = [AllowAny]
    serializer_class = EnhancedMarketplaceProductSerializer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.geo_service = GeoLocationService()
        self.filter_service = GeoProductFilterService()
        self.edge_case_handler = GeographicEdgeCaseHandler()
        self.distance_handler = DistanceCalculationHandler()
        self.cache_manager = GeographicCacheManager()
        self.degradation_manager = GracefulDegradationManager()
        self.db_circuit_breaker = get_circuit_breaker("database")
        self.geo_circuit_breaker = get_circuit_breaker("geocoding")

        # Additional edge case handlers
        self.cross_border_handler = CrossBorderDeliveryHandler()
        self.timezone_calculator = TimezoneDeliveryCalculator()
        self.mobile_handler = MobileConnectivityHandler()
        self.seasonal_manager = SeasonalAvailabilityManager()
        self.emergency_manager = EmergencyModeManager()
        self.gdpr_manager = GDPRLocationComplianceManager()

    def get_queryset(self):
        """Base queryset - will be filtered by location in actions."""
        return MarketplaceProduct.objects.none()

    def get_serializer_class(self):
        """Dynamic serializer based on product type."""
        product_type = self.request.query_params.get("type", "marketplace")
        if product_type == "user":
            return EnhancedMarketplaceUserProductSerializer
        return EnhancedMarketplaceProductSerializer

    def _get_model_class(self, product_type: str) -> Type[models.Model]:
        """Get the appropriate model class based on product type."""
        if product_type == "user":
            return MarketplaceUserProduct
        return MarketplaceProduct

    def _validate_coordinates_comprehensive(self, latitude: float, longitude: float, request) -> Dict:
        """Comprehensive coordinate validation with all edge cases."""
        # Check GDPR compliance first
        user_ip = request.META.get("REMOTE_ADDR", "")
        gdpr_check = self.gdpr_manager.check_location_consent(request.user, user_ip)

        if not gdpr_check["can_process_location"]:
            return {"valid": False, "error": "Location processing requires consent", "gdpr_consent_required": True}

        # Basic validation using geographic edge case handler
        validation_result = self.edge_case_handler.validate_coordinates_comprehensive(latitude, longitude)

        if not validation_result["valid"]:
            return validation_result

        # Check for emergency mode restrictions
        emergency_mode = self.emergency_manager.get_current_emergency_mode()
        if emergency_mode != EmergencyMode.NORMAL:
            validation_result["emergency_mode"] = emergency_mode.value
            validation_result["emergency_restrictions"] = True

        # Apply GDPR anonymization if needed
        if gdpr_check["consent_required"]:
            anon_lat, anon_lon = self.gdpr_manager.anonymize_location_data(latitude, longitude, "city")
            validation_result["anonymized_coordinates"] = (anon_lat, anon_lon)

        return validation_result

    def _calculate_comprehensive_delivery_info(self, product, user_lat: float, user_lon: float, request) -> Dict:
        """Calculate delivery info with all edge cases handled."""
        try:
            # Get product location
            if hasattr(product, "product") and hasattr(product.product, "producer"):
                producer = product.product.producer
                if not producer or not producer.location:
                    return {"available": False, "reason": "Producer location not available"}
                product_lat, product_lon = producer.location.y, producer.location.x
                product_value = product.listed_price
                category = product.product.category
            else:
                if not product.location or not product.location.location:
                    return {"available": False, "reason": "Product location not available"}
                product_lat, product_lon = product.location.location.y, product.location.location.x
                product_value = product.price
                category = getattr(product, "category", "general")

            # Check cross-border delivery requirements
            cross_border_info = self.cross_border_handler.check_cross_border_delivery(
                product_lat, product_lon, user_lat, user_lon, category, product_value
            )

            # Calculate timezone-aware delivery estimate
            timezone_estimate = self.timezone_calculator.calculate_delivery_estimate(
                product_lat, product_lon, user_lat, user_lon
            )

            # Get emergency mode adjustments
            emergency_mode = self.emergency_manager.get_current_emergency_mode()
            emergency_delivery_info = self.emergency_manager.get_emergency_delivery_info(emergency_mode, product_value)

            # Calculate base distance and cost
            distance_result = self.distance_handler.calculate_distance_robust(
                product_lat, product_lon, user_lat, user_lon, method="auto"
            )

            if not distance_result["valid"]:
                return {"available": False, "reason": "Distance calculation failed"}

            base_distance = distance_result["distance_km"]
            base_cost = base_distance * 10  # 10 NPR per km

            # Apply cross-border adjustments
            total_cost = base_cost + cross_border_info.additional_fees
            if cross_border_info.customs_required:
                estimated_hours = 48 + cross_border_info.estimated_customs_delay_hours
            else:
                estimated_hours = 24

            # Apply emergency adjustments
            total_cost += emergency_delivery_info["surcharge"]
            if emergency_delivery_info["priority"] == "emergency":
                estimated_hours = emergency_delivery_info["estimated_hours"]

            return {
                "available": True,
                "distance_km": base_distance,
                "estimated_cost": float(total_cost),
                "estimated_delivery_time": timezone_estimate.estimated_delivery_time.isoformat(),
                "cross_border": {
                    "required": cross_border_info.customs_required,
                    "additional_fees": float(cross_border_info.additional_fees),
                    "required_documents": cross_border_info.required_documents,
                },
                "emergency_mode": emergency_mode.value,
                "timezone_info": {
                    "pickup_time": timezone_estimate.estimated_pickup_time.isoformat(),
                    "timezone": timezone_estimate.local_timezone,
                },
            }

        except Exception as e:
            logger.error(f"Comprehensive delivery calculation error: {e}")
            return {"available": False, "reason": f"Calculation error: {str(e)}"}

    def _apply_product_filters(
        self, queryset, product_type: str, category: Optional[str], min_price: Optional[float], max_price: Optional[float]
    ):
        """Apply category and price filters to queryset."""
        if category:
            if product_type == "user":
                queryset = queryset.filter(category=category)
            else:
                queryset = queryset.filter(product__category__name=category)

        if min_price is not None:
            price_field = "listed_price" if product_type == "marketplace" else "price"
            queryset = queryset.filter(**{f"{price_field}__gte": min_price})

        if max_price is not None:
            price_field = "listed_price" if product_type == "marketplace" else "price"
            queryset = queryset.filter(**{f"{price_field}__lte": max_price})

        return queryset

    def _apply_performance_optimizations(self, queryset, product_type: str):
        """Apply select_related and prefetch_related for performance."""
        if product_type == "marketplace":
            return queryset.select_related("product", "product__producer", "product__category").prefetch_related(
                "product__images", "marketplaceproductreview_set"
            )
        else:  # user products
            return queryset.select_related("user", "location").prefetch_related("images", "marketplaceuserproductreview_set")

    def _annotate_distance(
        self, queryset, latitude: float, longitude: float, field_name: str = "distance_km"
    ) -> models.QuerySet:
        """Annotate queryset with distance in kilometers."""
        user_location = Point(longitude, latitude, srid=4326)

        # Determine which location field to use based on model
        if queryset.model == MarketplaceProduct:
            location_field = "product__producer__location"
        else:  # MarketplaceUserProduct
            location_field = "location__location"

        # Annotate with distance in meters, then convert to km
        return queryset.annotate(distance_m=Distance(location_field, user_location)).annotate(
            **{field_name: Coalesce(F("distance_m") / 1000.0, Value(999999.0, output_field=FloatField()))}
        )

    @extend_schema(
        summary="Find nearby products",
        description="Get products within specified radius of user location",
        parameters=[
            OpenApiParameter("latitude", OpenApiTypes.FLOAT, required=True, description="User latitude"),
            OpenApiParameter("longitude", OpenApiTypes.FLOAT, required=True, description="User longitude"),
            OpenApiParameter("radius_km", OpenApiTypes.FLOAT, description="Search radius in km (default: 50)"),
            OpenApiParameter(
                "type", OpenApiTypes.STR, description="Product type: 'marketplace' or 'user' (default: marketplace)"
            ),
            OpenApiParameter("category", OpenApiTypes.STR, description="Product category filter"),
            OpenApiParameter("min_price", OpenApiTypes.FLOAT, description="Minimum price filter"),
            OpenApiParameter("max_price", OpenApiTypes.FLOAT, description="Maximum price filter"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Maximum results (default: 50)"),
        ],
    )
    @action(detail=False, methods=["get"])
    @handle_location_errors
    def nearby(self, request):
        """Get products near user location with distance-based filtering."""
        try:
            # Validate required parameters using LocationValidator
            lat_param = request.query_params.get("latitude")
            lon_param = request.query_params.get("longitude")

            if lat_param is None or lon_param is None:
                return Response(
                    {"error": "latitude and longitude are required parameters"}, status=status.HTTP_400_BAD_REQUEST
                )

            latitude, longitude = LocationValidator.validate_coordinates(lat_param, lon_param)

        except LocationValidationError as e:
            return LocationAPIErrorHandler.handle_validation_error(e)
        except (TypeError, ValueError) as e:
            return Response({"error": f"Invalid coordinate format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Parse and validate optional parameters
        try:
            radius_km = LocationValidator.validate_distance(request.query_params.get("radius_km", 50))
            min_price, max_price = LocationValidator.validate_price_range(
                request.query_params.get("min_price"), request.query_params.get("max_price")
            )
        except LocationValidationError as e:
            return LocationAPIErrorHandler.handle_validation_error(e)

        product_type = request.query_params.get("type", "marketplace")
        category = request.query_params.get("category")

        try:
            limit = int(request.query_params.get("limit", 40))
            # Validate limit parameter
            if limit > 100:
                limit = 100
            elif limit < 1:
                limit = 1
        except ValueError:
            limit = 40

        # Determine model class and base queryset
        model_class = self._get_model_class(product_type)

        # Get base queryset with appropriate filters
        if product_type == "user":
            base_queryset = model_class.objects.filter(is_sold=False, is_verified=True)
        else:
            base_queryset = model_class.objects.filter(is_available=True)

        # Apply category and price filters
        base_queryset = self._apply_product_filters(base_queryset, product_type, category, min_price, max_price)

        # Annotate with distance
        queryset = self._annotate_distance(base_queryset, latitude, longitude)

        # Filter by radius
        queryset = queryset.filter(distance_km__lte=radius_km)

        # Apply performance optimizations
        queryset = self._apply_performance_optimizations(queryset, product_type)

        # Order by distance and limit
        queryset = queryset.order_by("distance_km")[:limit]

        # Serialize results
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(queryset, many=True)

        # Add location metadata
        user_zone = self.geo_service.get_user_zone(request.user, latitude, longitude)

        return Response(
            {
                "count": len(queryset),
                "radius_km": radius_km,
                "user_location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "zone": user_zone.name if user_zone else None,
                    "zone_tier": user_zone.tier if user_zone else None,
                },
                "products": serializer.data,
            }
        )

    @extend_schema(
        summary="Get products in user's geographic zone",
        description="Find all products available in user's delivery zone",
        parameters=[
            OpenApiParameter("latitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("longitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("type", OpenApiTypes.STR, description="Product type: 'marketplace' or 'user'"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Maximum results (default: 40)"),
        ],
    )
    @action(detail=False, methods=["get"])
    def in_zone(self, request):
        """Get products available in user's geographic zone."""
        try:
            latitude = float(request.query_params.get("latitude"))
            longitude = float(request.query_params.get("longitude"))
        except (TypeError, ValueError):
            return Response({"error": "latitude and longitude are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Get user's geographic zone
        user_zone = self.geo_service.get_user_zone(request.user, latitude, longitude)
        if not user_zone:
            return Response({"message": "No delivery zone found for your location", "products": [], "count": 0})

        product_type = request.query_params.get("type", "marketplace")
        try:
            limit = int(request.query_params.get("limit", 40))
            if limit > 200:
                limit = 200
        except ValueError:
            limit = 40

        # Get products in zone
        model_class = self._get_model_class(product_type)
        products = self.filter_service.get_products_in_user_zone(model_class, user_zone, limit)

        # Apply performance optimizations
        products = self._apply_performance_optimizations(products, product_type)

        serializer_class = self.get_serializer_class()
        serializer = serializer_class(products, many=True)

        return Response(
            {
                "zone": {
                    "name": user_zone.name,
                    "tier": user_zone.tier,
                    "shipping_cost": float(user_zone.shipping_cost or 0),
                    "estimated_delivery_days": user_zone.estimated_delivery_days,
                },
                "count": len(products),
                "products": serializer.data,
            }
        )

    @extend_schema(
        summary="Calculate delivery information",
        description="Get delivery cost, time and availability for specific product",
        parameters=[
            OpenApiParameter("product_id", OpenApiTypes.INT, required=True),
            OpenApiParameter("product_type", OpenApiTypes.STR, required=True, description="'marketplace' or 'user'"),
            OpenApiParameter("delivery_latitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("delivery_longitude", OpenApiTypes.FLOAT, required=True),
        ],
    )
    @action(detail=False, methods=["get"])
    def delivery_info(self, request):
        """Calculate delivery information for a specific product."""
        try:
            product_id = int(request.query_params.get("product_id"))
            product_type = request.query_params.get("product_type", "marketplace")
            delivery_lat = float(request.query_params.get("delivery_latitude"))
            delivery_lon = float(request.query_params.get("delivery_longitude"))
        except (TypeError, ValueError):
            return Response(
                {"error": "product_id, product_type, delivery_latitude and delivery_longitude are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if product_type not in ["marketplace", "user"]:
            return Response(
                {"error": "product_type must be either 'marketplace' or 'user'"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get product
        try:
            if product_type == "user":
                product = MarketplaceUserProduct.objects.select_related("location", "user").get(id=product_id, is_sold=False)
            else:
                product = MarketplaceProduct.objects.select_related("product", "product__producer").get(
                    id=product_id, is_available=True
                )
        except MarketplaceProduct.DoesNotExist:
            return Response({"error": "Marketplace product not found"}, status=status.HTTP_404_NOT_FOUND)
        except MarketplaceUserProduct.DoesNotExist:
            return Response({"error": "User product not found"}, status=status.HTTP_404_NOT_FOUND)

        # Calculate delivery info
        try:
            delivery_info = self.filter_service.calculate_delivery_info(product, delivery_lat, delivery_lon)
        except Exception as e:
            return Response(
                {"error": f"Error calculating delivery info: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(delivery_info)

    @extend_schema(
        summary="Search products with advanced location filters",
        description="Advanced search with multiple location and product filters",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, description="Search query"),
            OpenApiParameter("latitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("longitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("max_distance", OpenApiTypes.FLOAT, description="Maximum distance in km"),
            OpenApiParameter("max_delivery_cost", OpenApiTypes.FLOAT, description="Maximum delivery cost"),
            OpenApiParameter("max_delivery_days", OpenApiTypes.INT, description="Maximum delivery days"),
            OpenApiParameter("categories", OpenApiTypes.STR, description="Comma-separated categories"),
            OpenApiParameter(
                "sort_by", OpenApiTypes.STR, description="Sort by: distance, price, rating (default: distance)"
            ),
            OpenApiParameter("type", OpenApiTypes.STR, description="Product type: 'marketplace' or 'user'"),
        ],
    )
    @action(detail=False, methods=["get"])
    def search(self, request):
        """Advanced location-based product search."""
        try:
            latitude = float(request.query_params.get("latitude"))
            longitude = float(request.query_params.get("longitude"))
        except (TypeError, ValueError):
            return Response({"error": "latitude and longitude are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Parse search parameters
        query = request.query_params.get("q", "").strip()
        max_distance = request.query_params.get("max_distance")
        max_delivery_cost = request.query_params.get("max_delivery_cost")
        max_delivery_days = request.query_params.get("max_delivery_days")
        categories_param = request.query_params.get("categories", "")
        categories = [c.strip() for c in categories_param.split(",") if c.strip()]
        sort_by = request.query_params.get("sort_by", "distance")
        product_type = request.query_params.get("type", "marketplace")

        # Convert numeric parameters
        max_distance = float(max_distance) if max_distance else None
        max_delivery_cost = float(max_delivery_cost) if max_delivery_cost else None
        max_delivery_days = int(max_delivery_days) if max_delivery_days else None

        # Determine model class and base queryset
        if product_type == "user":
            model_class = MarketplaceUserProduct
            queryset = MarketplaceUserProduct.objects.filter(is_sold=False, is_verified=True)
        else:
            model_class = MarketplaceProduct
            queryset = MarketplaceProduct.objects.filter(is_available=True)

        # Apply text search if provided
        if query:
            if product_type == "user":
                queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
            else:
                queryset = queryset.filter(
                    Q(product__name__icontains=query)
                    | Q(product__description__icontains=query)
                    | Q(search_tags__icontains=query)
                )

        # Apply category filter
        if categories:
            if product_type == "user":
                queryset = queryset.filter(category__in=categories)
            else:
                queryset = queryset.filter(product__category__in=categories)

        # Apply location filtering with distance annotation
        queryset = self._annotate_distance(queryset, latitude, longitude)

        # Apply distance filter
        if max_distance is not None:
            queryset = queryset.filter(distance_km__lte=max_distance)

        # Apply performance optimizations early
        queryset = self._apply_performance_optimizations(queryset, product_type)

        # Apply sorting
        if sort_by == "price":
            price_field = "listed_price" if product_type == "marketplace" else "price"
            queryset = queryset.order_by(price_field)
        elif sort_by == "rating":
            if product_type == "marketplace":
                # Order by rank_score (desc) then distance (asc)
                queryset = queryset.order_by("-rank_score", "distance_km")
            else:
                # User products don't have ratings, sort by distance
                queryset = queryset.order_by("distance_km")
        else:  # distance (default)
            queryset = queryset.order_by("distance_km")

        # Limit results for performance (get more than needed for post-filtering)
        queryset = queryset[:100]

        # Apply delivery filters (post-DB filtering for complex delivery logic)
        filtered_products = []
        for product in queryset:
            try:
                if max_delivery_cost is not None or max_delivery_days is not None:
                    delivery_info = self.filter_service.calculate_delivery_info(product, latitude, longitude)

                    if not delivery_info.get("available", False):
                        continue

                    if (
                        max_delivery_cost is not None
                        and delivery_info.get("estimated_cost", float("inf")) > max_delivery_cost
                    ):
                        continue

                    if (
                        max_delivery_days is not None
                        and delivery_info.get("estimated_days", float("inf")) > max_delivery_days
                    ):
                        continue

                filtered_products.append(product)
            except Exception:
                # Skip products that cause errors in delivery calculation
                continue

            if len(filtered_products) >= 50:  # Cap at 50 results
                break

        # Serialize results
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(filtered_products, many=True)

        return Response(
            {
                "query": query,
                "filters": {
                    "location": {"latitude": latitude, "longitude": longitude},
                    "max_distance_km": max_distance,
                    "max_delivery_cost": max_delivery_cost,
                    "max_delivery_days": max_delivery_days,
                    "categories": categories,
                    "sort_by": sort_by,
                },
                "count": len(filtered_products),
                "products": serializer.data,
            }
        )

    def _optimize_response_for_mobile(self, response_data: Dict, request) -> Dict:
        """Optimize API response based on mobile connectivity."""
        connectivity_mode = self.mobile_handler.detect_connectivity_mode(request)
        return self.mobile_handler.optimize_response_for_connectivity(response_data, connectivity_mode)

    @extend_schema(
        summary="Emergency-aware product search",
        description="Product search with emergency mode handling, cross-border support, and mobile optimization",
        parameters=[
            OpenApiParameter("latitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("longitude", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("radius_km", OpenApiTypes.FLOAT, description="Search radius in kilometers"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Product category"),
            OpenApiParameter("include_cross_border", OpenApiTypes.BOOL, description="Include cross-border deliveries"),
        ],
    )
    @action(detail=False, methods=["get"])
    def emergency_search(self, request):
        """Emergency-optimized product search with comprehensive edge case handling."""
        try:
            latitude = float(request.query_params.get("latitude"))
            longitude = float(request.query_params.get("longitude"))

            # Validate coordinates with all edge cases
            validation_result = self._validate_coordinates_comprehensive(latitude, longitude, request)
            if not validation_result["valid"]:
                return Response(validation_result, status=status.HTTP_400_BAD_REQUEST)

            # Use anonymized coordinates if GDPR requires it
            if "anonymized_coordinates" in validation_result:
                latitude, longitude = validation_result["anonymized_coordinates"]

            radius_km = float(request.query_params.get("radius_km", 10))  # Smaller radius for emergency
            category = request.query_params.get("category")
            include_cross_border = request.query_params.get("include_cross_border", "false").lower() == "true"

            # Get emergency mode
            emergency_mode = self.emergency_manager.get_current_emergency_mode()

            # Apply emergency-specific product filtering
            model_class = self._get_model_class("marketplace")
            queryset = model_class.objects.filter(is_available=True)

            # Emergency mode restrictions
            if emergency_mode != EmergencyMode.NORMAL:
                queryset = self.emergency_manager.apply_emergency_restrictions(queryset, emergency_mode, latitude, longitude)

            # Location-based filtering with smaller radius in emergency
            queryset = self.filter_service.filter_products_by_location(queryset, latitude, longitude, min(radius_km, 10))

            # Limit to essential products in emergency
            queryset = queryset[:20]

            enhanced_products = []
            for product in queryset:
                delivery_info = self._calculate_comprehensive_delivery_info(product, latitude, longitude, request)

                # In emergency mode, prioritize local deliveries
                if emergency_mode != EmergencyMode.NORMAL:
                    if delivery_info.get("cross_border", {}).get("required", False) and not include_cross_border:
                        continue

                product_data = {
                    "id": product.id,
                    "name": product.product.name,
                    "delivery_info": delivery_info,
                    "distance_km": delivery_info.get("distance_km"),
                    "price": float(product.listed_price),
                    "emergency_priority": delivery_info.get("emergency_mode") != "normal",
                }
                enhanced_products.append(product_data)

            # Sort by emergency priority, then distance
            enhanced_products.sort(key=lambda x: (not x["emergency_priority"], x["distance_km"] or float("inf")))

            response_data = {
                "products": enhanced_products,
                "total_count": len(enhanced_products),
                "emergency_mode": emergency_mode.value,
                "search_metadata": {
                    "user_location": {"latitude": latitude, "longitude": longitude},
                    "radius_km": radius_km,
                    "validation_warnings": validation_result.get("warnings", []),
                },
            }

            # Optimize for mobile connectivity
            response_data = self._optimize_response_for_mobile(response_data, request)

            return Response(response_data)

        except ValueError as e:
            return Response({"error": f"Invalid parameters: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Emergency search error: {e}")
            return Response({"error": "Service unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
