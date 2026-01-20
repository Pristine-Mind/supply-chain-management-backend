import logging
import uuid

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class SupplierScorecard(models.Model):
    """
    Supplier health scorecard with weighted performance metrics.

    Updated daily at midnight via Celery task.
    One record per supplier containing latest calculated scores.
    """

    supplier = models.OneToOneField(
        "producer.Producer",
        on_delete=models.CASCADE,
        related_name="scorecard",
        verbose_name=_("Supplier"),
        help_text=_("Producer/Supplier entity"),
    )

    # Score Metrics (0-100 scale)
    on_time_delivery_pct = models.FloatField(
        default=0, verbose_name=_("On-Time Delivery %"), help_text=_("Percentage of orders delivered on-time")
    )
    quality_performance_pct = models.FloatField(
        default=100, verbose_name=_("Quality Performance %"), help_text=_("100% - defect_rate")
    )
    lead_time_consistency_pct = models.FloatField(
        default=100, verbose_name=_("Lead Time Consistency %"), help_text=_("Consistency rating of lead times")
    )
    payment_reliability_pct = models.FloatField(
        default=100, verbose_name=_("Payment Reliability %"), help_text=_("On-time payment percentage")
    )

    # Weighted Health Score
    health_score = models.FloatField(default=80, verbose_name=_("Health Score"), help_text=_("Weighted average (0-100)"))
    health_status = models.CharField(
        max_length=20,
        choices=[
            ("healthy", _("Healthy (80-100)")),
            ("monitor", _("Monitor (60-79)")),
            ("critical", _("Critical (0-59)")),
        ],
        default="healthy",
        verbose_name=_("Health Status"),
    )

    # Supporting Metrics
    total_orders = models.IntegerField(default=0, verbose_name=_("Total Orders"), help_text=_("Orders in 90-day window"))
    on_time_orders = models.IntegerField(default=0, verbose_name=_("On-Time Orders"))
    defect_count = models.IntegerField(default=0, verbose_name=_("Defect Count"))
    avg_lead_time_days = models.FloatField(default=0, verbose_name=_("Average Lead Time (days)"))
    lead_time_variance = models.FloatField(
        default=0, verbose_name=_("Lead Time Variance"), help_text=_("Standard deviation of lead times")
    )
    late_payments_count = models.IntegerField(default=0, verbose_name=_("Late Payments Count"))

    # Timestamps
    last_calculated = models.DateTimeField(auto_now=True, verbose_name=_("Last Calculated"))
    calculation_period_start = models.DateField(
        verbose_name=_("Calculation Period Start"), help_text=_("Start of 90-day evaluation window")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Supplier Scorecard")
        verbose_name_plural = _("Supplier Scorecards")
        indexes = [
            models.Index(fields=["supplier"]),
            models.Index(fields=["health_status"]),
            models.Index(fields=["last_calculated"]),
        ]

    def __str__(self):
        return f"Scorecard: {self.supplier.name} ({self.health_score:.1f})"

    @property
    def is_healthy(self):
        """Check if supplier is in healthy status."""
        return self.health_status == "healthy"

    @property
    def is_critical(self):
        """Check if supplier is in critical status."""
        return self.health_status == "critical"


class SupplierScoreHistory(models.Model):
    """
    Historical snapshots of supplier health scores.

    Retains 90 days of history for trend analysis.
    One record per day per supplier.
    """

    supplier = models.ForeignKey(
        "producer.Producer", on_delete=models.CASCADE, related_name="score_history", verbose_name=_("Supplier")
    )
    health_score = models.FloatField(verbose_name=_("Health Score"))
    health_status = models.CharField(
        max_length=20,
        choices=[
            ("healthy", _("Healthy")),
            ("monitor", _("Monitor")),
            ("critical", _("Critical")),
        ],
        verbose_name=_("Health Status"),
    )
    on_time_delivery_pct = models.FloatField(default=0, verbose_name=_("On-Time Delivery %"))
    quality_performance_pct = models.FloatField(default=100, verbose_name=_("Quality Performance %"))
    lead_time_consistency_pct = models.FloatField(default=100, verbose_name=_("Lead Time Consistency %"))
    recorded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Recorded At"))

    class Meta:
        verbose_name = _("Supplier Score History")
        verbose_name_plural = _("Supplier Score Histories")
        indexes = [
            models.Index(fields=["supplier", "recorded_at"]),
            models.Index(fields=["recorded_at"]),
        ]
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.supplier.name}: {self.health_score:.1f} ({self.recorded_at.date()})"


