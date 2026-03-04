import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Service is failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: int = 60  # Seconds before trying to recover
    success_threshold: int = 2  # Successes needed to close circuit
    timeout: float = 30.0  # Request timeout in seconds
    expected_exception: tuple = (Exception,)  # Exceptions to count as failures


@dataclass
class CircuitBreakerMetrics:
    """Metrics tracking for circuit breaker."""

    total_requests: int = 0
    failed_requests: int = 0
    successful_requests: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_change_history: List[Dict] = field(default_factory=list)


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting services from cascading failures.
    """

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.metrics = CircuitBreakerMetrics()
        self.state = CircuitBreakerState.CLOSED
        self.lock = Lock()

        # Cache key for persistence across requests
        self.cache_key = f"circuit_breaker:{self.name}"
        self._load_state()

    def _load_state(self):
        """Load circuit breaker state from cache."""
        try:
            cached_data = cache.get(self.cache_key)
            if cached_data:
                self.state = CircuitBreakerState(cached_data.get("state", "closed"))
                self.metrics.consecutive_failures = cached_data.get("consecutive_failures", 0)
                self.metrics.last_failure_time = cached_data.get("last_failure_time")
        except Exception as e:
            logger.warning(f"Failed to load circuit breaker state: {e}")

    def _save_state(self):
        """Save circuit breaker state to cache."""
        try:
            cache_data = {
                "state": self.state.value,
                "consecutive_failures": self.metrics.consecutive_failures,
                "last_failure_time": self.metrics.last_failure_time,
                "last_success_time": self.metrics.last_success_time,
            }
            cache.set(self.cache_key, cache_data, 3600)  # 1 hour TTL
        except Exception as e:
            logger.warning(f"Failed to save circuit breaker state: {e}")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker protection.

        Args:
            func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments

        Returns:
            Function result or raises CircuitBreakerOpenError

        Raises:
            CircuitBreakerOpenError: When circuit is open
            Original exception: When function fails and circuit allows it
        """
        with self.lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    self._log_state_change("OPEN -> HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")

            self.metrics.total_requests += 1

        try:
            # Execute the function with timeout
            result = self._execute_with_timeout(func, *args, **kwargs)
            self._on_success()
            return result

        except self.config.expected_exception as e:
            self._on_failure(e)
            raise

    def _execute_with_timeout(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with timeout protection."""
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Function {func.__name__} timed out after {self.config.timeout}s")

        # Set timeout for non-async functions
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(self.config.timeout))

        try:
            return func(*args, **kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def _on_success(self):
        """Handle successful function execution."""
        with self.lock:
            self.metrics.successful_requests += 1
            self.metrics.consecutive_successes += 1
            self.metrics.consecutive_failures = 0
            self.metrics.last_success_time = time.time()

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self.metrics.consecutive_successes >= self.config.success_threshold:
                    self.state = CircuitBreakerState.CLOSED
                    self._log_state_change("HALF_OPEN -> CLOSED")

            self._save_state()

    def _on_failure(self, exception: Exception):
        """Handle failed function execution."""
        with self.lock:
            self.metrics.failed_requests += 1
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            self.metrics.last_failure_time = time.time()

            if (
                self.state == CircuitBreakerState.CLOSED
                and self.metrics.consecutive_failures >= self.config.failure_threshold
            ):
                self.state = CircuitBreakerState.OPEN
                self._log_state_change("CLOSED -> OPEN")

            elif self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.OPEN
                self._log_state_change("HALF_OPEN -> OPEN")

            self._save_state()
            logger.warning(f"Circuit breaker '{self.name}' recorded failure: {exception}")

    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt to reset."""
        if not self.metrics.last_failure_time:
            return True
        return (time.time() - self.metrics.last_failure_time) >= self.config.recovery_timeout

    def _log_state_change(self, transition: str):
        """Log circuit breaker state changes."""
        logger.info(f"Circuit breaker '{self.name}' state change: {transition}")
        self.metrics.state_change_history.append(
            {
                "timestamp": time.time(),
                "transition": transition,
                "consecutive_failures": self.metrics.consecutive_failures,
            }
        )

    def get_stats(self) -> Dict:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_requests": self.metrics.total_requests,
            "failed_requests": self.metrics.failed_requests,
            "successful_requests": self.metrics.successful_requests,
            "failure_rate": (
                self.metrics.failed_requests / self.metrics.total_requests if self.metrics.total_requests > 0 else 0
            ),
            "consecutive_failures": self.metrics.consecutive_failures,
            "last_failure": self.metrics.last_failure_time,
            "last_success": self.metrics.last_success_time,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""

    pass


class LocationServiceCircuitBreakers:
    """
    Circuit breakers specifically for location-based services.
    """

    # Service-specific configurations
    CONFIGS = {
        "geo_location_service": CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30,
            success_threshold=2,
            timeout=10.0,
        ),
        "distance_calculation": CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=3,
            timeout=5.0,
        ),
        "zone_detection": CircuitBreakerConfig(
            failure_threshold=4,
            recovery_timeout=45,
            success_threshold=2,
            timeout=8.0,
        ),
        "delivery_calculation": CircuitBreakerConfig(
            failure_threshold=6,
            recovery_timeout=90,
            success_threshold=2,
            timeout=15.0,
        ),
        "database_queries": CircuitBreakerConfig(
            failure_threshold=8,
            recovery_timeout=120,
            success_threshold=3,
            timeout=30.0,
        ),
    }

    _instances = {}

    @classmethod
    def get_breaker(cls, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for service."""
        if service_name not in cls._instances:
            config = cls.CONFIGS.get(service_name, CircuitBreakerConfig())
            cls._instances[service_name] = CircuitBreaker(service_name, config)
        return cls._instances[service_name]

    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict]:
        """Get statistics for all circuit breakers."""
        return {name: breaker.get_stats() for name, breaker in cls._instances.items()}


def circuit_breaker_protected(service_name: str, fallback: Callable = None):
    """
    Decorator for protecting functions with circuit breaker.

    Args:
        service_name: Name of the service for circuit breaker
        fallback: Optional fallback function to call when circuit is open

    Usage:
        @circuit_breaker_protected('geo_location_service', fallback=lambda: None)
        def get_user_location(lat, lon):
            # Service implementation
            pass
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            breaker = LocationServiceCircuitBreakers.get_breaker(service_name)

            try:
                return breaker.call(func, *args, **kwargs)
            except CircuitBreakerOpenError:
                logger.warning(f"Circuit breaker open for {service_name}, using fallback")
                if fallback:
                    return fallback(*args, **kwargs)
                raise

        return wrapper

    return decorator


class ServiceHealthMonitor:
    """
    Monitor health of location-based services and trigger circuit breaker actions.
    """

    def __init__(self):
        self.health_checks = {
            "database": self._check_database_health,
            "cache": self._check_cache_health,
            "geo_service": self._check_geo_service_health,
        }

    def run_health_checks(self) -> Dict[str, Dict]:
        """Run all health checks and return results."""
        results = {}

        for service, check_func in self.health_checks.items():
            try:
                start_time = time.time()
                healthy, details = check_func()
                response_time = (time.time() - start_time) * 1000  # ms

                results[service] = {
                    "healthy": healthy,
                    "response_time_ms": response_time,
                    "details": details,
                    "timestamp": timezone.now().isoformat(),
                }

            except Exception as e:
                results[service] = {
                    "healthy": False,
                    "error": str(e),
                    "timestamp": timezone.now().isoformat(),
                }

        return results

    def _check_database_health(self) -> tuple[bool, str]:
        """Check database connectivity and performance."""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            if result and result[0] == 1:
                return True, "Database connection healthy"
            else:
                return False, "Database query returned unexpected result"

        except Exception as e:
            return False, f"Database error: {str(e)}"

    def _check_cache_health(self) -> tuple[bool, str]:
        """Check cache connectivity and performance."""
        try:
            test_key = "health_check_test"
            cache.set(test_key, "test_value", 10)
            retrieved = cache.get(test_key)

            if retrieved == "test_value":
                cache.delete(test_key)
                return True, "Cache working correctly"
            else:
                return False, "Cache set/get operation failed"

        except Exception as e:
            return False, f"Cache error: {str(e)}"

    def _check_geo_service_health(self) -> tuple[bool, str]:
        """Check geographic service functionality."""
        try:
            from geo.services import GeoLocationService

            geo_service = GeoLocationService()

            # Test with known coordinates (Kathmandu)
            zone = geo_service.get_user_zone(None, 27.7172, 85.3240)

            return True, f"Geo service working, zone: {zone.name if zone else 'None'}"

        except Exception as e:
            return False, f"Geo service error: {str(e)}"

    def trigger_circuit_breakers_on_health(self):
        """Trigger circuit breaker actions based on health check results."""
        health_results = self.run_health_checks()

        for service, result in health_results.items():
            if not result.get("healthy", False):
                # Get corresponding circuit breaker
                if service == "database":
                    breaker = LocationServiceCircuitBreakers.get_breaker("database_queries")
                elif service == "geo_service":
                    breaker = LocationServiceCircuitBreakers.get_breaker("geo_location_service")
                else:
                    continue

                # Simulate a failure to potentially open the circuit
                try:
                    raise Exception(f"Health check failed for {service}")
                except Exception as e:
                    breaker._on_failure(e)


# Fallback functions for when services are unavailable
class LocationServiceFallbacks:
    """
    Fallback implementations for location services when primary services fail.
    """

    @staticmethod
    def fallback_distance_calculation(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Simple distance calculation fallback using haversine formula."""
        from math import asin, cos, radians, sin, sqrt

        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        # Earth's radius in kilometers
        r = 6371
        return c * r

    @staticmethod
    def fallback_delivery_info(distance_km: float) -> Dict:
        """Fallback delivery information calculation."""
        if distance_km <= 5:
            cost, days = 0, 1
        elif distance_km <= 25:
            cost, days = 100, 2
        elif distance_km <= 50:
            cost, days = 200, 3
        else:
            cost, days = 300, 5

        return {
            "available": True,
            "reason": "Fallback calculation (primary service unavailable)",
            "distance_km": round(distance_km, 2),
            "estimated_cost": cost,
            "estimated_days": days,
            "zone_name": "Estimated Zone",
        }

    @staticmethod
    def fallback_zone_detection() -> Dict:
        """Fallback zone information when zone service is down."""
        return {
            "name": "Default Zone",
            "tier": "tier2",
            "shipping_cost": 150.0,
            "estimated_delivery_days": 3,
        }


def get_circuit_breaker(service_name: str) -> Optional[CircuitBreaker]:
    """
    Get a circuit breaker instance for a given service name.
    Maps common service names to LocationServiceCircuitBreakers configs.
    """
    # Map generic service names to specific circuit breaker names
    service_mapping = {
        "database": "database_queries",
        "db": "database_queries",
        "geocoding": "geo_location_service",
        "geo": "geo_location_service",
        "distance": "distance_calculation",
        "zone": "zone_detection",
        "delivery": "delivery_calculation",
    }

    mapped_name = service_mapping.get(service_name.lower(), service_name.lower())

    # Return circuit breaker if config exists
    if mapped_name in LocationServiceCircuitBreakers.CONFIGS:
        return LocationServiceCircuitBreakers.get_breaker(mapped_name)

    return None


# Health check endpoint data
def get_service_health_summary() -> Dict:
    """Get comprehensive service health summary for monitoring."""
    monitor = ServiceHealthMonitor()
    health_results = monitor.run_health_checks()
    circuit_breaker_stats = LocationServiceCircuitBreakers.get_all_stats()

    return {
        "timestamp": timezone.now().isoformat(),
        "health_checks": health_results,
        "circuit_breakers": circuit_breaker_stats,
        "overall_health": all(result.get("healthy", False) for result in health_results.values()),
    }
