import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Union

from celery import Celery, Task
from celery.result import AsyncResult
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels for background processing."""

    CRITICAL = 1  # System maintenance, data integrity
    HIGH = 2  # User-requested operations
    NORMAL = 3  # Regular background tasks
    LOW = 4  # Analytics, cleanup, optimization


class TaskStatus(Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    """Background task definition."""

    task_id: str
    task_type: str
    priority: TaskPriority
    payload: Dict
    created_at: datetime = field(default_factory=timezone.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict] = None
    error: Optional[str] = None
    progress: int = 0  # 0-100
    max_retries: int = 3
    retry_count: int = 0


class LocationBackgroundTaskManager:
    """
    Manager for location-related background tasks.
    """

    def __init__(self):
        self.task_registry = {}
        self.task_lock = Lock()
        self.executor = ThreadPoolExecutor(
            max_workers=getattr(settings, "LOCATION_BACKGROUND_WORKERS", 5), thread_name_prefix="LocationBG"
        )

    def submit_task(
        self, task_type: str, payload: Dict, priority: TaskPriority = TaskPriority.NORMAL, max_retries: int = 3
    ) -> str:
        """
        Submit a background task for processing.

        Args:
            task_type: Type of task to execute
            payload: Task parameters
            priority: Task priority level
            max_retries: Maximum retry attempts

        Returns:
            Task ID for tracking
        """
        task_id = str(uuid.uuid4())

        task = BackgroundTask(
            task_id=task_id, task_type=task_type, priority=priority, payload=payload, max_retries=max_retries
        )

        with self.task_lock:
            self.task_registry[task_id] = task

        # Submit to executor
        future = self.executor.submit(self._execute_task, task)

        # Store future reference
        task.future = future

        logger.info(f"Submitted background task {task_id}: {task_type}")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status of a background task."""
        with self.task_lock:
            task = self.task_registry.get(task_id)

        if not task:
            return None

        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "progress": task.progress,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result": task.result,
            "error": task.error,
            "retry_count": task.retry_count,
        }

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a background task if possible."""
        with self.task_lock:
            task = self.task_registry.get(task_id)

        if not task or task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return False

        # Try to cancel future
        if hasattr(task, "future") and task.future:
            cancelled = task.future.cancel()
            if cancelled:
                task.status = TaskStatus.CANCELLED
                task.completed_at = timezone.now()
                return True

        return False

    def _execute_task(self, task: BackgroundTask):
        """Execute a background task."""
        with self.task_lock:
            task.status = TaskStatus.RUNNING
            task.started_at = timezone.now()

        try:
            # Get task executor
            executor = self._get_task_executor(task.task_type)
            if not executor:
                raise ValueError(f"No executor found for task type: {task.task_type}")

            # Execute task
            result = executor(task)

            # Update task status
            with self.task_lock:
                task.status = TaskStatus.SUCCESS
                task.result = result
                task.progress = 100
                task.completed_at = timezone.now()

            logger.info(f"Task {task.task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {str(e)}")

            with self.task_lock:
                task.error = str(e)
                task.retry_count += 1

                # Retry if under limit
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.PENDING
                    # Reschedule with exponential backoff
                    delay = 2**task.retry_count
                    logger.info(f"Retrying task {task.task_id} in {delay} seconds")

                    # Schedule retry
                    def retry_task():
                        time.sleep(delay)
                        self._execute_task(task)

                    self.executor.submit(retry_task)
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = timezone.now()

    def _get_task_executor(self, task_type: str) -> Optional[Callable]:
        """Get executor function for task type."""
        executors = {
            "bulk_distance_calculation": self._execute_bulk_distance_calculation,
            "cache_warming": self._execute_cache_warming,
            "location_data_validation": self._execute_location_data_validation,
            "delivery_cost_precomputation": self._execute_delivery_cost_precomputation,
            "geographic_zone_update": self._execute_geographic_zone_update,
            "producer_location_sync": self._execute_producer_location_sync,
            "analytics_processing": self._execute_analytics_processing,
        }

        return executors.get(task_type)

    def _execute_bulk_distance_calculation(self, task: BackgroundTask) -> Dict:
        """Execute bulk distance calculations."""
        payload = task.payload
        coordinates = payload.get("coordinates", [])
        center_lat = payload.get("center_lat")
        center_lon = payload.get("center_lon")

        if not coordinates or not center_lat or not center_lon:
            raise ValueError("Invalid payload for bulk distance calculation")

        results = []
        total_coords = len(coordinates)

        for i, (lat, lon, item_id) in enumerate(coordinates):
            try:
                from market.geographic_edge_cases import DistanceCalculationHandler

                distance_result = DistanceCalculationHandler.calculate_distance_robust(center_lat, center_lon, lat, lon)

                results.append(
                    {
                        "item_id": item_id,
                        "latitude": lat,
                        "longitude": lon,
                        "distance_km": distance_result.get("distance_km"),
                        "valid": distance_result.get("valid", False),
                    }
                )

                # Update progress
                task.progress = int((i + 1) / total_coords * 100)

            except Exception as e:
                logger.warning(f"Distance calculation failed for {item_id}: {e}")
                results.append(
                    {
                        "item_id": item_id,
                        "latitude": lat,
                        "longitude": lon,
                        "distance_km": None,
                        "valid": False,
                        "error": str(e),
                    }
                )

        return {
            "total_processed": len(results),
            "successful": len([r for r in results if r["valid"]]),
            "failed": len([r for r in results if not r["valid"]]),
            "results": results,
        }

    def _execute_cache_warming(self, task: BackgroundTask) -> Dict:
        """Execute cache warming operations."""
        payload = task.payload
        locations = payload.get("locations", [])
        radius_km = payload.get("radius_km", 50)

        from market.advanced_caching import LocationCacheManager

        cache_manager = LocationCacheManager()

        warmed_count = 0
        failed_count = 0

        for i, location in enumerate(locations):
            try:
                lat = location["latitude"]
                lon = location["longitude"]

                cache_manager.warm_cache_for_location(lat, lon, radius_km)
                warmed_count += 1

                # Update progress
                task.progress = int((i + 1) / len(locations) * 100)

            except Exception as e:
                logger.warning(f"Cache warming failed for location {location}: {e}")
                failed_count += 1

        return {
            "locations_processed": len(locations),
            "successfully_warmed": warmed_count,
            "failed": failed_count,
        }

    def _execute_location_data_validation(self, task: BackgroundTask) -> Dict:
        """Execute location data validation."""
        from geo.models import City
        from market.geographic_edge_cases import GeographicDataIntegrityManager
        from producer.models import Producer

        payload = task.payload
        model_type = payload.get("model_type", "all")

        results = {
            "producers": {"checked": 0, "issues": 0, "details": []},
            "cities": {"checked": 0, "issues": 0, "details": []},
        }

        if model_type in ["all", "producers"]:
            producers = Producer.objects.filter(location__isnull=False)
            total_producers = producers.count()

            for i, producer in enumerate(producers):
                try:
                    issues = GeographicDataIntegrityManager.validate_producer_location_integrity(producer)
                    results["producers"]["checked"] += 1

                    if issues:
                        results["producers"]["issues"] += 1
                        results["producers"]["details"].append(
                            {
                                "id": producer.id,
                                "name": producer.name,
                                "issues": issues,
                            }
                        )

                    # Update progress
                    if model_type == "producers":
                        task.progress = int((i + 1) / total_producers * 100)
                    else:
                        task.progress = int((i + 1) / total_producers * 50)  # 50% for producers

                except Exception as e:
                    logger.error(f"Validation failed for producer {producer.id}: {e}")

        if model_type in ["all", "cities"]:
            cities = City.objects.filter(location__isnull=False)
            total_cities = cities.count()

            for i, city in enumerate(cities):
                try:
                    issues = GeographicDataIntegrityManager.validate_city_location_integrity(city)
                    results["cities"]["checked"] += 1

                    if issues:
                        results["cities"]["issues"] += 1
                        results["cities"]["details"].append(
                            {
                                "id": city.id,
                                "name": city.name,
                                "issues": issues,
                            }
                        )

                    # Update progress
                    if model_type == "cities":
                        task.progress = int((i + 1) / total_cities * 100)
                    else:
                        task.progress = 50 + int((i + 1) / total_cities * 50)  # Second 50%

                except Exception as e:
                    logger.error(f"Validation failed for city {city.id}: {e}")

        return results

    def _execute_delivery_cost_precomputation(self, task: BackgroundTask) -> Dict:
        """Pre-compute delivery costs for common routes."""
        payload = task.payload
        source_locations = payload.get("source_locations", [])
        destination_locations = payload.get("destination_locations", [])

        from geo.services import GeoProductFilterService

        filter_service = GeoProductFilterService()

        computed_routes = []
        total_combinations = len(source_locations) * len(destination_locations)
        processed = 0

        for source in source_locations:
            for dest in destination_locations:
                try:
                    # Create mock product for delivery calculation
                    mock_product = type(
                        "MockProduct", (), {"location": type("Point", (), {"y": source["lat"], "x": source["lon"]})()}
                    )()

                    delivery_info = filter_service.calculate_delivery_info(mock_product, dest["lat"], dest["lon"])

                    # Cache the result
                    cache_key = f"precomputed_delivery:{source['lat']}:{source['lon']}:{dest['lat']}:{dest['lon']}"
                    cache.set(cache_key, delivery_info, 86400)  # 24 hour cache

                    computed_routes.append(
                        {
                            "source": source,
                            "destination": dest,
                            "delivery_info": delivery_info,
                        }
                    )

                    processed += 1
                    task.progress = int(processed / total_combinations * 100)

                except Exception as e:
                    logger.warning(f"Delivery cost computation failed: {e}")

        return {
            "total_combinations": total_combinations,
            "successfully_computed": len(computed_routes),
            "cache_entries_created": len(computed_routes),
        }

    def _execute_geographic_zone_update(self, task: BackgroundTask) -> Dict:
        """Update geographic zones and related data."""
        payload = task.payload
        zone_updates = payload.get("zone_updates", [])

        from geo.models import GeographicZone

        updated_zones = []
        failed_updates = []

        for i, zone_update in enumerate(zone_updates):
            try:
                zone_id = zone_update["zone_id"]
                updates = zone_update["updates"]

                with transaction.atomic():
                    zone = GeographicZone.objects.get(id=zone_id)

                    for field, value in updates.items():
                        if hasattr(zone, field):
                            setattr(zone, field, value)

                    zone.save()

                updated_zones.append(zone_id)

                # Update progress
                task.progress = int((i + 1) / len(zone_updates) * 100)

            except Exception as e:
                logger.error(f"Zone update failed for {zone_update}: {e}")
                failed_updates.append(
                    {
                        "zone_update": zone_update,
                        "error": str(e),
                    }
                )

        # Invalidate related caches
        from market.advanced_caching import CacheInvalidationManager

        invalidator = CacheInvalidationManager()
        invalidator.cache_manager.invalidate_by_tags(["geo", "zones", "delivery"])

        return {
            "total_updates": len(zone_updates),
            "successful_updates": len(updated_zones),
            "failed_updates": len(failed_updates),
            "updated_zone_ids": updated_zones,
            "failures": failed_updates,
        }

    def _execute_producer_location_sync(self, task: BackgroundTask) -> Dict:
        """Synchronize producer locations with external data sources."""
        payload = task.payload
        producer_data = payload.get("producer_data", [])

        from producer.models import Producer

        synced_producers = []
        failed_syncs = []

        for i, data in enumerate(producer_data):
            try:
                producer_id = data["producer_id"]
                new_location = data.get("location")

                if new_location:
                    with transaction.atomic():
                        producer = Producer.objects.get(id=producer_id)

                        # Validate new location
                        from market.geographic_edge_cases import (
                            GeographicEdgeCaseHandler,
                        )

                        validation = GeographicEdgeCaseHandler.validate_coordinates_comprehensive(
                            new_location["latitude"], new_location["longitude"]
                        )

                        if validation["valid"]:
                            from django.contrib.gis.geos import Point

                            producer.location = Point(new_location["longitude"], new_location["latitude"], srid=4326)
                            producer.save()

                            synced_producers.append(producer_id)
                        else:
                            raise ValueError(f"Invalid coordinates: {validation['warnings']}")

                # Update progress
                task.progress = int((i + 1) / len(producer_data) * 100)

            except Exception as e:
                logger.error(f"Producer sync failed for {data}: {e}")
                failed_syncs.append(
                    {
                        "producer_data": data,
                        "error": str(e),
                    }
                )

        return {
            "total_producers": len(producer_data),
            "successfully_synced": len(synced_producers),
            "failed_syncs": len(failed_syncs),
            "synced_producer_ids": synced_producers,
            "failures": failed_syncs,
        }

    def _execute_analytics_processing(self, task: BackgroundTask) -> Dict:
        """Process location-based analytics."""
        payload = task.payload
        analytics_type = payload.get("type", "general")
        date_range = payload.get("date_range", {})

        results = {"type": analytics_type, "metrics": {}}

        try:
            if analytics_type == "distance_statistics":
                # Process distance calculation statistics
                results["metrics"] = self._process_distance_statistics(date_range, task)
            elif analytics_type == "zone_usage":
                # Process geographic zone usage statistics
                results["metrics"] = self._process_zone_usage_statistics(date_range, task)
            elif analytics_type == "delivery_patterns":
                # Process delivery pattern analytics
                results["metrics"] = self._process_delivery_patterns(date_range, task)

        except Exception as e:
            logger.error(f"Analytics processing failed: {e}")
            results["error"] = str(e)

        return results

    def _process_distance_statistics(self, date_range: Dict, task: BackgroundTask) -> Dict:
        """Process distance calculation statistics."""
        # This would analyze distance calculation patterns
        # Implementation depends on your specific analytics needs

        task.progress = 50

        stats = {
            "total_calculations": 0,
            "average_distance": 0.0,
            "max_distance": 0.0,
            "min_distance": 0.0,
            "distance_distribution": {},
        }

        task.progress = 100
        return stats

    def _process_zone_usage_statistics(self, date_range: Dict, task: BackgroundTask) -> Dict:
        """Process zone usage statistics."""
        task.progress = 50

        stats = {
            "most_accessed_zones": [],
            "zone_request_counts": {},
            "average_requests_per_zone": 0.0,
        }

        task.progress = 100
        return stats

    def _process_delivery_patterns(self, date_range: Dict, task: BackgroundTask) -> Dict:
        """Process delivery pattern analytics."""
        task.progress = 50

        patterns = {
            "popular_routes": [],
            "average_delivery_distance": 0.0,
            "delivery_cost_trends": {},
            "peak_delivery_times": [],
        }

        task.progress = 100
        return patterns

    def get_all_tasks(self, status_filter: Optional[TaskStatus] = None) -> List[Dict]:
        """Get all tasks, optionally filtered by status."""
        with self.task_lock:
            tasks = list(self.task_registry.values())

        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]

        return [self.get_task_status(task.task_id) for task in tasks]

    def cleanup_completed_tasks(self, older_than_hours: int = 24):
        """Clean up completed tasks older than specified hours."""
        cutoff_time = timezone.now() - timedelta(hours=older_than_hours)

        with self.task_lock:
            tasks_to_remove = []

            for task_id, task in self.task_registry.items():
                if (
                    task.status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED]
                    and task.completed_at
                    and task.completed_at < cutoff_time
                ):
                    tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                del self.task_registry[task_id]

        logger.info(f"Cleaned up {len(tasks_to_remove)} completed tasks")
        return len(tasks_to_remove)


# Global task manager instance
_task_manager = None


def get_task_manager() -> LocationBackgroundTaskManager:
    """Get global task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = LocationBackgroundTaskManager()
    return _task_manager


# Convenience functions for common background tasks
def start_bulk_distance_calculation(
    coordinates: List[Tuple[float, float, str]], center_lat: float, center_lon: float
) -> str:
    """Start bulk distance calculation task."""
    manager = get_task_manager()
    return manager.submit_task(
        "bulk_distance_calculation",
        {
            "coordinates": coordinates,
            "center_lat": center_lat,
            "center_lon": center_lon,
        },
        TaskPriority.NORMAL,
    )


def start_cache_warming(locations: List[Dict], radius_km: float = 50) -> str:
    """Start cache warming task."""
    manager = get_task_manager()
    return manager.submit_task(
        "cache_warming",
        {
            "locations": locations,
            "radius_km": radius_km,
        },
        TaskPriority.LOW,
    )


def start_location_validation(model_type: str = "all") -> str:
    """Start location data validation task."""
    manager = get_task_manager()
    return manager.submit_task("location_data_validation", {"model_type": model_type}, TaskPriority.HIGH)
