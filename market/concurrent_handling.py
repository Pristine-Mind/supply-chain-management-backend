import asyncio
import logging
import time
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import wraps
from queue import Empty, PriorityQueue, Queue
from threading import Lock, RLock, Semaphore
from typing import Any, Callable, Dict, List, Optional, Union

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@dataclass
class RequestPriority:
    """Request priority levels for queue management."""

    HIGH = 1  # Premium users, critical operations
    NORMAL = 2  # Regular users
    LOW = 3  # Background tasks, bulk operations


@dataclass
class LoadMetrics:
    """Current system load metrics."""

    active_requests: int = 0
    queued_requests: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    response_time_avg: float = 0.0
    error_rate: float = 0.0
    timestamp: float = 0.0


class RequestQueue:
    """
    Advanced request queue with priority handling and overflow protection.
    """

    def __init__(self, max_size: int = 1000):
        self.queue = PriorityQueue(maxsize=max_size)
        self.overflow_queue = Queue(maxsize=500)  # Emergency overflow
        self.processing = set()
        self.lock = Lock()
        self.stats = {
            "total_requests": 0,
            "completed_requests": 0,
            "failed_requests": 0,
            "overflow_count": 0,
        }

    def enqueue(self, request_id: str, priority: int, func: Callable, args: tuple = (), kwargs: dict = None) -> bool:
        """
        Add request to queue with priority.

        Returns:
            True if queued successfully, False if queue is full
        """
        kwargs = kwargs or {}
        request_item = (priority, time.time(), request_id, func, args, kwargs)

        try:
            self.queue.put(request_item, block=False)
            self.stats["total_requests"] += 1
            return True

        except:
            # Try overflow queue as last resort
            try:
                self.overflow_queue.put(request_item, block=False)
                self.stats["overflow_count"] += 1
                logger.warning(f"Request {request_id} moved to overflow queue")
                return True
            except:
                logger.error(f"Request {request_id} dropped - all queues full")
                return False

    def dequeue(self, timeout: float = 1.0) -> Optional[tuple]:
        """Get next request from queue."""
        try:
            # Try main queue first
            item = self.queue.get(timeout=timeout)
            return item
        except Empty:
            # Try overflow queue
            try:
                item = self.overflow_queue.get(timeout=0.1)
                return item
            except Empty:
                return None

    def mark_processing(self, request_id: str):
        """Mark request as currently processing."""
        with self.lock:
            self.processing.add(request_id)

    def mark_completed(self, request_id: str, success: bool = True):
        """Mark request as completed."""
        with self.lock:
            self.processing.discard(request_id)
            if success:
                self.stats["completed_requests"] += 1
            else:
                self.stats["failed_requests"] += 1

    def get_stats(self) -> Dict:
        """Get queue statistics."""
        return {
            **self.stats,
            "queued_requests": self.queue.qsize() + self.overflow_queue.qsize(),
            "processing_requests": len(self.processing),
        }


