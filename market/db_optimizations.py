import logging
import time
from contextlib import contextmanager
from typing import Dict, List, Optional, Union

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.db import connection, connections, transaction
from django.db.models import F, Q, QuerySet
from django.db.utils import DatabaseError, OperationalError

logger = logging.getLogger(__name__)


class DatabaseOptimizationMixin:
    """
    Mixin for optimizing database queries in high-traffic scenarios.
    """

    # Query timeout settings (seconds)
    QUERY_TIMEOUT = getattr(settings, "LOCATION_QUERY_TIMEOUT", 30)
    MAX_RETRIES = 3
    RETRY_DELAY = 0.1  # 100ms

    @classmethod
    def optimize_queryset_for_location(
        cls, queryset: QuerySet, latitude: float, longitude: float, max_distance_km: Optional[float] = None
    ) -> QuerySet:
        """
        Optimize queryset for location-based operations with proper indexing hints.

        Args:
            queryset: Base QuerySet
            latitude: User latitude
            longitude: User longitude
            max_distance_km: Maximum distance filter

        Returns:
            Optimized QuerySet with proper select_related and indexes
        """
        user_location = Point(longitude, latitude, srid=4326)

        # Apply different optimization strategies based on model
        model = queryset.model

        if hasattr(model, "product") and hasattr(model.product.related.related_model, "producer"):
            # MarketplaceProduct optimization
            queryset = cls._optimize_marketplace_product_query(queryset, user_location, max_distance_km)
        elif hasattr(model, "location") and hasattr(model, "user"):
            # MarketplaceUserProduct optimization
            queryset = cls._optimize_user_product_query(queryset, user_location, max_distance_km)

        return queryset

    @classmethod
    def _optimize_marketplace_product_query(
        cls, queryset: QuerySet, user_location: Point, max_distance_km: Optional[float]
    ) -> QuerySet:
        """Optimize MarketplaceProduct queries."""
        # Use select_related for foreign keys to avoid N+1
        queryset = queryset.select_related("product__producer", "product__category", "product__user")

        # Filter products with producer location first (indexed)
        queryset = queryset.filter(product__producer__location__isnull=False, is_available=True)

        # Add spatial index hint for PostGIS
        if max_distance_km:
            # Use spatial index with bounding box pre-filter for performance
            bbox_size = max_distance_km / 111.0  # Rough degrees conversion
            queryset = queryset.extra(
                where=["ST_DWithin(producer_location, ST_GeomFromText(%s, 4326), %s)"],
                params=[user_location.wkt, max_distance_km * 1000],  # meters
            )

        # Annotate distance (this will use spatial index)
        queryset = queryset.annotate(distance_km=Distance("product__producer__location", user_location) / 1000)

        # Apply service radius filter using database function
        queryset = queryset.extra(
            where=["(producer.service_radius_km IS NULL OR distance_km <= producer.service_radius_km)"]
        )

        return queryset.order_by("distance_km")

    @classmethod
    def _optimize_user_product_query(
        cls, queryset: QuerySet, user_location: Point, max_distance_km: Optional[float]
    ) -> QuerySet:
        """Optimize MarketplaceUserProduct queries."""
        # Select related for foreign keys
        queryset = queryset.select_related("user", "location")

        # Filter products with city location
        queryset = queryset.filter(location__location__isnull=False, is_sold=False, is_verified=True)

        # Spatial filtering with index hint
        if max_distance_km:
            queryset = queryset.extra(
                where=["ST_DWithin(geo_city.location, ST_GeomFromText(%s, 4326), %s)"],
                params=[user_location.wkt, max_distance_km * 1000],
            )

        # Annotate distance
        queryset = queryset.annotate(distance_km=Distance("location__location", user_location) / 1000)

        return queryset.order_by("distance_km")

    @classmethod
    def execute_with_retry(cls, query_func, *args, **kwargs):
        """
        Execute database query with retry logic for handling connection issues.
        """
        for attempt in range(cls.MAX_RETRIES):
            try:
                return query_func(*args, **kwargs)

            except OperationalError as e:
                if "connection" in str(e).lower() and attempt < cls.MAX_RETRIES - 1:
                    logger.warning(f"Database connection error (attempt {attempt + 1}): {e}")
                    time.sleep(cls.RETRY_DELAY * (2**attempt))  # Exponential backoff
                    continue
                raise

            except DatabaseError as e:
                if "deadlock" in str(e).lower() and attempt < cls.MAX_RETRIES - 1:
                    logger.warning(f"Deadlock detected (attempt {attempt + 1}): {e}")
                    time.sleep(cls.RETRY_DELAY * (2**attempt))
                    continue
                raise

        return None


