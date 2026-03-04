"""
Comprehensive monitoring and alerting system for location-based marketplace APIs.

Provides:
- Real-time metrics collection and aggregation
- Performance monitoring and SLA tracking  
- Alerting with multiple channels (email, Slack, webhook)
- Health checks and service availability monitoring
- Resource utilization tracking
- Error rate and latency monitoring
- Capacity planning metrics
- Custom dashboards and reporting
"""

import json
import logging
import queue
import smtplib
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import psutil
import requests
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics to track."""

    COUNTER = "counter"  # Incremental values (requests, errors)
    GAUGE = "gauge"  # Current state values (CPU, memory)
    HISTOGRAM = "histogram"  # Distribution of values (response times)
    TIMER = "timer"  # Duration measurements


@dataclass
class Metric:
    """Individual metric measurement."""

    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=timezone.now)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class Alert:
    """Alert definition and status."""

    alert_id: str
    name: str
    level: AlertLevel
    message: str
    threshold: float
    current_value: float
    tags: Dict[str, str] = field(default_factory=dict)
    triggered_at: datetime = field(default_factory=timezone.now)
    acknowledged: bool = False
    resolved: bool = False


class MetricsCollector:
    """
    Collects and aggregates metrics for location-based operations.
    """

    def __init__(self):
        self.metrics = defaultdict(deque)  # Store recent metrics per name
        self.metric_locks = defaultdict(threading.Lock)
        self.max_history = 1000  # Keep last 1000 measurements per metric
        self.aggregation_window = 60  # Aggregate over 60 seconds

    def record_metric(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None, metric_type: MetricType = MetricType.GAUGE
    ):
        """Record a metric measurement."""
        metric = Metric(name=name, value=value, tags=tags or {}, metric_type=metric_type)

        with self.metric_locks[name]:
            self.metrics[name].append(metric)

            # Maintain max history
            while len(self.metrics[name]) > self.max_history:
                self.metrics[name].popleft()

    def get_metric_stats(self, metric_name: str, window_seconds: Optional[int] = None) -> Dict:
        """Get statistical summary of a metric."""
        window_seconds = window_seconds or self.aggregation_window
        cutoff_time = timezone.now() - timedelta(seconds=window_seconds)

        with self.metric_locks[metric_name]:
            recent_metrics = [m for m in self.metrics[metric_name] if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return {}

        values = [m.value for m in recent_metrics]

        stats = {
            "count": len(values),
            "sum": sum(values),
            "avg": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "latest": values[-1] if values else 0,
            "window_seconds": window_seconds,
        }

        # Add percentiles for distributions
        if len(values) >= 2:
            sorted_values = sorted(values)
            stats.update(
                {
                    "median": statistics.median(sorted_values),
                    "p95": sorted_values[int(len(sorted_values) * 0.95)],
                    "p99": sorted_values[int(len(sorted_values) * 0.99)],
                    "stddev": statistics.stdev(values) if len(values) > 1 else 0,
                }
            )

        return stats

    def get_all_metrics(self) -> Dict[str, Dict]:
        """Get stats for all metrics."""
        all_stats = {}

        for metric_name in list(self.metrics.keys()):
            all_stats[metric_name] = self.get_metric_stats(metric_name)

        return all_stats


class PerformanceMonitor:
    """
    Monitors performance metrics for location-based operations.
    """

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.active_requests = {}
        self.request_lock = threading.Lock()

    def start_request_tracking(self, request_id: str, endpoint: str, user_location: Optional[Dict] = None):
        """Start tracking a request."""
        with self.request_lock:
            self.active_requests[request_id] = {
                "endpoint": endpoint,
                "start_time": time.time(),
                "user_location": user_location,
            }

        # Record request start
        self.metrics.record_metric("requests_started", 1, {"endpoint": endpoint}, MetricType.COUNTER)

    def end_request_tracking(
        self, request_id: str, status_code: int, response_size: Optional[int] = None, error: Optional[str] = None
    ):
        """End tracking a request."""
        with self.request_lock:
            request_info = self.active_requests.pop(request_id, None)

        if not request_info:
            return

        duration = time.time() - request_info["start_time"]
        endpoint = request_info["endpoint"]

        # Record metrics
        tags = {"endpoint": endpoint, "status": str(status_code)}

        self.metrics.record_metric("request_duration_seconds", duration, tags, MetricType.HISTOGRAM)

        self.metrics.record_metric("requests_completed", 1, tags, MetricType.COUNTER)

        # Record errors
        if status_code >= 400:
            self.metrics.record_metric("request_errors", 1, {**tags, "error_type": error or "unknown"}, MetricType.COUNTER)

        # Record response size
        if response_size:
            self.metrics.record_metric("response_size_bytes", response_size, tags, MetricType.HISTOGRAM)

    def record_database_operation(self, operation: str, duration: float, query_count: int = 1):
        """Record database operation metrics."""
        self.metrics.record_metric("db_operation_duration_seconds", duration, {"operation": operation}, MetricType.HISTOGRAM)

        self.metrics.record_metric("db_queries_count", query_count, {"operation": operation}, MetricType.COUNTER)

    def record_cache_operation(self, operation: str, hit: bool, duration: float):
        """Record cache operation metrics."""
        self.metrics.record_metric(
            "cache_operation_duration_seconds", duration, {"operation": operation}, MetricType.HISTOGRAM
        )

        self.metrics.record_metric("cache_hits" if hit else "cache_misses", 1, {"operation": operation}, MetricType.COUNTER)


class ResourceMonitor:
    """
    Monitors system resources and capacity.
    """

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.monitoring = False
        self.monitor_thread = None
        self.collection_interval = 10  # seconds

    def start_monitoring(self):
        """Start resource monitoring."""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Resource monitoring started")

    def stop_monitoring(self):
        """Stop resource monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Resource monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.monitoring:
            try:
                self._collect_system_metrics()
                self._collect_database_metrics()
                self._collect_cache_metrics()
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(self.collection_interval)

    def _collect_system_metrics(self):
        """Collect system-level metrics."""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        self.metrics.record_metric("system_cpu_percent", cpu_percent)

        # Memory usage
        memory = psutil.virtual_memory()
        self.metrics.record_metric("system_memory_percent", memory.percent)
        self.metrics.record_metric("system_memory_available_mb", memory.available / 1024 / 1024)

        # Disk usage
        disk = psutil.disk_usage("/")
        self.metrics.record_metric("system_disk_percent", (disk.used / disk.total) * 100)

        # Network I/O
        network = psutil.net_io_counters()
        self.metrics.record_metric("system_network_bytes_sent", network.bytes_sent, metric_type=MetricType.COUNTER)
        self.metrics.record_metric("system_network_bytes_recv", network.bytes_recv, metric_type=MetricType.COUNTER)

        # Active connections
        connections = len(psutil.net_connections(kind="tcp"))
        self.metrics.record_metric("system_tcp_connections", connections)

    def _collect_database_metrics(self):
        """Collect database metrics."""
        try:
            with connection.cursor() as cursor:
                # Active connections
                cursor.execute(
                    """
                    SELECT count(*) FROM pg_stat_activity 
                    WHERE state = 'active'
                """
                )
                active_connections = cursor.fetchone()[0]
                self.metrics.record_metric("db_active_connections", active_connections)

                # Database size
                cursor.execute(
                    """
                    SELECT pg_database_size(current_database())
                """
                )
                db_size_bytes = cursor.fetchone()[0]
                self.metrics.record_metric("db_size_mb", db_size_bytes / 1024 / 1024)

        except Exception as e:
            logger.error(f"Database metrics collection error: {e}")

    def _collect_cache_metrics(self):
        """Collect cache metrics."""
        try:
            # Redis metrics (if using Redis)
            redis_info = cache._cache.get_client().info()

            self.metrics.record_metric("cache_used_memory_mb", redis_info.get("used_memory", 0) / 1024 / 1024)

            self.metrics.record_metric("cache_connected_clients", redis_info.get("connected_clients", 0))

            self.metrics.record_metric(
                "cache_keyspace_hits", redis_info.get("keyspace_hits", 0), metric_type=MetricType.COUNTER
            )

            self.metrics.record_metric(
                "cache_keyspace_misses", redis_info.get("keyspace_misses", 0), metric_type=MetricType.COUNTER
            )

        except Exception as e:
            logger.error(f"Cache metrics collection error: {e}")