class ConcurrentRequestManager:
    """
    Manager for handling high concurrent load with resource management.
    """

    # Configuration for 2000 concurrent users
    MAX_CONCURRENT_REQUESTS = getattr(settings, "MAX_CONCURRENT_LOCATION_REQUESTS", 100)
    MAX_WORKER_THREADS = getattr(settings, "LOCATION_WORKER_THREADS", 20)
    REQUEST_TIMEOUT = 30  # seconds
    QUEUE_SIZE = 2000

    def __init__(self):
        self.request_semaphore = Semaphore(self.MAX_CONCURRENT_REQUESTS)
        self.worker_pool = ThreadPoolExecutor(max_workers=self.MAX_WORKER_THREADS, thread_name_prefix="LocationAPI")
        self.request_queue = RequestQueue(self.QUEUE_SIZE)
        self.load_monitor = LoadMonitor()

        # Track active requests
        self._active_requests = weakref.WeakSet()
        self._request_metrics = {}
        self._metrics_lock = RLock()

        # Start background queue processor
        self._start_queue_processor()

    def handle_request(self, request_id: str, func: Callable, priority: int = RequestPriority.NORMAL, *args, **kwargs):
        """
        Handle incoming request with concurrency control.

        Args:
            request_id: Unique request identifier
            func: Function to execute
            priority: Request priority level
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Response or queued status
        """
        current_load = self.load_monitor.get_current_metrics()

        # Check if system is overloaded
        if self._is_system_overloaded(current_load):
            return self._handle_overload(request_id, priority)

        # Try to acquire semaphore (non-blocking)
        if self.request_semaphore.acquire(blocking=False):
            try:
                # Execute immediately
                return self._execute_request(request_id, func, args, kwargs)
            finally:
                self.request_semaphore.release()
        else:
            # Queue the request
            if self.request_queue.enqueue(request_id, priority, func, args, kwargs):
                return {
                    "status": "queued",
                    "message": "Request queued due to high load",
                    "queue_position": self.request_queue.queue.qsize(),
                    "estimated_wait_time": self._estimate_wait_time(),
                }
            else:
                return {
                    "status": "rejected",
                    "message": "System at capacity, please try again later",
                    "retry_after": 60,  # seconds
                }

    def _execute_request(self, request_id: str, func: Callable, args: tuple, kwargs: dict):
        """Execute request with monitoring."""
        start_time = time.time()

        try:
            # Track request
            self._track_request_start(request_id, start_time)

            # Execute function with timeout protection
            result = self._execute_with_timeout(func, args, kwargs)

            # Track success
            execution_time = time.time() - start_time
            self._track_request_completion(request_id, execution_time, True)

            return result

        except Exception as e:
            # Track failure
            execution_time = time.time() - start_time
            self._track_request_completion(request_id, execution_time, False)

            logger.error(f"Request {request_id} failed after {execution_time:.2f}s: {e}")
            raise

    def _execute_with_timeout(self, func: Callable, args: tuple, kwargs: dict):
        """Execute function with timeout protection."""
        future = self.worker_pool.submit(func, *args, **kwargs)

        try:
            return future.result(timeout=self.REQUEST_TIMEOUT)
        except TimeoutError:
            # Attempt to cancel the future
            future.cancel()
            raise TimeoutError(f"Request timed out after {self.REQUEST_TIMEOUT} seconds")
        except Exception as e:
            raise e

    def _start_queue_processor(self):
        """Start background queue processor."""

        def process_queue():
            while True:
                try:
                    item = self.request_queue.dequeue(timeout=1.0)
                    if item is None:
                        continue

                    priority, timestamp, request_id, func, args, kwargs = item

                    # Check if request is too old
                    if time.time() - timestamp > 60:  # 1 minute timeout
                        self.request_queue.mark_completed(request_id, False)
                        logger.warning(f"Dropping expired request {request_id}")
                        continue

                    # Wait for semaphore
                    if self.request_semaphore.acquire(blocking=True, timeout=30):
                        try:
                            self.request_queue.mark_processing(request_id)
                            result = self._execute_request(request_id, func, args, kwargs)
                            self.request_queue.mark_completed(request_id, True)
                        except Exception as e:
                            self.request_queue.mark_completed(request_id, False)
                            logger.error(f"Queued request {request_id} failed: {e}")
                        finally:
                            self.request_semaphore.release()
                    else:
                        # Put back in queue if can't acquire semaphore
                        self.request_queue.enqueue(request_id, priority, func, args, kwargs)

                except Exception as e:
                    logger.error(f"Error in queue processor: {e}")
                    time.sleep(1)

        # Start processor in daemon thread
        import threading

        processor_thread = threading.Thread(target=process_queue, daemon=True)
        processor_thread.start()

    def _is_system_overloaded(self, metrics: LoadMetrics) -> bool:
        """Check if system is overloaded based on metrics."""
        overload_conditions = [
            metrics.active_requests > self.MAX_CONCURRENT_REQUESTS * 0.9,  # 90% capacity
            metrics.cpu_usage > 80.0,  # 80% CPU
            metrics.memory_usage > 85.0,  # 85% memory
            metrics.response_time_avg > 10.0,  # 10 second average response
            metrics.error_rate > 0.1,  # 10% error rate
        ]

        return any(overload_conditions)

    def _handle_overload(self, request_id: str, priority: int) -> Dict:
        """Handle system overload conditions."""
        if priority == RequestPriority.HIGH:
            # Allow high priority requests through with warning
            logger.warning(f"Allowing high-priority request {request_id} during overload")
            return None  # Continue processing
        else:
            # Reject lower priority requests
            return {
                "status": "overloaded",
                "message": "System temporarily overloaded, please try again later",
                "retry_after": 120,  # 2 minutes
            }

    def _estimate_wait_time(self) -> int:
        """Estimate wait time based on queue size and processing rate."""
        queue_size = self.request_queue.queue.qsize()
        avg_processing_time = self._get_average_processing_time()

        # Estimate based on queue size and worker capacity
        estimated_seconds = (queue_size / self.MAX_WORKER_THREADS) * avg_processing_time
        return min(int(estimated_seconds), 300)  # Max 5 minutes

    def _get_average_processing_time(self) -> float:
        """Get average request processing time."""
        with self._metrics_lock:
            if not self._request_metrics:
                return 2.0  # Default estimate

            total_time = sum(m["execution_time"] for m in self._request_metrics.values())
            return total_time / len(self._request_metrics)

    def _track_request_start(self, request_id: str, start_time: float):
        """Track request start."""
        with self._metrics_lock:
            self._request_metrics[request_id] = {
                "start_time": start_time,
                "execution_time": None,
                "success": None,
            }

    def _track_request_completion(self, request_id: str, execution_time: float, success: bool):
        """Track request completion."""
        with self._metrics_lock:
            if request_id in self._request_metrics:
                self._request_metrics[request_id].update(
                    {
                        "execution_time": execution_time,
                        "success": success,
                    }
                )

                # Keep only recent metrics (last 1000 requests)
                if len(self._request_metrics) > 1000:
                    oldest_id = min(self._request_metrics.keys(), key=lambda k: self._request_metrics[k]["start_time"])
                    del self._request_metrics[oldest_id]

    def get_system_status(self) -> Dict:
        """Get comprehensive system status."""
        queue_stats = self.request_queue.get_stats()
        load_metrics = self.load_monitor.get_current_metrics()

        with self._metrics_lock:
            recent_requests = len(self._request_metrics)
            successful_requests = sum(1 for m in self._request_metrics.values() if m.get("success", False))

            success_rate = (successful_requests / recent_requests) if recent_requests > 0 else 1.0

        return {
            "timestamp": timezone.now().isoformat(),
            "load_metrics": {
                "active_requests": load_metrics.active_requests,
                "queued_requests": load_metrics.queued_requests,
                "cpu_usage": load_metrics.cpu_usage,
                "memory_usage": load_metrics.memory_usage,
                "avg_response_time": load_metrics.response_time_avg,
            },
            "queue_stats": queue_stats,
            "performance": {
                "success_rate": success_rate,
                "avg_processing_time": self._get_average_processing_time(),
                "worker_threads": self.MAX_WORKER_THREADS,
                "max_concurrent": self.MAX_CONCURRENT_REQUESTS,
            },
            "capacity": {
                "utilization": (load_metrics.active_requests / self.MAX_CONCURRENT_REQUESTS) * 100,
                "queue_utilization": (queue_stats["queued_requests"] / self.QUEUE_SIZE) * 100,
            },
        }