class ProductDefectRecord(models.Model):
    """
    Tracks product defects, quality issues, and returns.

    Used to calculate quality performance metrics for suppliers.
    """

    DEFECT_TYPE_CHOICES = [
        ("quality", _("Quality Issue")),
        ("damage", _("Damage")),
        ("missing_items", _("Missing Items")),
        ("other", _("Other")),
    ]

    RESOLUTION_STATUS_CHOICES = [
        ("open", _("Open")),
        ("resolved", _("Resolved")),
        ("escalated", _("Escalated")),
    ]

    product = models.ForeignKey(
        "producer.Product", on_delete=models.CASCADE, related_name="defect_records", verbose_name=_("Product")
    )
    supplier = models.ForeignKey(
        "producer.Producer", on_delete=models.CASCADE, related_name="defect_records", verbose_name=_("Supplier")
    )
    order = models.ForeignKey(
        "producer.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="defect_records",
        verbose_name=_("Related Order"),
    )
    defect_type = models.CharField(max_length=50, choices=DEFECT_TYPE_CHOICES, verbose_name=_("Defect Type"))
    quantity_defective = models.IntegerField(verbose_name=_("Quantity Defective"))
    description = models.TextField(verbose_name=_("Description"))
    resolution_status = models.CharField(
        max_length=20, choices=RESOLUTION_STATUS_CHOICES, default="open", verbose_name=_("Resolution Status")
    )
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Resolved At"))
    resolution_notes = models.TextField(blank=True, verbose_name=_("Resolution Notes"))
    defect_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Defect Date"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Product Defect Record")
        verbose_name_plural = _("Product Defect Records")
        indexes = [
            models.Index(fields=["supplier", "defect_date"]),
            models.Index(fields=["product", "resolution_status"]),
            models.Index(fields=["defect_type"]),
        ]
        ordering = ["-defect_date"]

    def __str__(self):
        return f"{self.product.name}: {self.defect_type} (x{self.quantity_defective})"