class AlertManager:
    """
    Manages alerts and notifications.
    """

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.alert_rules = []
        self.active_alerts = {}
        self.alert_channels = []
        self.check_interval = 30  # seconds
        self.checking = False
        self.check_thread = None

    def add_alert_rule(
        self,
        name: str,
        metric_name: str,
        threshold: float,
        condition: str,
        level: AlertLevel = AlertLevel.WARNING,
        cooldown_minutes: int = 5,
        tags: Optional[Dict] = None,
    ):
        """
        Add an alert rule.

        Args:
            name: Human-readable alert name
            metric_name: Name of metric to monitor
            threshold: Alert threshold value
            condition: Condition ('>', '<', '>=', '<=', '==', '!=')
            level: Alert severity level
            cooldown_minutes: Minutes to wait before re-alerting
            tags: Optional tags to filter metrics
        """
        rule = {
            "name": name,
            "metric_name": metric_name,
            "threshold": threshold,
            "condition": condition,
            "level": level,
            "cooldown_minutes": cooldown_minutes,
            "tags": tags or {},
            "last_triggered": None,
        }

        self.alert_rules.append(rule)
        logger.info(f"Added alert rule: {name}")

    def add_notification_channel(self, channel_type: str, config: Dict):
        """
        Add a notification channel.

        Args:
            channel_type: 'email', 'slack', 'webhook'
            config: Channel-specific configuration
        """
        channel = {
            "type": channel_type,
            "config": config,
        }

        self.alert_channels.append(channel)
        logger.info(f"Added notification channel: {channel_type}")

    def start_monitoring(self):
        """Start alert monitoring."""
        if self.checking:
            return

        self.checking = True
        self.check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.check_thread.start()
        logger.info("Alert monitoring started")

    def stop_monitoring(self):
        """Stop alert monitoring."""
        self.checking = False
        if self.check_thread:
            self.check_thread.join(timeout=5)
        logger.info("Alert monitoring stopped")

    def _check_loop(self):
        """Main alert checking loop."""
        while self.checking:
            try:
                self._check_alert_rules()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Alert checking error: {e}")
                time.sleep(self.check_interval)

    def _check_alert_rules(self):
        """Check all alert rules against current metrics."""
        for rule in self.alert_rules:
            try:
                self._check_single_rule(rule)
            except Exception as e:
                logger.error(f"Error checking rule {rule['name']}: {e}")

    def _check_single_rule(self, rule: Dict):
        """Check a single alert rule."""
        metric_stats = self.metrics.get_metric_stats(rule["metric_name"])

        if not metric_stats:
            return  # No data available

        current_value = metric_stats.get("latest", 0)
        threshold = rule["threshold"]
        condition = rule["condition"]

        # Evaluate condition
        triggered = False
        if condition == ">":
            triggered = current_value > threshold
        elif condition == "<":
            triggered = current_value < threshold
        elif condition == ">=":
            triggered = current_value >= threshold
        elif condition == "<=":
            triggered = current_value <= threshold
        elif condition == "==":
            triggered = current_value == threshold
        elif condition == "!=":
            triggered = current_value != threshold

        if triggered:
            self._handle_triggered_alert(rule, current_value, metric_stats)
        else:
            self._handle_resolved_alert(rule)

    def _handle_triggered_alert(self, rule: Dict, current_value: float, metric_stats: Dict):
        """Handle a triggered alert."""
        rule_name = rule["name"]

        # Check cooldown
        if rule["last_triggered"]:
            cooldown = timedelta(minutes=rule["cooldown_minutes"])
            if timezone.now() - rule["last_triggered"] < cooldown:
                return  # Still in cooldown

        # Create alert
        alert_id = f"{rule_name}_{int(time.time())}"
        alert = Alert(
            alert_id=alert_id,
            name=rule_name,
            level=rule["level"],
            message=self._format_alert_message(rule, current_value, metric_stats),
            threshold=rule["threshold"],
            current_value=current_value,
            tags=rule["tags"],
        )

        self.active_alerts[alert_id] = alert
        rule["last_triggered"] = timezone.now()

        # Send notifications
        self._send_notifications(alert)

        logger.warning(f"Alert triggered: {alert.name} - {alert.message}")

    def _handle_resolved_alert(self, rule: Dict):
        """Handle alert resolution."""
        # Mark matching alerts as resolved
        for alert_id, alert in self.active_alerts.items():
            if alert.name == rule["name"] and not alert.resolved:
                alert.resolved = True
                logger.info(f"Alert resolved: {alert.name}")

    def _format_alert_message(self, rule: Dict, current_value: float, metric_stats: Dict) -> str:
        """Format alert message."""
        return (
            f"Metric '{rule['metric_name']}' {rule['condition']} {rule['threshold']} "
            f"(current: {current_value:.2f}, avg: {metric_stats.get('avg', 0):.2f})"
        )

    def _send_notifications(self, alert: Alert):
        """Send alert notifications to all channels."""
        for channel in self.alert_channels:
            try:
                if channel["type"] == "email":
                    self._send_email_notification(alert, channel["config"])
                elif channel["type"] == "slack":
                    self._send_slack_notification(alert, channel["config"])
                elif channel["type"] == "webhook":
                    self._send_webhook_notification(alert, channel["config"])
            except Exception as e:
                logger.error(f"Failed to send {channel['type']} notification: {e}")

    def _send_email_notification(self, alert: Alert, config: Dict):
        """Send email notification."""
        smtp_server = config.get("smtp_server", "localhost")
        smtp_port = config.get("smtp_port", 587)
        username = config.get("username")
        password = config.get("password")
        to_emails = config.get("to_emails", [])

        if not to_emails:
            return

        msg = MIMEMultipart()
        msg["From"] = config.get("from_email", "alerts@example.com")
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = f"[{alert.level.value.upper()}] {alert.name}"

        body = f"""
Alert: {alert.name}
Level: {alert.level.value}
Message: {alert.message}
Triggered: {alert.triggered_at.isoformat()}
Current Value: {alert.current_value}
Threshold: {alert.threshold}
        """

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if username:
                server.starttls()
                server.login(username, password)
            server.send_message(msg)

    def _send_slack_notification(self, alert: Alert, config: Dict):
        """Send Slack notification."""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            return

        color = {
            AlertLevel.INFO: "good",
            AlertLevel.WARNING: "warning",
            AlertLevel.CRITICAL: "danger",
        }.get(alert.level, "warning")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"[{alert.level.value.upper()}] {alert.name}",
                    "text": alert.message,
                    "fields": [
                        {"title": "Current Value", "value": str(alert.current_value), "short": True},
                        {"title": "Threshold", "value": str(alert.threshold), "short": True},
                        {"title": "Time", "value": alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S"), "short": False},
                    ],
                    "ts": int(alert.triggered_at.timestamp()),
                }
            ]
        }

        requests.post(webhook_url, json=payload, timeout=10)

    def _send_webhook_notification(self, alert: Alert, config: Dict):
        """Send webhook notification."""
        url = config.get("url")
        if not url:
            return

        payload = {
            "alert_id": alert.alert_id,
            "name": alert.name,
            "level": alert.level.value,
            "message": alert.message,
            "current_value": alert.current_value,
            "threshold": alert.threshold,
            "triggered_at": alert.triggered_at.isoformat(),
            "tags": alert.tags,
        }

        headers = config.get("headers", {})
        requests.post(url, json=payload, headers=headers, timeout=10)