class ConnectionPoolManager:
    """
    Manage database connections for high concurrent load.
    """

    @staticmethod
    def get_connection_stats() -> Dict:
        """Get current connection pool statistics."""
        stats = {}

        for alias in connections:
            conn = connections[alias]
            if hasattr(conn, "queries_logged"):
                stats[alias] = {
                    "queries_count": len(conn.queries_logged),
                    "is_usable": conn.is_usable(),
                }

        return stats

    @staticmethod
    @contextmanager
    def managed_connection(using="default"):
        """Context manager for managed database connections with cleanup."""
        connection_obj = connections[using]

        try:
            # Ensure connection is alive
            connection_obj.ensure_connection()
            yield connection_obj

        except Exception as e:
            logger.error(f"Database connection error: {e}")
            # Force connection close on error
            connection_obj.close()
            raise

        finally:
            # Close connection if it's been idle too long
            if hasattr(connection_obj, "queries_logged") and len(connection_obj.queries_logged) > 100:
                connection_obj.close()


class QueryOptimizer:
    """
    Optimize specific query patterns for location-based operations.
    """

    @staticmethod
    def batch_distance_calculation(products: List, user_latitude: float, user_longitude: float) -> Dict:
        """
        Calculate distances for multiple products in batch to avoid N+1 queries.
        """
        from geopy.distance import geodesic

        user_coords = (user_latitude, user_longitude)
        distances = {}

        try:
            for product in products:
                product_coords = None

                # Get product coordinates based on type
                if hasattr(product, "product") and product.product.producer and product.product.producer.location:
                    loc = product.product.producer.location
                    product_coords = (loc.y, loc.x)
                elif hasattr(product, "location") and product.location and product.location.location:
                    loc = product.location.location
                    product_coords = (loc.y, loc.x)

                if product_coords:
                    try:
                        distance_km = geodesic(user_coords, product_coords).kilometers
                        distances[product.id] = round(distance_km, 2)
                    except Exception as e:
                        logger.warning(f"Error calculating distance for product {product.id}: {e}")
                        distances[product.id] = None
                else:
                    distances[product.id] = None

        except Exception as e:
            logger.error(f"Error in batch distance calculation: {e}")

        return distances

    @staticmethod
    def prefetch_related_optimized(queryset: QuerySet, model_type: str) -> QuerySet:
        """
        Apply model-specific prefetch optimizations to prevent N+1 queries.
        """
        if model_type == "marketplace":
            return queryset.prefetch_related(
                # Optimize product images loading
                "product__images",
                # Optimize reviews loading with limited fields
                "marketplaceproductreview_set__user",
                # Optimize producer data
                "product__producer__user",
            ).select_related(
                "product__category",
                "product__producer",
            )
        elif model_type == "user":
            return queryset.prefetch_related(
                # Optimize user product images
                "images",
                # Optimize user profile data
                "user__profile",
            ).select_related(
                "user",
                "location",
            )

        return queryset

    @staticmethod
    def add_query_indexes_hints(queryset: QuerySet, operation: str = "location_search") -> QuerySet:
        """
        Add database-specific index hints for better query performance.
        """
        if operation == "location_search":
            # Force use of spatial indexes
            if connection.vendor == "postgresql":
                queryset = queryset.extra(
                    select={"distance_calculated": "TRUE"},
                    where=["ST_DWithin(location, %s, %s)"],
                    params=[Point(0, 0), 50000],  # Placeholder values
                )

        elif operation == "price_filter":
            # Use B-tree index on price fields
            queryset = queryset.extra(select={"price_indexed": "TRUE"})

        return queryset


