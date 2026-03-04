import logging
from decimal import Decimal, InvalidOperation
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Union

from django.contrib.gis.geos import GEOSException, Point
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError, models, transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

# Optional imports for fallback functionality
try:
    from geopy.distance import geodesic

    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    geodesic = None

from geo.models import GeographicZone
from geo.services import GeoLocationService, GeoProductFilterService

logger = logging.getLogger(__name__)

# Import advanced edge case handlers
try:
    from .geographic_edge_cases import (
        DistanceCalculationHandler,
        GeographicEdgeCaseHandler,
        GeographicRegion,
    )

    # from .circuit_breakers import CircuitBreaker
    # from .graceful_degradation import GracefulDegradationManager
    ADVANCED_HANDLERS_AVAILABLE = True
except ImportError:
    ADVANCED_HANDLERS_AVAILABLE = False
    logger.warning("Advanced edge case handlers not available")


class LocationValidationError(Exception):
    """Custom exception for location validation errors."""

    pass


class GeoServiceError(Exception):
    """Custom exception for geographic service errors."""

    pass


class LocationValidator:
    """
    Comprehensive location data validation with edge case handling.
    """

    @staticmethod
    def validate_coordinates(
        latitude: Union[str, float, int, None], longitude: Union[str, float, int, None]
    ) -> Tuple[float, float]:
        """
        Validate and normalize coordinates with comprehensive error handling.

        Args:
            latitude: Latitude value (any numeric type or string)
            longitude: Longitude value (any numeric type or string)

        Returns:
            Tuple of validated (lat, lon) as floats

        Raises:
            LocationValidationError: If coordinates are invalid
        """
        try:
            # Handle None values
            if latitude is None or longitude is None:
                raise LocationValidationError("Coordinates cannot be None")

            # Handle empty strings
            if isinstance(latitude, str) and not latitude.strip():
                raise LocationValidationError("Latitude cannot be empty string")
            if isinstance(longitude, str) and not longitude.strip():
                raise LocationValidationError("Longitude cannot be empty string")

            # Convert to float with proper error handling
            try:
                lat = float(latitude)
                lon = float(longitude)
            except (ValueError, TypeError) as e:
                raise LocationValidationError(f"Invalid coordinate format: {str(e)}")

            # Check for NaN or infinite values
            if lat != lat or lon != lon:  # NaN check
                raise LocationValidationError("Coordinates cannot be NaN")
            if abs(lat) == float("inf") or abs(lon) == float("inf"):
                raise LocationValidationError("Coordinates cannot be infinite")

            # Validate coordinate ranges
            if not (-90 <= lat <= 90):
                raise LocationValidationError(f"Latitude {lat} is out of valid range (-90 to 90)")

            if not (-180 <= lon <= 180):
                raise LocationValidationError(f"Longitude {lon} is out of valid range (-180 to 180)")

            # Check for special invalid values
            if lat == 0.0 and lon == 0.0:
                logger.warning("Received null island coordinates (0,0) - this might be invalid data")

            # Validate precision (prevent overly precise coordinates that might be fake)
            lat_str = str(lat)
            lon_str = str(lon)
            lat_precision = len(lat_str.split(".")[-1]) if "." in lat_str else 0
            lon_precision = len(lon_str.split(".")[-1]) if "." in lon_str else 0

            if lat_precision > 8 or lon_precision > 8:
                logger.warning(f"Unusually high precision coordinates: {lat}, {lon}")

            return lat, lon

        except LocationValidationError:
            raise
        except Exception as e:
            raise LocationValidationError(f"Unexpected error validating coordinates: {str(e)}")

    @staticmethod
    def validate_distance(distance_km: Union[str, float, int, None]) -> Optional[float]:
        """Validate distance parameters."""
        if distance_km is None:
            return None

        try:
            # Handle string input
            if isinstance(distance_km, str):
                distance_km = distance_km.strip()
                if not distance_km:
                    return None

            dist = float(distance_km)

            # Check for invalid values
            if dist != dist:  # NaN check
                raise LocationValidationError("Distance cannot be NaN")
            if abs(dist) == float("inf"):
                raise LocationValidationError("Distance cannot be infinite")
            if dist < 0:
                raise LocationValidationError("Distance cannot be negative")
            if dist > 1000:  # 1000km max reasonable distance
                raise LocationValidationError("Distance exceeds maximum allowed (1000km)")

            return dist
        except (ValueError, TypeError):
            raise LocationValidationError(f"Invalid distance format: {distance_km}")

    @staticmethod
    def validate_price_range(
        min_price: Union[str, float, int, None], max_price: Union[str, float, int, None]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Validate price range parameters."""
        min_val = None
        max_val = None

        if min_price is not None:
            try:
                # Handle string input
                if isinstance(min_price, str):
                    min_price = min_price.strip()
                    if not min_price:
                        min_val = None
                    else:
                        min_val = float(min_price)
                else:
                    min_val = float(min_price)

                if min_val is not None and min_val < 0:
                    raise LocationValidationError("Minimum price cannot be negative")
            except (ValueError, TypeError):
                raise LocationValidationError(f"Invalid minimum price format: {min_price}")

        if max_price is not None:
            try:
                # Handle string input
                if isinstance(max_price, str):
                    max_price = max_price.strip()
                    if not max_price:
                        max_val = None
                    else:
                        max_val = float(max_price)
                else:
                    max_val = float(max_price)

                if max_val is not None and max_val < 0:
                    raise LocationValidationError("Maximum price cannot be negative")
            except (ValueError, TypeError):
                raise LocationValidationError(f"Invalid maximum price format: {max_price}")

        if min_val is not None and max_val is not None and min_val > max_val:
            raise LocationValidationError("Minimum price cannot be greater than maximum price")

        return min_val, max_val


class GeoServiceErrorHandler:
    """Handle errors and fallbacks for geographic services."""

    def __init__(self):
        self.geo_service = GeoLocationService()
        self.filter_service = GeoProductFilterService()
        self.fallback_cache_timeout = 3600  # 1 hour

    def safe_get_user_zone(self, user, latitude: float, longitude: float) -> Optional[GeographicZone]:
        """Safely get user zone with error handling and caching."""
        cache_key = f"user_zone:{latitude}:{longitude}"

        try:
            # Try cache first
            cached_zone = cache.get(cache_key)
            if cached_zone is not None:
                # Handle cached 'NONE' sentinel value
                if cached_zone == "NONE":
                    return None
                return cached_zone

            # Try to get zone from service
            zone = self.geo_service.get_user_zone(user, latitude, longitude)

            # Cache result (use 'NONE' sentinel for None values)
            cache.set(cache_key, zone if zone else "NONE", self.fallback_cache_timeout)
            return zone

        except Exception as e:
            logger.error(f"Error getting user zone for {latitude},{longitude}: {str(e)}")

            # Try to get from longer-term cache as fallback
            fallback_key = f"user_zone_fallback:{latitude}:{longitude}"
            fallback_zone = cache.get(fallback_key)
            if fallback_zone is not None:
                logger.info(f"Using fallback zone data for {latitude},{longitude}")
                return fallback_zone if fallback_zone != "NONE" else None

            return None

    def safe_calculate_delivery_info(self, product, latitude: float, longitude: float) -> Dict[str, Any]:
        """Safely calculate delivery info with comprehensive error handling."""
        try:
            # Validate inputs
            if not product:
                return self._get_error_delivery_info("Product not provided")

            validator = LocationValidator()
            lat, lon = validator.validate_coordinates(latitude, longitude)

            # Try to calculate delivery info
            delivery_info = self.filter_service.calculate_delivery_info(product, lat, lon)

            # Validate returned data
            if not isinstance(delivery_info, dict):
                raise GeoServiceError("Invalid delivery info format returned")

            # Ensure required keys exist with defaults
            required_keys = ["available", "distance_km", "estimated_cost", "estimated_days"]
            for key in required_keys:
                if key not in delivery_info:
                    logger.warning(f"Missing key {key} in delivery info, adding default")
                    if key == "available":
                        delivery_info[key] = True
                    elif key == "distance_km":
                        delivery_info[key] = None
                    elif key == "estimated_cost":
                        delivery_info[key] = None
                    elif key == "estimated_days":
                        delivery_info[key] = None

            return delivery_info

        except LocationValidationError as e:
            logger.warning(f"Location validation error: {str(e)}")
            return self._get_error_delivery_info(f"Invalid location: {str(e)}")

        except GeoServiceError as e:
            logger.error(f"Geo service error: {str(e)}")
            return self._get_fallback_delivery_info(product, latitude, longitude)

        except Exception as e:
            logger.error(f"Unexpected error calculating delivery info: {str(e)}")
            return self._get_fallback_delivery_info(product, latitude, longitude)

    def _get_error_delivery_info(self, reason: str) -> Dict[str, Any]:
        """Return error delivery info structure."""
        return {
            "available": False,
            "reason": reason,
            "distance_km": None,
            "estimated_cost": None,
            "estimated_days": None,
            "zone_name": None,
        }

    def _get_fallback_delivery_info(self, product, latitude: float, longitude: float) -> Dict[str, Any]:
        """Provide fallback delivery info when service fails."""
        try:
            # Try simple distance calculation as fallback
            seller_coords = None

            # Extract seller coordinates based on product type
            if hasattr(product, "product") and product.product and hasattr(product.product, "producer"):
                producer = product.product.producer
                if producer and hasattr(producer, "location") and producer.location:
                    seller_coords = (producer.location.y, producer.location.x)
            elif hasattr(product, "location") and product.location:
                if hasattr(product.location, "location") and product.location.location:
                    seller_coords = (product.location.location.y, product.location.location.x)
            elif hasattr(product, "seller_location") and product.seller_location:
                seller_coords = (product.seller_location.y, product.seller_location.x)

            # Calculate distance if we have coordinates and geopy is available
            if seller_coords and GEOPY_AVAILABLE and geodesic:
                try:
                    buyer_coords = (latitude, longitude)
                    distance_km = geodesic(seller_coords, buyer_coords).kilometers

                    # Basic cost estimation based on distance
                    if distance_km <= 5:
                        cost, days = 0.0, 1
                    elif distance_km <= 25:
                        cost, days = 100.0, 2
                    elif distance_km <= 50:
                        cost, days = 200.0, 3
                    elif distance_km <= 100:
                        cost, days = 300.0, 4
                    else:
                        cost, days = 500.0, 5

                    return {
                        "available": True,
                        "reason": "Fallback calculation (service unavailable)",
                        "distance_km": round(distance_km, 2),
                        "estimated_cost": cost,
                        "estimated_days": days,
                        "zone_name": "Unknown",
                    }
                except Exception as e:
                    logger.warning(f"Error in geodesic calculation: {str(e)}")

            # Last resort fallback
            return {
                "available": True,
                "reason": "Service unavailable - using default estimates",
                "distance_km": None,
                "estimated_cost": 150.0,  # Default cost
                "estimated_days": 3,  # Default days
                "zone_name": "Unknown",
            }

        except Exception as e:
            logger.error(f"Error in fallback delivery calculation: {str(e)}")
            return self._get_error_delivery_info("Delivery calculation unavailable")


class LocationAPIErrorHandler:
    """Handle API-level errors for location-based endpoints."""

    ERROR_CODES = {
        "INVALID_COORDINATES": "INVALID_COORDINATES",
        "INVALID_PRICE_RANGE": "INVALID_PRICE_RANGE",
        "INVALID_DISTANCE": "INVALID_DISTANCE",
        "VALIDATION_ERROR": "VALIDATION_ERROR",
        "SERVICE_ERROR": "SERVICE_ERROR",
        "NOT_FOUND": "NOT_FOUND",
        "RATE_LIMIT_EXCEEDED": "RATE_LIMIT_EXCEEDED",
    }

    @staticmethod
    def handle_validation_error(error: Union[LocationValidationError, ValidationError, DRFValidationError]) -> Response:
        """Handle validation errors with appropriate HTTP responses."""
        error_message = str(error)
        error_lower = error_message.lower()

        if "coordinate" in error_lower:
            return Response(
                {
                    "error": "Invalid coordinates",
                    "message": error_message,
                    "code": LocationAPIErrorHandler.ERROR_CODES["INVALID_COORDINATES"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif "price" in error_lower:
            return Response(
                {
                    "error": "Invalid price range",
                    "message": error_message,
                    "code": LocationAPIErrorHandler.ERROR_CODES["INVALID_PRICE_RANGE"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif "distance" in error_lower:
            return Response(
                {
                    "error": "Invalid distance",
                    "message": error_message,
                    "code": LocationAPIErrorHandler.ERROR_CODES["INVALID_DISTANCE"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            return Response(
                {
                    "error": "Validation error",
                    "message": error_message,
                    "code": LocationAPIErrorHandler.ERROR_CODES["VALIDATION_ERROR"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @staticmethod
    def handle_service_error(error: Exception) -> Response:
        """Handle service-level errors."""
        logger.error(f"Service error in location API: {str(error)}", exc_info=True)

        return Response(
            {
                "error": "Service temporarily unavailable",
                "message": "Location services are currently experiencing issues. Please try again later.",
                "code": LocationAPIErrorHandler.ERROR_CODES["SERVICE_ERROR"],
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def handle_not_found_error(resource: str = "resource") -> Response:
        """Handle not found errors."""
        return Response(
            {
                "error": f"{resource.title()} not found",
                "message": f"The requested {resource} could not be found.",
                "code": LocationAPIErrorHandler.ERROR_CODES["NOT_FOUND"],
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    @staticmethod
    def handle_rate_limit_error() -> Response:
        """Handle rate limiting errors."""
        return Response(
            {
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please wait before trying again.",
                "code": LocationAPIErrorHandler.ERROR_CODES["RATE_LIMIT_EXCEEDED"],
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class LocationDataIntegrityChecker:
    """Check and ensure data integrity for location-based operations."""

    @staticmethod
    def check_product_location_integrity(queryset: models.QuerySet) -> Dict[str, Any]:
        """Check location data integrity for products."""
        stats = {
            "total_products": queryset.count(),
            "products_with_location": 0,
            "products_without_location": 0,
            "invalid_locations": [],
            "warnings": [],
        }

        for product in queryset.iterator():  # Use iterator for memory efficiency
            has_valid_location = False

            try:
                # Check MarketplaceProduct (producer location)
                if hasattr(product, "product") and product.product and hasattr(product.product, "producer"):
                    producer = product.product.producer
                    if producer and hasattr(producer, "location") and producer.location:
                        # Validate producer location
                        try:
                            lat, lon = producer.location.y, producer.location.x
                            LocationValidator.validate_coordinates(lat, lon)
                            has_valid_location = True
                        except LocationValidationError as e:
                            stats["invalid_locations"].append(
                                {"product_id": product.id, "type": "producer_location", "error": str(e)}
                            )

                # Check MarketplaceUserProduct (city location)
                elif hasattr(product, "location") and product.location:
                    if hasattr(product.location, "location") and product.location.location:
                        try:
                            lat, lon = product.location.location.y, product.location.location.x
                            LocationValidator.validate_coordinates(lat, lon)
                            has_valid_location = True
                        except LocationValidationError as e:
                            stats["invalid_locations"].append(
                                {"product_id": product.id, "type": "city_location", "error": str(e)}
                            )
                    else:
                        stats["warnings"].append(f"Product {product.id} has city but no coordinates")

                # Check direct location attribute
                elif hasattr(product, "location_point") and product.location_point:
                    try:
                        lat, lon = product.location_point.y, product.location_point.x
                        LocationValidator.validate_coordinates(lat, lon)
                        has_valid_location = True
                    except LocationValidationError as e:
                        stats["invalid_locations"].append(
                            {"product_id": product.id, "type": "direct_location", "error": str(e)}
                        )

                if has_valid_location:
                    stats["products_with_location"] += 1
                else:
                    stats["products_without_location"] += 1

            except Exception as e:
                logger.error(f"Error checking product {product.id} location integrity: {str(e)}")
                stats["warnings"].append(f"Error checking product {product.id}: {str(e)}")

        return stats

    @staticmethod
    def repair_location_data() -> Dict[str, int]:
        """Attempt to repair common location data issues."""
        # Import models here to avoid circular imports
        from django.apps import apps

        repair_stats = {"producers_fixed": 0, "cities_fixed": 0, "errors": 0}

        try:
            # Get models dynamically to avoid circular imports
            Producer = apps.get_model("producer", "Producer")
            City = apps.get_model("geo", "City")

            with transaction.atomic():
                # Fix producers with invalid locations
                if Producer:
                    for producer in Producer.objects.filter(location__isnull=False).iterator():
                        try:
                            if producer.location:
                                lat, lon = producer.location.y, producer.location.x
                                LocationValidator.validate_coordinates(lat, lon)
                        except (LocationValidationError, Exception) as e:
                            logger.warning(f"Invalid producer location for {producer.id}: {e}")
                            # Could implement location lookup by address here
                            repair_stats["errors"] += 1

                # Fix cities with invalid locations
                if City:
                    for city in City.objects.filter(location__isnull=False).iterator():
                        try:
                            if city.location:
                                lat, lon = city.location.y, city.location.x
                                LocationValidator.validate_coordinates(lat, lon)
                        except (LocationValidationError, Exception) as e:
                            logger.warning(f"Invalid city location for {city.id}: {e}")
                            repair_stats["errors"] += 1

        except LookupError as e:
            logger.error(f"Could not find required models: {str(e)}")
            repair_stats["errors"] += 1
        except Exception as e:
            logger.error(f"Error during location data repair: {str(e)}")
            repair_stats["errors"] += 1

        return repair_stats


# Utility decorators for error handling
def handle_location_errors(func):
    """Decorator to handle location-related errors in API views."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except LocationValidationError as e:
            return LocationAPIErrorHandler.handle_validation_error(e)
        except ValidationError as e:
            return LocationAPIErrorHandler.handle_validation_error(e)
        except DatabaseError as e:
            logger.error(f"Database error in location API: {str(e)}", exc_info=True)
            return LocationAPIErrorHandler.handle_service_error(e)
        except Exception as e:
            logger.error(f"Unexpected error in location API: {str(e)}", exc_info=True)
            return LocationAPIErrorHandler.handle_service_error(e)

    return wrapper


def rate_limit_location_calls(max_calls: int = 100, time_window: int = 3600):
    """Decorator to rate limit expensive location operations."""

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                user_key = f"location_rate_limit:{request.user.id}"
            else:
                # Use IP for anonymous users
                ip_address = request.META.get("REMOTE_ADDR", "unknown")
                # Handle proxy IPs
                if "HTTP_X_FORWARDED_FOR" in request.META:
                    ip_address = request.META["HTTP_X_FORWARDED_FOR"].split(",")[0].strip()
                user_key = f"location_rate_limit:ip:{ip_address}"

            # Get current count
            current_calls = cache.get(user_key, 0)

            # Check if limit exceeded
            if current_calls >= max_calls:
                logger.warning(f"Rate limit exceeded for {user_key}")
                return LocationAPIErrorHandler.handle_rate_limit_error()

            # Increment counter (using cache.incr for atomic increment if possible)
            try:
                cache.incr(user_key)
            except ValueError:
                # Key doesn't exist or isn't an integer
                cache.set(user_key, current_calls + 1, time_window)

            return func(request, *args, **kwargs)

        return wrapper

    return decorator