class HealthChecker:
    """
    Health checks for location-based services.
    """

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.health_checks = {}

    def register_check(
        self, name: str, check_function: Callable[[], Dict], interval_seconds: int = 60, timeout_seconds: int = 30
    ):
        """
        Register a health check.

        Args:
            name: Health check name
            check_function: Function that returns health status dict
            interval_seconds: How often to run the check
            timeout_seconds: Timeout for the check
        """
        self.health_checks[name] = {
            "function": check_function,
            "interval": interval_seconds,
            "timeout": timeout_seconds,
            "last_run": None,
            "last_result": None,
        }

    def run_check(self, check_name: str) -> Dict:
        """Run a specific health check."""
        if check_name not in self.health_checks:
            return {"status": "error", "message": f"Health check {check_name} not found"}

        check = self.health_checks[check_name]

        try:
            start_time = time.time()
            result = check["function"]()
            duration = time.time() - start_time

            # Record metrics
            self.metrics.record_metric(
                "health_check_duration_seconds", duration, {"check_name": check_name}, MetricType.HISTOGRAM
            )

            status = result.get("status", "unknown")
            self.metrics.record_metric(
                "health_check_status", 1 if status == "healthy" else 0, {"check_name": check_name, "status": status}
            )

            check["last_run"] = timezone.now()
            check["last_result"] = result

            return result

        except Exception as e:
            logger.error(f"Health check {check_name} failed: {e}")

            result = {
                "status": "error",
                "message": str(e),
                "check_name": check_name,
            }

            check["last_result"] = result
            return result

    def run_all_checks(self) -> Dict[str, Dict]:
        """Run all health checks."""
        results = {}

        for check_name in self.health_checks:
            results[check_name] = self.run_check(check_name)

        return results