class ConcurrentRequestManager:
    """
    Handle concurrent request limitations and queueing.
    """

    # Rate limiting configuration
    MAX_CONCURRENT_LOCATION_REQUESTS = getattr(settings, "MAX_CONCURRENT_LOCATION_REQUESTS", 50)
    REQUEST_QUEUE_TIMEOUT = 30  # seconds

    @classmethod
    def acquire_request_slot(cls, user_id: Optional[int] = None, ip: Optional[str] = None) -> bool:
        """
        Acquire a slot for processing location request to prevent overload.

        Args:
            user_id: User ID if authenticated
            ip: IP address for anonymous users

        Returns:
            True if slot acquired, False if at capacity
        """
        key = f"location_request_slots:{user_id or ip}"
        current_time = time.time()

        # Clean up old requests (older than 1 minute)
        active_requests = cache.get(f"location_active_requests", {})
        active_requests = {k: v for k, v in active_requests.items() if current_time - v < 60}

        # Check if under limit
        if len(active_requests) >= cls.MAX_CONCURRENT_LOCATION_REQUESTS:
            logger.warning(f"Location request limit reached: {len(active_requests)} active requests")
            return False

        # Add current request
        request_id = f"{key}:{current_time}"
        active_requests[request_id] = current_time
        cache.set("location_active_requests", active_requests, 120)

        return True

    @classmethod
    def release_request_slot(cls, user_id: Optional[int] = None, ip: Optional[str] = None):
        """Release request slot when processing complete."""
        key = f"location_request_slots:{user_id or ip}"

        active_requests = cache.get("location_active_requests", {})
        # Remove requests matching this user/ip
        active_requests = {k: v for k, v in active_requests.items() if not k.startswith(key)}
        cache.set("location_active_requests", active_requests, 120)


# Database connection settings for high load
DATABASE_OPTIMIZATION_SETTINGS = {
    "default": {
        # Connection pooling
        "CONN_MAX_AGE": 600,  # 10 minutes
        "CONN_HEALTH_CHECKS": True,
        # Query optimization
        "OPTIONS": {
            "MAX_CONNS": 200,  # Max connections for 2000 users
            "MIN_CONNS": 20,  # Keep minimum connections open
            "TIMEOUT": 30,  # Connection timeout
            "RETRY_INTERVAL": 1,
            # PostgreSQL specific optimizations
            "isolation_level": "read_committed",
            "autocommit": True,
            # Connection pooling with pgbouncer support
            "sslmode": "prefer",
            "connect_timeout": 10,
            "statement_timeout": 30000,  # 30 seconds
            "lock_timeout": 10000,  # 10 seconds
        },
    }
}

# Index creation SQL for optimal performance
LOCATION_INDEXES_SQL = [
    # Spatial indexes for producer locations
    """
    CREATE INDEX IF NOT EXISTS idx_producer_location_gist 
    ON producer_producer USING GIST (location);
    """,
    # Spatial indexes for city locations
    """
    CREATE INDEX IF NOT EXISTS idx_city_location_gist 
    ON geo_city USING GIST (location);
    """,
    # Composite indexes for common filters
    """
    CREATE INDEX IF NOT EXISTS idx_marketplace_product_available_price 
    ON producer_marketplaceproduct (is_available, listed_price) 
    WHERE is_available = TRUE;
    """,
    # User product indexes
    """
    CREATE INDEX IF NOT EXISTS idx_user_product_verified_sold 
    ON market_marketplaceuserproduct (is_verified, is_sold, price)  
    WHERE is_verified = TRUE AND is_sold = FALSE;
    """,
    # Service radius index
    """
    CREATE INDEX IF NOT EXISTS idx_producer_service_radius 
    ON producer_producer (service_radius_km);
    """,
]
