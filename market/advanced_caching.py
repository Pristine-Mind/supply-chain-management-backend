import hashlib
import json
import logging
import pickle
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Union

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.cache import cache, caches
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for different cache types."""

    ttl: int = 300  # Time to live in seconds
    max_entries: int = 10000  # Max entries in cache
    compression: bool = False  # Enable compression for large objects
    version: int = 1  # Cache version for invalidation
    tags: List[str] = None  # Cache tags for group invalidation


class LocationCacheManager:
    """
    Advanced cache manager for location-based operations with high concurrency support.
    """

    # Cache configurations for different data types
    CACHE_CONFIGS = {
        "user_zones": CacheConfig(ttl=1800, max_entries=50000, tags=["geo", "zones"]),  # 30 min
        "product_distances": CacheConfig(ttl=600, max_entries=100000, tags=["geo", "products"]),  # 10 min
        "delivery_info": CacheConfig(ttl=300, max_entries=200000, tags=["delivery"]),  # 5 min
        "search_results": CacheConfig(ttl=180, max_entries=50000, tags=["search"]),  # 3 min
        "zone_products": CacheConfig(ttl=900, max_entries=10000, tags=["geo", "products"]),  # 15 min
        "producer_locations": CacheConfig(ttl=3600, max_entries=5000, tags=["producers"]),  # 1 hour
    }

    # Cache stampede prevention locks
    _locks = {}
    _lock_lock = Lock()

    def __init__(self):
        self.default_cache = cache
        try:
            self.location_cache = caches["location_cache"]  # Dedicated location cache
        except (KeyError, Exception):
            self.location_cache = cache  # Fallback to default cache

    def get_cache_key(self, key_type: str, **params) -> str:
        """
        Generate consistent cache keys for different operations.

        Args:
            key_type: Type of cache operation
            **params: Parameters for key generation

        Returns:
            Consistent cache key
        """
        # Sort parameters for consistent key generation
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)

        # Hash long parameter strings to avoid key length issues
        if len(param_str) > 100:
            param_hash = hashlib.md5(param_str.encode()).hexdigest()
            param_str = f"hash_{param_hash}"

        version = self.CACHE_CONFIGS.get(key_type, CacheConfig()).version

        return f"location_cache:v{version}:{key_type}:{param_str}"

    def get_with_fallback(
        self, key: str, fallback_func: Callable, cache_type: str = "default", **fallback_kwargs
    ) -> Optional[Any]:
        """
        Get value from cache with fallback function and stampede prevention.

        Args:
            key: Cache key
            fallback_func: Function to call if cache miss
            cache_type: Type of cache configuration to use
            **fallback_kwargs: Arguments for fallback function

        Returns:
            Cached value or result from fallback function
        """
        # Try to get from cache first
        value = self.location_cache.get(key)
        if value is not None:
            return self._deserialize_cache_value(value)

        # Cache stampede prevention
        lock_key = f"lock:{key}"
        with self._get_lock(lock_key):
            # Check cache again in case another thread filled it
            value = self.location_cache.get(key)
            if value is not None:
                return self._deserialize_cache_value(value)

            # Call fallback function
            try:
                result = fallback_func(**fallback_kwargs)

                # Cache the result
                config = self.CACHE_CONFIGS.get(cache_type, CacheConfig())
                serialized_value = self._serialize_cache_value(result)

                self.location_cache.set(key, serialized_value, config.ttl)

                # Track cache metrics
                self._track_cache_metrics("miss", cache_type)

                return result

            except Exception as e:
                logger.error(f"Fallback function failed for key {key}: {e}")
                self._track_cache_metrics("error", cache_type)
                return None

    def set_with_config(self, key: str, value: Any, cache_type: str = "default"):
        """Set value in cache with appropriate configuration."""
        config = self.CACHE_CONFIGS.get(cache_type, CacheConfig())
        serialized_value = self._serialize_cache_value(value)

        self.location_cache.set(key, serialized_value, config.ttl)
        self._track_cache_metrics("set", cache_type)

    def invalidate_by_tags(self, tags: List[str]):
        """Invalidate cache entries by tags."""
        for cache_type, config in self.CACHE_CONFIGS.items():
            if config.tags and any(tag in config.tags for tag in tags):
                # Increment version to invalidate
                config.version += 1
                logger.info(f"Invalidated cache type '{cache_type}' for tags: {tags}")

    def invalidate_user_location_cache(self, user_id: int):
        """Invalidate all location-related cache for a specific user."""
        patterns = [
            f"location_cache:*:user_zones:*user_id={user_id}*",
            f"location_cache:*:delivery_info:*user_id={user_id}*",
            f"location_cache:*:search_results:*user_id={user_id}*",
        ]

        for pattern in patterns:
            self._delete_by_pattern(pattern)

    def warm_cache_for_location(self, latitude: float, longitude: float, radius_km: float = 50):
        """
        Pre-warm cache for a specific location to improve response times.
        """
        from geo.services import GeoLocationService, GeoProductFilterService

        geo_service = GeoLocationService()
        filter_service = GeoProductFilterService()

        # Warm up zone detection
        zone_key = self.get_cache_key("user_zones", latitude=latitude, longitude=longitude)
        self.get_with_fallback(
            zone_key, geo_service.get_user_zone, "user_zones", user=None, latitude=latitude, longitude=longitude
        )

        # Warm up nearby products cache
        from market.models import MarketplaceUserProduct
        from producer.models import MarketplaceProduct

        for model_class in [MarketplaceProduct, MarketplaceUserProduct]:
            products_key = self.get_cache_key(
                "zone_products", model=model_class.__name__, latitude=latitude, longitude=longitude, radius=radius_km
            )

            self.get_with_fallback(
                products_key,
                filter_service.get_nearby_products,
                "zone_products",
                model_class=model_class,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                limit=20,  # Limit for warming
            )

    def get_cache_stats(self) -> Dict:
        """Get cache performance statistics."""
        stats = {
            "cache_types": {},
            "total_hits": 0,
            "total_misses": 0,
            "total_errors": 0,
        }

        for cache_type in self.CACHE_CONFIGS:
            type_stats = cache.get(f"cache_stats:{cache_type}", {"hits": 0, "misses": 0, "errors": 0, "sets": 0})

            stats["cache_types"][cache_type] = type_stats
            stats["total_hits"] += type_stats.get("hits", 0)
            stats["total_misses"] += type_stats.get("misses", 0)
            stats["total_errors"] += type_stats.get("errors", 0)

        # Calculate hit ratio
        total_requests = stats["total_hits"] + stats["total_misses"]
        stats["hit_ratio"] = stats["total_hits"] / total_requests if total_requests > 0 else 0

        return stats

    def _get_lock(self, lock_key: str) -> Lock:
        """Get or create lock for cache stampede prevention."""
        with self._lock_lock:
            if lock_key not in self._locks:
                self._locks[lock_key] = Lock()
            return self._locks[lock_key]

    def _serialize_cache_value(self, value: Any) -> Any:
        """Serialize value for caching."""
        try:
            # For simple types, return as-is
            if isinstance(value, (str, int, float, bool, type(None))):
                return value

            # For QuerySets, convert to list
            if hasattr(value, "__iter__") and hasattr(value, "model"):
                return {"type": "queryset", "model": value.model.__name__, "data": list(value.values())}

            # For complex objects, use pickle
            return {"type": "pickled", "data": pickle.dumps(value)}

        except Exception as e:
            logger.warning(f"Failed to serialize cache value: {e}")
            return None

    def _deserialize_cache_value(self, value: Any) -> Any:
        """Deserialize cached value."""
        try:
            if isinstance(value, dict) and "type" in value:
                if value["type"] == "pickled":
                    return pickle.loads(value["data"])
                elif value["type"] == "queryset":
                    return value["data"]  # Return as list

            return value

        except Exception as e:
            logger.warning(f"Failed to deserialize cache value: {e}")
            return None

    def _track_cache_metrics(self, metric_type: str, cache_type: str):
        """Track cache performance metrics."""
        stats_key = f"cache_stats:{cache_type}"
        stats = cache.get(stats_key, {"hits": 0, "misses": 0, "errors": 0, "sets": 0})

        if metric_type in stats:
            stats[metric_type] += 1
            cache.set(stats_key, stats, 3600)  # 1 hour TTL for stats

    def _delete_by_pattern(self, pattern: str):
        """Delete cache keys matching pattern (Redis-specific)."""
        try:
            # This is Redis-specific - implement based on your cache backend
            if hasattr(self.location_cache, "_cache") and hasattr(self.location_cache._cache, "delete_pattern"):
                self.location_cache._cache.delete_pattern(pattern)
        except Exception as e:
            logger.warning(f"Pattern-based cache deletion failed: {e}")


# Alias for geographic-specific caching
class GeographicCacheManager(LocationCacheManager):
    """
    Cache manager specialized for geographic operations.
    Extends LocationCacheManager with geographic-specific features.
    """

    pass


class GeographicCachePartitioner:
    """
    Partition cache based on geographic regions for better performance and locality.
    """

    # Define geographic regions for cache partitioning
    REGIONS = {
        "kathmandu": {"min_lat": 27.6, "max_lat": 27.8, "min_lon": 85.2, "max_lon": 85.4},
        "pokhara": {"min_lat": 28.1, "max_lat": 28.3, "min_lon": 83.8, "max_lon": 84.1},
        "chitwan": {"min_lat": 27.5, "max_lat": 27.8, "min_lon": 84.2, "max_lon": 84.6},
        "other": {"min_lat": -90, "max_lat": 90, "min_lon": -180, "max_lon": 180},
    }

    @classmethod
    def get_region_for_coordinates(cls, latitude: float, longitude: float) -> str:
        """Determine geographic region for coordinates."""
        for region, bounds in cls.REGIONS.items():
            if bounds["min_lat"] <= latitude <= bounds["max_lat"] and bounds["min_lon"] <= longitude <= bounds["max_lon"]:
                return region
        return "other"

    @classmethod
    def get_regional_cache_key(cls, base_key: str, latitude: float, longitude: float) -> str:
        """Generate region-specific cache key."""
        region = cls.get_region_for_coordinates(latitude, longitude)
        return f"{base_key}:region_{region}"


class CacheWarmingService:
    """
    Service for proactive cache warming to improve performance.
    """

    def __init__(self):
        self.cache_manager = LocationCacheManager()
        self.executor = ThreadPoolExecutor(max_workers=5)

    def warm_popular_locations(self):
        """Warm cache for popular/frequently accessed locations."""
        popular_locations = [
            (27.7172, 85.3240),  # Kathmandu
            (28.2096, 83.9856),  # Pokhara
            (27.7000, 84.4333),  # Chitwan
            # Add more based on analytics
        ]

        for lat, lon in popular_locations:
            self.executor.submit(self.cache_manager.warm_cache_for_location, lat, lon, 25)  # 25km radius

    def warm_user_preferences(self, user_locations: List[Dict]):
        """Warm cache based on user location preferences."""
        for location in user_locations:
            self.executor.submit(
                self.cache_manager.warm_cache_for_location,
                location["latitude"],
                location["longitude"],
                location.get("preferred_radius", 20),
            )

    def schedule_cache_warming(self):
        """Schedule regular cache warming operations."""
        # This would typically be called by a background task
        self.warm_popular_locations()


def cached_location_operation(cache_type: str = "default", ttl: Optional[int] = None):
    """
    Decorator for caching location-based operations with automatic key generation.

    Args:
        cache_type: Type of cache configuration to use
        ttl: Custom TTL override

    Usage:
        @cached_location_operation('user_zones', ttl=900)
        def get_user_zone_expensive(user_id, lat, lon):
            # Expensive operation
            pass
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_manager = LocationCacheManager()

            # Generate cache key from function name and arguments
            key_params = {}

            # Handle positional arguments
            import inspect

            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())

            for i, arg in enumerate(args):
                if i < len(param_names):
                    key_params[param_names[i]] = arg

            # Add keyword arguments
            key_params.update(kwargs)

            cache_key = cache_manager.get_cache_key(f"{func.__module__}.{func.__name__}", **key_params)

            # Try to get from cache
            result = cache_manager.get_with_fallback(cache_key, func, cache_type, **dict(zip(param_names, args), **kwargs))

            return result

        return wrapper

    return decorator