class SupplyChainKPI(models.Model):
    """
    Key Performance Indicator snapshots captured at regular intervals.

    Created every 6 hours. Supports per-supplier and global metrics.
    """

    supplier = models.ForeignKey(
        "producer.Producer",
        on_delete=models.CASCADE,
        related_name="kpi_snapshots",
        null=True,
        blank=True,
        verbose_name=_("Supplier"),
        help_text=_("NULL = global/aggregate KPIs"),
    )

    # OTIF Rate (On-Time In-Full)
    otif_rate = models.FloatField(default=0, verbose_name=_("OTIF Rate %"))
    otif_previous = models.FloatField(default=0, verbose_name=_("OTIF Previous %"))
    otif_trend_pct = models.FloatField(default=0, verbose_name=_("OTIF Trend %"))

    # Lead Time Variability
    lead_time_variability = models.FloatField(
        default=0, verbose_name=_("Lead Time Variability (days)"), help_text=_("Standard deviation")
    )
    lead_time_avg = models.FloatField(default=0, verbose_name=_("Average Lead Time (days)"))
    lead_time_trend = models.FloatField(default=0, verbose_name=_("Lead Time Trend (days)"))

    # Inventory Turnover
    inventory_turnover_ratio = models.FloatField(default=0, verbose_name=_("Inventory Turnover Ratio"))
    inventory_turnover_previous = models.FloatField(default=0, verbose_name=_("Inventory Turnover Previous"))
    inventory_trend_pct = models.FloatField(default=0, verbose_name=_("Inventory Trend %"))

    # Additional Metrics
    stock_out_incidents = models.IntegerField(default=0, verbose_name=_("Stock Out Incidents"))
    low_stock_items_count = models.IntegerField(default=0, verbose_name=_("Low Stock Items Count"))
    orders_pending_count = models.IntegerField(default=0, verbose_name=_("Pending Orders Count"))
    orders_delayed_count = models.IntegerField(default=0, verbose_name=_("Delayed Orders Count"))

    # Metadata
    period_start = models.DateField(verbose_name=_("Period Start"))
    period_end = models.DateField(verbose_name=_("Period End"))
    snapshot_date = models.DateField(auto_now_add=True, verbose_name=_("Snapshot Date"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Supply Chain KPI")
        verbose_name_plural = _("Supply Chain KPIs")
        indexes = [
            models.Index(fields=["supplier", "snapshot_date"]),
            models.Index(fields=["snapshot_date"]),
        ]
        ordering = ["-snapshot_date"]
        get_latest_by = "snapshot_date"

    def __str__(self):
        supplier_name = self.supplier.name if self.supplier else "Global"
        return f"KPI - {supplier_name} ({self.snapshot_date})"


class AlertThreshold(models.Model):
    """
    Configurable thresholds for alert generation.

    Allows admins to tune alert sensitivity per alert type.
    """

    ALERT_TYPE_CHOICES = [
        ("supplier_health", _("Supplier Health Alert")),
        ("otif", _("OTIF Rate Alert")),
        ("lead_time", _("Lead Time Alert")),
        ("stock_low", _("Low Stock Alert")),
        ("stock_out", _("Stock Out Alert")),
        ("delayed_order", _("Delayed Order")),
        ("quality_issue", _("Quality Issue")),
        ("inventory_variance", _("Inventory Variance")),
    ]

    alert_type = models.CharField(max_length=50, unique=True, choices=ALERT_TYPE_CHOICES, verbose_name=_("Alert Type"))

    # Critical threshold
    critical_threshold = models.FloatField(
        verbose_name=_("Critical Threshold"), help_text=_("Value that triggers CRITICAL alert")
    )
    critical_enabled = models.BooleanField(default=True, verbose_name=_("Critical Enabled"))

    # Warning threshold
    warning_threshold = models.FloatField(
        verbose_name=_("Warning Threshold"), help_text=_("Value that triggers WARNING alert")
    )
    warning_enabled = models.BooleanField(default=True, verbose_name=_("Warning Enabled"))

    # Check frequency
    check_frequency_minutes = models.IntegerField(
        default=120, verbose_name=_("Check Frequency (minutes)"), help_text=_("How often to check this threshold")
    )

    # Auto-resolve window
    auto_resolve_hours = models.IntegerField(
        default=24,
        verbose_name=_("Auto-Resolve Window (hours)"),
        help_text=_("Auto-resolve if condition normalizes for N hours"),
    )

    # Description for UI
    description = models.TextField(blank=True, verbose_name=_("Description"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Alert Threshold Configuration")
        verbose_name_plural = _("Alert Threshold Configurations")

    def __str__(self):
        return f"Thresholds for {self.get_alert_type_display()}"


class SupplyChainAlert(models.Model):
    """
    Automated supply chain risk alerts with tracking and management.

    Generated by scheduled Celery tasks. Supports acknowledgement,
    resolution, and auto-resolution.
    """

    ALERT_TYPE_CHOICES = [
        ("supplier_health", _("Supplier Health Alert")),
        ("otif", _("OTIF Rate Alert")),
        ("lead_time", _("Lead Time Alert")),
        ("stock_low", _("Low Stock Alert")),
        ("stock_out", _("Stock Out Alert")),
        ("delayed_order", _("Delayed Order")),
        ("quality_issue", _("Quality Issue")),
        ("inventory_variance", _("Inventory Variance")),
    ]

    SEVERITY_CHOICES = [
        ("critical", _("Critical - Immediate Action")),
        ("warning", _("Warning - Review Soon")),
        ("info", _("Info - FYI")),
    ]

    STATUS_CHOICES = [
        ("active", _("Active")),
        ("acknowledged", _("Acknowledged")),
        ("resolved", _("Resolved")),
        ("auto_resolved", _("Auto-Resolved")),
    ]

    # Identification
    alert_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name=_("Alert ID"))
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPE_CHOICES, verbose_name=_("Alert Type"), db_index=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, verbose_name=_("Severity"), db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active", verbose_name=_("Status"), db_index=True
    )

    # Content
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    description = models.TextField(verbose_name=_("Description"))

    # Context (generic FK for flexibility)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("Content Type")
    )
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Object ID"))
    related_object = GenericForeignKey("content_type", "object_id")

    # Supplier/Product affected
    supplier = models.ForeignKey(
        "producer.Producer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="supply_chain_alerts",
        verbose_name=_("Supplier"),
    )
    product = models.ForeignKey(
        "producer.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
        verbose_name=_("Product"),
    )

    # Metric values
    metric_value = models.FloatField(null=True, blank=True, verbose_name=_("Metric Value"))
    threshold_value = models.FloatField(null=True, blank=True, verbose_name=_("Threshold Value"))

    # Timeline
    triggered_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Triggered At"), db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Acknowledged At"))
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Resolved At"))
    auto_resolve_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Auto-Resolve At"),
        help_text=_("Alert automatically resolved if condition normalizes for 24 hours"),
    )

    # Recipient
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Assigned To"))

    # Metadata
    metadata = models.JSONField(
        default=dict, verbose_name=_("Metadata"), help_text=_("Additional context (previous_value, trend, etc.)")
    )
    is_notified = models.BooleanField(default=False, verbose_name=_("Is Notified"))
    notification_channels = models.JSONField(
        default=list, verbose_name=_("Notification Channels"), help_text=_("['email', 'push', 'in_app']")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Supply Chain Alert")
        verbose_name_plural = _("Supply Chain Alerts")
        indexes = [
            models.Index(fields=["supplier", "severity", "status"]),
            models.Index(fields=["alert_type", "triggered_at"]),
            models.Index(fields=["status", "triggered_at"]),
        ]
        ordering = ["-triggered_at"]
        get_latest_by = "triggered_at"

    def __str__(self):
        return f"{self.get_alert_type_display()}: {self.title}"

    def acknowledge(self, user):
        """Mark alert as acknowledged."""
        self.status = "acknowledged"
        self.acknowledged_at = timezone.now()
        self.assigned_to = user
        self.save(update_fields=["status", "acknowledged_at", "assigned_to", "updated_at"])
        logger.info(f"Alert {self.alert_id} acknowledged by {user.username}")

    def resolve(self, user=None):
        """Manually resolve alert."""
        self.status = "resolved"
        self.resolved_at = timezone.now()
        if user:
            self.assigned_to = user
        self.save(update_fields=["status", "resolved_at", "assigned_to", "updated_at"])
        logger.info(f"Alert {self.alert_id} resolved")

    def auto_resolve(self):
        """Auto-resolve alert when condition normalizes."""
        self.status = "auto_resolved"
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at", "updated_at"])
        logger.info(f"Alert {self.alert_id} auto-resolved")


class RiskCategory(models.Model):
    """
    High-level risk assessment across different categories.

    Updated daily at 6 AM. Aggregates data from all other modules.
    One record per day per supplier (NULL supplier = global).
    """

    RISK_LEVEL_CHOICES = [
        ("low", _("Low Risk")),
        ("medium", _("Medium Risk")),
        ("high", _("High Risk")),
    ]

    # Supplier Risk
    supplier_risk_level = models.CharField(
        max_length=20, choices=RISK_LEVEL_CHOICES, default="low", verbose_name=_("Supplier Risk Level")
    )
    supplier_high_risk_count = models.IntegerField(
        default=0, verbose_name=_("High Risk Suppliers Count"), help_text=_("Count of suppliers with score < 70")
    )
    supplier_spend_at_risk = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Supplier Spend At Risk"),
        help_text=_("$ amount in last 90 days"),
    )
    single_source_dependencies = models.IntegerField(
        default=0, verbose_name=_("Single Source Dependencies"), help_text=_("Products from single supplier only")
    )

    # Logistics Risk
    logistics_risk_level = models.CharField(
        max_length=20, choices=RISK_LEVEL_CHOICES, default="low", verbose_name=_("Logistics Risk Level")
    )
    active_shipment_delays = models.IntegerField(
        default=0, verbose_name=_("Active Shipment Delays"), help_text=_("Count of delayed deliveries")
    )
    avg_delay_days = models.FloatField(default=0, verbose_name=_("Average Delay (days)"))
    routes_with_issues = models.IntegerField(default=0, verbose_name=_("Routes With Issues"))

    # Demand Risk
    demand_risk_level = models.CharField(
        max_length=20, choices=RISK_LEVEL_CHOICES, default="low", verbose_name=_("Demand Risk Level")
    )
    forecast_accuracy = models.FloatField(default=0, verbose_name=_("Forecast Accuracy %"))
    volatile_products_count = models.IntegerField(
        default=0, verbose_name=_("Volatile Products Count"), help_text=_("High demand variability")
    )
    stockout_incidents = models.IntegerField(default=0, verbose_name=_("Stock Out Incidents"), help_text=_("Last 30 days"))

    # Inventory Risk
    inventory_risk_level = models.CharField(
        max_length=20, choices=RISK_LEVEL_CHOICES, default="low", verbose_name=_("Inventory Risk Level")
    )
    items_below_safety_stock = models.IntegerField(default=0, verbose_name=_("Items Below Safety Stock"))
    overstock_items_count = models.IntegerField(
        default=0, verbose_name=_("Overstock Items Count"), help_text=_("> 180 days supply")
    )
    total_inventory_value_at_risk = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, verbose_name=_("Total Inventory Value At Risk")
    )

    # Overall Risk Score (0-100)
    overall_risk_score = models.FloatField(default=0, verbose_name=_("Overall Risk Score"))
    overall_risk_level = models.CharField(
        max_length=20, choices=RISK_LEVEL_CHOICES, default="low", verbose_name=_("Overall Risk Level"), db_index=True
    )

    # Metadata
    supplier = models.ForeignKey(
        "producer.Producer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="risk_categories",
        verbose_name=_("Supplier"),
        help_text=_("NULL = global/aggregate risks"),
    )
    snapshot_date = models.DateField(auto_now_add=True, verbose_name=_("Snapshot Date"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Risk Category")
        verbose_name_plural = _("Risk Categories")
        indexes = [
            models.Index(fields=["supplier", "snapshot_date"]),
            models.Index(fields=["snapshot_date"]),
            models.Index(fields=["overall_risk_level"]),
        ]
        ordering = ["-snapshot_date"]
        get_latest_by = "snapshot_date"
        unique_together = [["supplier", "snapshot_date"]]

    def __str__(self):
        supplier_name = self.supplier.name if self.supplier else "Global"
        return f"Risk Categories - {supplier_name} ({self.snapshot_date})"


class RiskDrillDown(models.Model):
    """
    Detailed list items for risk categories.

    E.g., list of suppliers at risk, products with low stock, etc.
    """

    ITEM_TYPE_CHOICES = [
        ("supplier", _("Supplier")),
        ("product", _("Product")),
        ("route", _("Route")),
        ("order", _("Order")),
        ("delivery", _("Delivery")),
    ]

    RISK_TYPE_CHOICES = [
        ("supplier_health", _("Supplier Health")),
        ("lead_time", _("Lead Time")),
        ("inventory", _("Inventory")),
        ("demand_forecast", _("Demand Forecast")),
        ("shipment_delay", _("Shipment Delay")),
        ("quality", _("Quality Issue")),
    ]

    STATUS_CHOICES = [
        ("at_risk", _("At Risk")),
        ("critical", _("Critical")),
        ("warning", _("Warning")),
    ]

    risk_category = models.ForeignKey(
        RiskCategory, on_delete=models.CASCADE, related_name="drill_downs", verbose_name=_("Risk Category")
    )
    risk_type = models.CharField(max_length=50, choices=RISK_TYPE_CHOICES, verbose_name=_("Risk Type"))

    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, verbose_name=_("Item Type"))
    item_id = models.PositiveIntegerField(verbose_name=_("Item ID"))
    item_name = models.CharField(max_length=255, verbose_name=_("Item Name"))

    # Context
    metric_value = models.FloatField(verbose_name=_("Metric Value"))
    threshold = models.FloatField(verbose_name=_("Threshold"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name=_("Status"))

    # Additional details
    details = models.JSONField(default=dict, verbose_name=_("Details"), help_text=_("Flexible field for extra context"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Risk Drill Down")
        verbose_name_plural = _("Risk Drill Downs")
        indexes = [
            models.Index(fields=["risk_category", "risk_type"]),
            models.Index(fields=["item_type", "status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_risk_type_display()}: {self.item_name}"
