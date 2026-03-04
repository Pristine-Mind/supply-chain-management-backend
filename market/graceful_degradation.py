import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class ServiceHealthStatus(Enum):
    """Service health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DOWN = "down"


class DegradationLevel(Enum):
    """Progressive degradation levels."""

    NONE = 0  # Full functionality
    MINOR = 1  # Reduce some non-critical features
    MODERATE = 2  # Disable advanced features, basic functionality only
    MAJOR = 3  # Emergency mode, minimal functionality
    CRITICAL = 4  # Read-only mode or static responses


@dataclass
class ServiceStatus:
    """Service status tracking."""

    service_name: str
    health: ServiceHealthStatus
    degradation_level: DegradationLevel
    last_check: datetime = field(default_factory=timezone.now)
    failure_count: int = 0
    recovery_time: Optional[datetime] = None
    message: str = ""


class GracefulDegradationManager:
    """
    Manages progressive degradation of location-based marketplace services.
    """

    def __init__(self):
        self.service_statuses = {}
        self.degradation_strategies = {}
        self.fallback_data = {}
        self.status_lock = threading.Lock()
        self.monitoring_active = False

        # Configuration
        self.health_check_interval = 30  # seconds
        self.failure_threshold = 3
        self.recovery_threshold = 2
        self.degradation_timeout = 300  # 5 minutes before auto-recovery attempt

        # Initialize default strategies
        self._setup_default_strategies()

    def register_service(
        self, service_name: str, health_check_fn: Callable[[], bool], degradation_strategy: Optional[Dict] = None
    ):
        """
        Register a service for degradation management.

        Args:
            service_name: Unique service identifier
            health_check_fn: Function that returns True if service is healthy
            degradation_strategy: Custom degradation configuration
        """
        with self.status_lock:
            self.service_statuses[service_name] = ServiceStatus(
                service_name=service_name, health=ServiceHealthStatus.HEALTHY, degradation_level=DegradationLevel.NONE
            )

        if degradation_strategy:
            self.degradation_strategies[service_name] = degradation_strategy

        # Store health check function
        setattr(self, f"_{service_name}_health_check", health_check_fn)

        logger.info(f"Registered service for degradation management: {service_name}")

    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """Get current status of a service."""
        with self.status_lock:
            return self.service_statuses.get(service_name)

    def get_system_degradation_level(self) -> DegradationLevel:
        """Get overall system degradation level."""
        with self.status_lock:
            levels = [status.degradation_level.value for status in self.service_statuses.values()]

        if not levels:
            return DegradationLevel.NONE

        # Return the highest degradation level
        return DegradationLevel(max(levels))

    def force_service_degradation(self, service_name: str, level: DegradationLevel, reason: str = "Manual override"):
        """Manually force a service into degraded state."""
        with self.status_lock:
            if service_name in self.service_statuses:
                status_obj = self.service_statuses[service_name]
                status_obj.degradation_level = level
                status_obj.health = (
                    ServiceHealthStatus.DEGRADED if level > DegradationLevel.NONE else ServiceHealthStatus.HEALTHY
                )
                status_obj.message = reason
                status_obj.last_check = timezone.now()

        logger.warning(f"Forced degradation for {service_name}: {level.name} - {reason}")

    def check_service_health(self, service_name: str) -> bool:
        """Check health of a specific service."""
        health_check_fn = getattr(self, f"_{service_name}_health_check", None)
        if not health_check_fn:
            return True  # Assume healthy if no check function

        try:
            return health_check_fn()
        except Exception as e:
            logger.error(f"Health check failed for {service_name}: {e}")
            return False

    def update_service_status(self, service_name: str):
        """Update service status based on health check."""
        is_healthy = self.check_service_health(service_name)

        with self.status_lock:
            if service_name not in self.service_statuses:
                return

            status_obj = self.service_statuses[service_name]
            status_obj.last_check = timezone.now()

            if is_healthy:
                # Service is healthy
                if status_obj.health != ServiceHealthStatus.HEALTHY:
                    # Recovery
                    status_obj.failure_count = max(0, status_obj.failure_count - 1)

                    if status_obj.failure_count <= self.recovery_threshold:
                        self._recover_service(status_obj)

            else:
                # Service is unhealthy
                status_obj.failure_count += 1

                if status_obj.failure_count >= self.failure_threshold:
                    self._degrade_service(status_obj)

    def _recover_service(self, status_obj: ServiceStatus):
        """Recover a service from degraded state."""
        old_level = status_obj.degradation_level

        status_obj.health = ServiceHealthStatus.HEALTHY
        status_obj.degradation_level = DegradationLevel.NONE
        status_obj.recovery_time = timezone.now()
        status_obj.failure_count = 0
        status_obj.message = "Service recovered"

        logger.info(f"Service {status_obj.service_name} recovered from {old_level.name}")

    def _degrade_service(self, status_obj: ServiceStatus):
        """Degrade a service based on failure count."""
        # Progressive degradation based on failure count
        if status_obj.failure_count >= 10:
            new_level = DegradationLevel.CRITICAL
            new_health = ServiceHealthStatus.DOWN
        elif status_obj.failure_count >= 7:
            new_level = DegradationLevel.MAJOR
            new_health = ServiceHealthStatus.CRITICAL
        elif status_obj.failure_count >= 5:
            new_level = DegradationLevel.MODERATE
            new_health = ServiceHealthStatus.CRITICAL
        else:
            new_level = DegradationLevel.MINOR
            new_health = ServiceHealthStatus.DEGRADED

        old_level = status_obj.degradation_level
        status_obj.degradation_level = new_level
        status_obj.health = new_health
        status_obj.message = f"Service degraded due to {status_obj.failure_count} failures"

        logger.warning(f"Service {status_obj.service_name} degraded from {old_level.name} to {new_level.name}")

    def _setup_default_strategies(self):
        """Setup default degradation strategies."""
        self.degradation_strategies = {
            "database": {
                "minor": {"read_only": False, "cache_only_reads": True},
                "moderate": {"read_only": True, "use_cached_data": True},
                "major": {"read_only": True, "static_responses": True},
                "critical": {"offline_mode": True},
            },
            "cache": {
                "minor": {"reduced_ttl": True, "skip_complex_keys": True},
                "moderate": {"memory_cache_only": True},
                "major": {"disable_caching": True},
                "critical": {"disable_caching": True},
            },
            "geocoding": {
                "minor": {"use_cached_geocoding": True, "reduced_precision": True},
                "moderate": {"static_zones_only": True},
                "major": {"approximate_distances": True},
                "critical": {"disable_geocoding": True},
            },
            "delivery_calculation": {
                "minor": {"use_cached_routes": True, "approximate_costs": True},
                "moderate": {"flat_delivery_rates": True},
                "major": {"standard_rates_only": True},
                "critical": {"no_delivery_calculation": True},
            },
        }


class LocationServiceDegradation:
    """
    Specific degradation strategies for location-based services.
    """

    def __init__(self, degradation_manager: GracefulDegradationManager):
        self.manager = degradation_manager
        self.static_data_cache = {}

    def get_products_with_degradation(self, user_location: Dict, radius_km: float, filters: Dict = None) -> Dict:
        """
        Get products with appropriate degradation strategies.
        """
        degradation_level = self.manager.get_system_degradation_level()

        if degradation_level == DegradationLevel.NONE:
            return self._get_full_products(user_location, radius_km, filters)
        elif degradation_level == DegradationLevel.MINOR:
            return self._get_products_minor_degradation(user_location, radius_km, filters)
        elif degradation_level == DegradationLevel.MODERATE:
            return self._get_products_moderate_degradation(user_location, radius_km, filters)
        elif degradation_level == DegradationLevel.MAJOR:
            return self._get_products_major_degradation(user_location, radius_km, filters)
        else:  # CRITICAL
            return self._get_products_critical_degradation(user_location, radius_km, filters)

    def _get_full_products(self, user_location: Dict, radius_km: float, filters: Dict) -> Dict:
        """Full functionality product retrieval."""
        try:
            from geo.services import GeoProductFilterService

            filter_service = GeoProductFilterService()

            products = filter_service.get_products_within_radius(
                user_location["latitude"], user_location["longitude"], radius_km, filters or {}
            )

            return {
                "products": products,
                "degradation_level": "none",
                "total_count": len(products),
                "has_accurate_distances": True,
                "has_delivery_costs": True,
            }

        except Exception as e:
            logger.error(f"Full product retrieval failed: {e}")
            # Fallback to degraded mode
            return self._get_products_minor_degradation(user_location, radius_km, filters)

    def _get_products_minor_degradation(self, user_location: Dict, radius_km: float, filters: Dict) -> Dict:
        """Minor degradation - use cached data and approximate distances."""
        try:
            # Use cached product data with approximate distances
            cache_key = f"products_approx:{user_location['latitude']:.2f}:{user_location['longitude']:.2f}:{radius_km}"
            cached_products = cache.get(cache_key)

            if cached_products:
                return {
                    "products": cached_products,
                    "degradation_level": "minor",
                    "total_count": len(cached_products),
                    "has_accurate_distances": False,
                    "has_delivery_costs": True,
                    "message": "Using cached data with approximate distances",
                }

            # Fallback to database query with reduced accuracy
            from django.contrib.gis.geos import Point
            from django.contrib.gis.measure import D

            from market.models import MarketplaceProduct

            user_point = Point(user_location["longitude"], user_location["latitude"], srid=4326)

            products = MarketplaceProduct.objects.filter(
                location__distance_lte=(user_point, D(km=radius_km))
            ).select_related("producer")[
                :50
            ]  # Limit results

            product_list = []
            for product in products:
                # Approximate distance calculation
                distance_km = user_point.distance(product.location).km if product.location else radius_km

                product_list.append(
                    {
                        "id": product.id,
                        "name": product.name,
                        "producer_name": product.producer.name if product.producer else "Unknown",
                        "distance_km": round(distance_km, 1),
                        "price": float(product.price) if hasattr(product, "price") else None,
                        "approximate_distance": True,
                    }
                )

            # Cache the result
            cache.set(cache_key, product_list, 300)  # 5 minute cache

            return {
                "products": product_list,
                "degradation_level": "minor",
                "total_count": len(product_list),
                "has_accurate_distances": False,
                "has_delivery_costs": True,
                "message": "Using approximate distances due to service degradation",
            }

        except Exception as e:
            logger.error(f"Minor degradation failed: {e}")
            return self._get_products_moderate_degradation(user_location, radius_km, filters)

    def _get_products_moderate_degradation(self, user_location: Dict, radius_km: float, filters: Dict) -> Dict:
        """Moderate degradation - static zones and flat delivery rates."""
        try:
            # Use predefined geographic zones
            zone = self._get_static_zone(user_location)

            if zone:
                products = self._get_products_for_zone(zone, filters)

                return {
                    "products": products,
                    "degradation_level": "moderate",
                    "total_count": len(products),
                    "has_accurate_distances": False,
                    "has_delivery_costs": False,
                    "zone": zone,
                    "message": "Using static zone data with flat delivery rates",
                }

            # Fallback to major degradation
            return self._get_products_major_degradation(user_location, radius_km, filters)

        except Exception as e:
            logger.error(f"Moderate degradation failed: {e}")
            return self._get_products_major_degradation(user_location, radius_km, filters)

    def _get_products_major_degradation(self, user_location: Dict, radius_km: float, filters: Dict) -> Dict:
        """Major degradation - emergency mode with minimal data."""
        try:
            # Return cached emergency data
            emergency_key = f"emergency_products_{radius_km}"
            emergency_products = cache.get(emergency_key)

            if not emergency_products:
                # Generate minimal product list from available data
                emergency_products = self._generate_emergency_product_list(user_location, radius_km)
                cache.set(emergency_key, emergency_products, 3600)  # 1 hour cache

            return {
                "products": emergency_products,
                "degradation_level": "major",
                "total_count": len(emergency_products),
                "has_accurate_distances": False,
                "has_delivery_costs": False,
                "message": "Emergency mode: Limited product data available",
            }

        except Exception as e:
            logger.error(f"Major degradation failed: {e}")
            return self._get_products_critical_degradation(user_location, radius_km, filters)

    def _get_products_critical_degradation(self, user_location: Dict, radius_km: float, filters: Dict) -> Dict:
        """Critical degradation - static message only."""
        return {
            "products": [],
            "degradation_level": "critical",
            "total_count": 0,
            "has_accurate_distances": False,
            "has_delivery_costs": False,
            "message": "Service temporarily unavailable. Please try again later.",
            "retry_after": 300,  # 5 minutes
        }

    def _get_static_zone(self, location: Dict) -> Optional[str]:
        """Get static geographic zone for location."""
        # Define static zones for Nepal
        zones = {
            "kathmandu_valley": {
                "bounds": {"lat_min": 27.6, "lat_max": 27.8, "lon_min": 85.2, "lon_max": 85.4},
                "name": "Kathmandu Valley",
            },
            "pokhara": {"bounds": {"lat_min": 28.1, "lat_max": 28.3, "lon_min": 83.9, "lon_max": 84.1}, "name": "Pokhara"},
            "chitwan": {"bounds": {"lat_min": 27.4, "lat_max": 27.8, "lon_min": 84.2, "lon_max": 84.6}, "name": "Chitwan"},
        }

        lat = location["latitude"]
        lon = location["longitude"]

        for zone_id, zone_info in zones.items():
            bounds = zone_info["bounds"]
            if bounds["lat_min"] <= lat <= bounds["lat_max"] and bounds["lon_min"] <= lon <= bounds["lon_max"]:
                return zone_id

        return "general"  # Default zone

    def _get_products_for_zone(self, zone: str, filters: Dict) -> List[Dict]:
        """Get products for a static zone."""
        cache_key = f"zone_products_{zone}"
        products = cache.get(cache_key)

        if products:
            return products

        # Generate static product list for zone
        static_products = {
            "kathmandu_valley": [
                {"id": "static_1", "name": "Fresh Vegetables", "category": "agriculture", "zone": zone},
                {"id": "static_2", "name": "Dairy Products", "category": "dairy", "zone": zone},
                {"id": "static_3", "name": "Grains & Cereals", "category": "grains", "zone": zone},
            ],
            "pokhara": [
                {"id": "static_4", "name": "Mountain Vegetables", "category": "agriculture", "zone": zone},
                {"id": "static_5", "name": "Local Honey", "category": "honey", "zone": zone},
            ],
            "chitwan": [
                {"id": "static_6", "name": "Rice Products", "category": "grains", "zone": zone},
                {"id": "static_7", "name": "Seasonal Fruits", "category": "fruits", "zone": zone},
            ],
            "general": [
                {"id": "static_8", "name": "General Products", "category": "mixed", "zone": zone},
            ],
        }

        products = static_products.get(zone, static_products["general"])
        cache.set(cache_key, products, 1800)  # 30 minute cache

        return products

    def _generate_emergency_product_list(self, location: Dict, radius_km: float) -> List[Dict]:
        """Generate emergency product list."""
        return [
            {
                "id": "emergency_1",
                "name": "Essential Products Available",
                "category": "emergency",
                "message": "Contact local producers directly",
                "emergency_contact": "+977-1-4000000",
            }
        ]


class LoadSheddingManager:
    """
    Manages load shedding during high traffic periods.
    """

    def __init__(self, degradation_manager: GracefulDegradationManager):
        self.manager = degradation_manager
        self.request_counts = {}
        self.rate_limits = {
            "anonymous": 10,  # requests per minute
            "authenticated": 50,
            "premium": 200,
        }
        self.shed_levels = {
            DegradationLevel.MINOR: 0.1,  # Shed 10% of requests
            DegradationLevel.MODERATE: 0.25,  # Shed 25% of requests
            DegradationLevel.MAJOR: 0.5,  # Shed 50% of requests
            DegradationLevel.CRITICAL: 0.8,  # Shed 80% of requests
        }

    def should_shed_request(self, user_tier: str, endpoint: str) -> bool:
        """Determine if request should be shed."""
        degradation_level = self.manager.get_system_degradation_level()

        if degradation_level == DegradationLevel.NONE:
            return False

        # Calculate shed probability
        shed_probability = self.shed_levels.get(degradation_level, 0)

        # Adjust based on user tier
        tier_adjustments = {
            "premium": 0.5,  # Premium users less likely to be shed
            "authenticated": 0.8,
            "anonymous": 1.2,  # Anonymous users more likely to be shed
        }

        adjusted_probability = shed_probability * tier_adjustments.get(user_tier, 1.0)

        # Random shedding based on probability
        import random

        return random.random() < adjusted_probability

    def get_shed_response(self, degradation_level: DegradationLevel) -> Response:
        """Get appropriate response for shed requests."""
        if degradation_level in [DegradationLevel.MAJOR, DegradationLevel.CRITICAL]:
            return Response(
                {
                    "error": "Service temporarily overloaded",
                    "message": "Please try again in a few minutes",
                    "retry_after": 300,
                    "degradation_level": degradation_level.name.lower(),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "300"},
            )
        else:
            return Response(
                {
                    "error": "Service experiencing high load",
                    "message": "Reduced functionality available",
                    "degradation_level": degradation_level.name.lower(),
                },
                status=status.HTTP_206_PARTIAL_CONTENT,
            )


class FallbackDataManager:
    """
    Manages fallback data sources during service degradation.
    """

    def __init__(self):
        self.fallback_sources = {}
        self.static_data = {}

    def register_fallback_source(self, data_type: str, source_function: Callable):
        """Register a fallback data source."""
        self.fallback_sources[data_type] = source_function

    def get_fallback_data(self, data_type: str, **kwargs) -> Any:
        """Get data from fallback source."""
        if data_type in self.fallback_sources:
            try:
                return self.fallback_sources[data_type](**kwargs)
            except Exception as e:
                logger.error(f"Fallback source failed for {data_type}: {e}")

        # Return static data if available
        return self.static_data.get(data_type, {})

    def preload_static_data(self):
        """Preload static data for emergency use."""
        self.static_data = {
            "popular_products": [
                {"id": 1, "name": "Rice", "category": "grains"},
                {"id": 2, "name": "Vegetables", "category": "agriculture"},
                {"id": 3, "name": "Dairy", "category": "dairy"},
            ],
            "delivery_zones": [
                {"name": "Kathmandu", "base_cost": 100},
                {"name": "Pokhara", "base_cost": 150},
                {"name": "Chitwan", "base_cost": 120},
            ],
            "emergency_contacts": [
                {"name": "Customer Support", "phone": "+977-1-4000000"},
                {"name": "Technical Support", "phone": "+977-1-4000001"},
            ],
        }


# Global instances
_degradation_manager = None
_location_service_degradation = None
_load_shedding_manager = None
_fallback_data_manager = None


def get_degradation_components():
    """Get global degradation management components."""
    global _degradation_manager, _location_service_degradation
    global _load_shedding_manager, _fallback_data_manager

    if _degradation_manager is None:
        _degradation_manager = GracefulDegradationManager()
        _location_service_degradation = LocationServiceDegradation(_degradation_manager)
        _load_shedding_manager = LoadSheddingManager(_degradation_manager)
        _fallback_data_manager = FallbackDataManager()

        # Setup default services
        setup_default_services()

    return (_degradation_manager, _location_service_degradation, _load_shedding_manager, _fallback_data_manager)


def setup_default_services():
    """Setup default services for degradation management."""
    manager, _, _, fallback_manager = get_degradation_components()

    # Database health check
    def database_health_check():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception:
            return False

    # Cache health check
    def cache_health_check():
        try:
            cache.set("health_test", "ok", 10)
            return cache.get("health_test") == "ok"
        except Exception:
            return False

    # Register services
    manager.register_service("database", database_health_check)
    manager.register_service("cache", cache_health_check)

    # Preload fallback data
    fallback_manager.preload_static_data()


def start_degradation_monitoring():
    """Start degradation monitoring."""
    manager, _, _, _ = get_degradation_components()

    def monitor_loop():
        while manager.monitoring_active:
            for service_name in manager.service_statuses:
                manager.update_service_status(service_name)
            time.sleep(manager.health_check_interval)

    if not manager.monitoring_active:
        manager.monitoring_active = True
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        logger.info("Degradation monitoring started")


def stop_degradation_monitoring():
    """Stop degradation monitoring."""
    manager, _, _, _ = get_degradation_components()
    manager.monitoring_active = False
    logger.info("Degradation monitoring stopped")


# Decorator for automatic degradation handling
def with_graceful_degradation(data_type: str = "products"):
    """Decorator to add automatic degradation handling to view functions."""

    def decorator(view_func):
        def wrapper(*args, **kwargs):
            manager, location_service, load_shedding, _ = get_degradation_components()

            # Check if request should be shed
            request = args[1] if len(args) > 1 else args[0]  # Get request object
            user_tier = getattr(request.user, "tier", "anonymous") if hasattr(request, "user") else "anonymous"

            if load_shedding.should_shed_request(user_tier, view_func.__name__):
                degradation_level = manager.get_system_degradation_level()
                return load_shedding.get_shed_response(degradation_level)

            try:
                # Execute original view
                return view_func(*args, **kwargs)
            except Exception as e:
                logger.error(f"View {view_func.__name__} failed: {e}")

                # Return degraded response
                degradation_level = manager.get_system_degradation_level()
                return Response(
                    {
                        "error": "Service temporarily degraded",
                        "message": "Limited functionality available",
                        "degradation_level": degradation_level.name.lower(),
                    },
                    status=status.HTTP_206_PARTIAL_CONTENT,
                )

        return wrapper

    return decorator