class CacheInvalidationManager:
    """
    Manage intelligent cache invalidation based on data changes.
    """

    def __init__(self):
        self.cache_manager = LocationCacheManager()

    def invalidate_on_product_update(self, product):
        """Invalidate relevant caches when product is updated."""
        tags_to_invalidate = ["products"]

        # If product location changed, invalidate geo-related caches
        if hasattr(product, "product") and product.product.producer:
            tags_to_invalidate.extend(["geo", "delivery"])
        elif hasattr(product, "location"):
            tags_to_invalidate.extend(["geo", "delivery"])

        self.cache_manager.invalidate_by_tags(tags_to_invalidate)

    def invalidate_on_producer_update(self, producer):
        """Invalidate caches when producer location/settings change."""
        self.cache_manager.invalidate_by_tags(["geo", "producers", "delivery", "products"])

    def invalidate_on_zone_update(self, geographic_zone):
        """Invalidate caches when geographic zones are modified."""
        self.cache_manager.invalidate_by_tags(["geo", "zones", "delivery"])


# Cache monitoring and health check functions
def get_cache_health_status() -> Dict:
    """Get comprehensive cache health status."""
    cache_manager = LocationCacheManager()

    try:
        # Test cache operations
        test_key = "health_check_test"
        test_value = {"test": True, "timestamp": time.time()}

        cache_manager.location_cache.set(test_key, test_value, 60)
        retrieved = cache_manager.location_cache.get(test_key)
        cache_manager.location_cache.delete(test_key)

        working = retrieved is not None

        return {
            "status": "healthy" if working else "unhealthy",
            "statistics": cache_manager.get_cache_stats(),
            "timestamp": timezone.now().isoformat(),
            "test_successful": working,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat(),
            "test_successful": False,
        }