class LoadMonitor:
    """
    Monitor system load and resource usage.
    """

    def __init__(self):
        self.metrics_history = []
        self.max_history = 100  # Keep last 100 measurements

    def get_current_metrics(self) -> LoadMetrics:
        """Get current system metrics."""
        try:
            import psutil

            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            # Get active request count from cache
            active_requests = cache.get("location_api_active_requests", 0)
            queued_requests = cache.get("location_api_queued_requests", 0)

            # Calculate average response time from recent history
            avg_response_time = self._calculate_avg_response_time()
            error_rate = self._calculate_error_rate()

            metrics = LoadMetrics(
                active_requests=active_requests,
                queued_requests=queued_requests,
                cpu_usage=cpu_percent,
                memory_usage=memory.percent,
                response_time_avg=avg_response_time,
                error_rate=error_rate,
                timestamp=time.time(),
            )

            # Store in history
            self.metrics_history.append(metrics)
            if len(self.metrics_history) > self.max_history:
                self.metrics_history.pop(0)

            return metrics

        except ImportError:
            logger.warning("psutil not available, using default metrics")
            return LoadMetrics(timestamp=time.time())
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return LoadMetrics(timestamp=time.time())

    def _calculate_avg_response_time(self) -> float:
        """Calculate average response time from recent history."""
        if len(self.metrics_history) < 2:
            return 0.0

        recent_metrics = self.metrics_history[-10:]  # Last 10 measurements
        return sum(m.response_time_avg for m in recent_metrics) / len(recent_metrics)

    def _calculate_error_rate(self) -> float:
        """Calculate current error rate."""
        error_count = cache.get("location_api_recent_errors", 0)
        total_requests = cache.get("location_api_recent_requests", 1)

        return error_count / total_requests if total_requests > 0 else 0.0