class MonitoringDashboard:
    """
    Provides dashboard data for monitoring UI.
    """

    def __init__(
        self,
        metrics_collector: MetricsCollector,
        performance_monitor: PerformanceMonitor,
        resource_monitor: ResourceMonitor,
        alert_manager: AlertManager,
        health_checker: HealthChecker,
    ):
        self.metrics = metrics_collector
        self.performance = performance_monitor
        self.resources = resource_monitor
        self.alerts = alert_manager
        self.health = health_checker

    def get_overview(self) -> Dict:
        """Get overview dashboard data."""
        # Request metrics
        request_stats = self.metrics.get_metric_stats("requests_completed", 300)  # 5 minute window
        error_stats = self.metrics.get_metric_stats("request_errors", 300)

        request_rate = request_stats.get("sum", 0) / 5  # requests per minute
        error_rate = error_stats.get("sum", 0) / max(request_stats.get("sum", 1), 1) * 100

        # Response time metrics
        latency_stats = self.metrics.get_metric_stats("request_duration_seconds", 300)
        avg_latency = latency_stats.get("avg", 0) * 1000  # Convert to ms
        p95_latency = latency_stats.get("p95", 0) * 1000

        # System metrics
        cpu_stats = self.metrics.get_metric_stats("system_cpu_percent")
        memory_stats = self.metrics.get_metric_stats("system_memory_percent")

        # Active alerts
        active_alerts = len([a for a in self.alerts.active_alerts.values() if not a.resolved])

        return {
            "timestamp": timezone.now().isoformat(),
            "requests_per_minute": round(request_rate, 2),
            "error_rate_percent": round(error_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "cpu_usage_percent": cpu_stats.get("latest", 0),
            "memory_usage_percent": memory_stats.get("latest", 0),
            "active_alerts": active_alerts,
            "status": "healthy" if active_alerts == 0 and error_rate < 5 else "warning",
        }

    def get_detailed_metrics(self) -> Dict:
        """Get detailed metrics data."""
        return {
            "timestamp": timezone.now().isoformat(),
            "requests": self._get_request_metrics(),
            "database": self._get_database_metrics(),
            "cache": self._get_cache_metrics(),
            "system": self._get_system_metrics(),
            "alerts": self._get_alert_metrics(),
        }

    def _get_request_metrics(self) -> Dict:
        """Get request-related metrics."""
        return {
            "completed": self.metrics.get_metric_stats("requests_completed", 3600),
            "errors": self.metrics.get_metric_stats("request_errors", 3600),
            "duration": self.metrics.get_metric_stats("request_duration_seconds", 3600),
        }

    def _get_database_metrics(self) -> Dict:
        """Get database-related metrics."""
        return {
            "connections": self.metrics.get_metric_stats("db_active_connections"),
            "operations": self.metrics.get_metric_stats("db_operation_duration_seconds", 3600),
            "queries": self.metrics.get_metric_stats("db_queries_count", 3600),
        }

    def _get_cache_metrics(self) -> Dict:
        """Get cache-related metrics."""
        return {
            "hits": self.metrics.get_metric_stats("cache_hits", 3600),
            "misses": self.metrics.get_metric_stats("cache_misses", 3600),
            "memory": self.metrics.get_metric_stats("cache_used_memory_mb"),
        }

    def _get_system_metrics(self) -> Dict:
        """Get system-related metrics."""
        return {
            "cpu": self.metrics.get_metric_stats("system_cpu_percent"),
            "memory": self.metrics.get_metric_stats("system_memory_percent"),
            "disk": self.metrics.get_metric_stats("system_disk_percent"),
            "network_sent": self.metrics.get_metric_stats("system_network_bytes_sent", 3600),
            "network_recv": self.metrics.get_metric_stats("system_network_bytes_recv", 3600),
        }

    def _get_alert_metrics(self) -> Dict:
        """Get alert-related metrics."""
        active_alerts = [a for a in self.alerts.active_alerts.values() if not a.resolved]

        by_level = defaultdict(int)
        for alert in active_alerts:
            by_level[alert.level.value] += 1

        return {
            "total_active": len(active_alerts),
            "by_level": dict(by_level),
            "recent": [
                {
                    "id": alert.alert_id,
                    "name": alert.name,
                    "level": alert.level.value,
                    "message": alert.message,
                    "triggered_at": alert.triggered_at.isoformat(),
                }
                for alert in sorted(active_alerts, key=lambda a: a.triggered_at, reverse=True)[:10]
            ],
        }


# Global monitoring instances
_metrics_collector = None
_performance_monitor = None
_resource_monitor = None
_alert_manager = None
_health_checker = None
_dashboard = None


def get_monitoring_components():
    """Get global monitoring component instances."""
    global _metrics_collector, _performance_monitor, _resource_monitor
    global _alert_manager, _health_checker, _dashboard

    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
        _performance_monitor = PerformanceMonitor(_metrics_collector)
        _resource_monitor = ResourceMonitor(_metrics_collector)
        _alert_manager = AlertManager(_metrics_collector)
        _health_checker = HealthChecker(_metrics_collector)
        _dashboard = MonitoringDashboard(
            _metrics_collector, _performance_monitor, _resource_monitor, _alert_manager, _health_checker
        )

    return (_metrics_collector, _performance_monitor, _resource_monitor, _alert_manager, _health_checker, _dashboard)


def setup_default_alerts():
    """Setup default alert rules."""
    _, _, _, alert_manager, _, _ = get_monitoring_components()

    # High error rate
    alert_manager.add_alert_rule(
        name="High Error Rate",
        metric_name="request_errors",
        threshold=10,  # 10 errors per minute
        condition=">",
        level=AlertLevel.WARNING,
    )

    # High response time
    alert_manager.add_alert_rule(
        name="High Response Time",
        metric_name="request_duration_seconds",
        threshold=2.0,  # 2 seconds average
        condition=">",
        level=AlertLevel.WARNING,
    )

    # High CPU usage
    alert_manager.add_alert_rule(
        name="High CPU Usage", metric_name="system_cpu_percent", threshold=80, condition=">", level=AlertLevel.WARNING
    )

    # High memory usage
    alert_manager.add_alert_rule(
        name="High Memory Usage", metric_name="system_memory_percent", threshold=90, condition=">", level=AlertLevel.CRITICAL
    )

    # Database connection issues
    alert_manager.add_alert_rule(
        name="High DB Connections",
        metric_name="db_active_connections",
        threshold=180,  # 90% of max 200
        condition=">",
        level=AlertLevel.WARNING,
    )


def setup_default_health_checks():
    """Setup default health checks."""
    _, _, _, _, health_checker, _ = get_monitoring_components()

    def database_health_check():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return {"status": "healthy", "message": "Database connection OK"}
        except Exception as e:
            return {"status": "unhealthy", "message": f"Database error: {e}"}

    def cache_health_check():
        try:
            cache.set("health_check", "test", 10)
            result = cache.get("health_check")
            if result == "test":
                return {"status": "healthy", "message": "Cache operational"}
            else:
                return {"status": "unhealthy", "message": "Cache read/write failed"}
        except Exception as e:
            return {"status": "unhealthy", "message": f"Cache error: {e}"}

    health_checker.register_check("database", database_health_check, 30)
    health_checker.register_check("cache", cache_health_check, 30)


def start_monitoring():
    """Start all monitoring components."""
    _, _, resource_monitor, alert_manager, _, _ = get_monitoring_components()

    # Setup defaults
    setup_default_alerts()
    setup_default_health_checks()

    # Start monitoring
    resource_monitor.start_monitoring()
    alert_manager.start_monitoring()

    logger.info("Location-based marketplace monitoring started")


def stop_monitoring():
    """Stop all monitoring components."""
    _, _, resource_monitor, alert_manager, _, _ = get_monitoring_components()

    resource_monitor.stop_monitoring()
    alert_manager.stop_monitoring()

    logger.info("Location-based marketplace monitoring stopped")