# Decorators and utilities for request management
def managed_concurrent_request(priority: int = RequestPriority.NORMAL):
    """
    Decorator for managing concurrent requests with automatic queuing.

    Usage:
        @managed_concurrent_request(priority=RequestPriority.HIGH)
        def expensive_location_operation(lat, lon):
            # Implementation
            pass
    """

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Get or create request manager
            manager = getattr(request, "_concurrent_manager", None)
            if not manager:
                manager = ConcurrentRequestManager()
                request._concurrent_manager = manager

            # Generate request ID
            request_id = f"{func.__name__}_{int(time.time() * 1000)}_{id(request)}"

            # Handle the request
            result = manager.handle_request(request_id, func, priority, request, *args, **kwargs)

            # If queued, return appropriate response
            if isinstance(result, dict) and result.get("status") in ["queued", "rejected", "overloaded"]:
                return JsonResponse(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            return result

        return wrapper

    return decorator


def track_request_metrics(func):
    """
    Decorator to track request metrics for monitoring.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        # Increment active request counter
        active_count = cache.get("location_api_active_requests", 0)
        cache.set("location_api_active_requests", active_count + 1, 60)

        try:
            result = func(*args, **kwargs)

            # Track success
            execution_time = time.time() - start_time
            _track_request_success(execution_time)

            return result

        except Exception as e:
            # Track error
            execution_time = time.time() - start_time
            _track_request_error(execution_time)
            raise

        finally:
            # Decrement active request counter
            active_count = cache.get("location_api_active_requests", 1)
            cache.set("location_api_active_requests", max(0, active_count - 1), 60)

    return wrapper


def _track_request_success(execution_time: float):
    """Track successful request."""
    # Update recent requests count
    recent_requests = cache.get("location_api_recent_requests", 0)
    cache.set("location_api_recent_requests", recent_requests + 1, 300)  # 5 min TTL

    # Update response time metrics
    _update_response_time_metrics(execution_time)


def _track_request_error(execution_time: float):
    """Track failed request."""
    # Update error count
    recent_errors = cache.get("location_api_recent_errors", 0)
    cache.set("location_api_recent_errors", recent_errors + 1, 300)  # 5 min TTL

    # Still track in total requests
    recent_requests = cache.get("location_api_recent_requests", 0)
    cache.set("location_api_recent_requests", recent_requests + 1, 300)

    _update_response_time_metrics(execution_time)


def _update_response_time_metrics(execution_time: float):
    """Update response time metrics."""
    # Simple rolling average
    current_avg = cache.get("location_api_avg_response_time", 0.0)
    current_count = cache.get("location_api_response_count", 0)

    new_count = current_count + 1
    new_avg = ((current_avg * current_count) + execution_time) / new_count

    cache.set("location_api_avg_response_time", new_avg, 300)
    cache.set("location_api_response_count", new_count, 300)


# Initialize global request manager instance
_global_request_manager = None


def get_request_manager() -> ConcurrentRequestManager:
    """Get global request manager instance."""
    global _global_request_manager
    if _global_request_manager is None:
        _global_request_manager = ConcurrentRequestManager()
    return _global_request_manager
