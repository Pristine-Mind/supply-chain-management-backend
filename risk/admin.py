from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    AlertThreshold,
    ProductDefectRecord,
    RiskCategory,
    RiskDrillDown,
    SupplierScorecard,
    SupplierScoreHistory,
    SupplyChainAlert,
    SupplyChainKPI,
)


@admin.register(SupplierScorecard)
class SupplierScorecardAdmin(admin.ModelAdmin):
    """Admin interface for supplier scorecards."""

    list_display = (
        "supplier_name",
        "health_score_colored",
        "health_status",
        "on_time_delivery_pct",
        "quality_performance_pct",
        "lead_time_consistency_pct",
        "last_calculated",
    )
    list_filter = ("health_status", "health_score")
    search_fields = ("supplier__name",)
    readonly_fields = (
        "health_score",
        "health_status",
        "is_healthy",
        "is_critical",
        "created_at",
        "updated_at",
        "last_calculated",
    )
    fieldsets = (
        ("Supplier Information", {"fields": ("supplier",)}),
        (
            "Health Metrics",
            {
                "fields": (
                    "health_score",
                    "health_status",
                    "on_time_delivery_pct",
                    "quality_performance_pct",
                    "lead_time_consistency_pct",
                    "payment_reliability_pct",
                    "is_healthy",
                    "is_critical",
                )
            },
        ),
        (
            "Supporting Data",
            {
                "fields": (
                    "total_orders",
                    "on_time_orders",
                    "defect_count",
                    "avg_lead_time_days",
                    "lead_time_variance",
                    "late_payments_count",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "last_calculated", "calculation_period_start"),
                "classes": ("collapse",),
            },
        ),
    )

    def supplier_name(self, obj):
        """Display supplier name."""
        return obj.supplier.name if obj.supplier else "Unknown"

    supplier_name.short_description = "Supplier"

    def health_score_colored(self, obj):
        """Display health score with color coding."""
        if obj.health_score >= 80:
            color = "green"
        elif obj.health_score >= 60:
            color = "orange"
        else:
            color = "red"

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.health_score)

    health_score_colored.short_description = "Health Score"


@admin.register(SupplierScoreHistory)
class SupplierScoreHistoryAdmin(admin.ModelAdmin):
    """Admin interface for supplier score history."""

    list_display = (
        "supplier_name",
        "health_score",
        "recorded_at",
    )
    list_filter = ("recorded_at", "supplier__name", "health_status")
    search_fields = ("supplier__name",)
    readonly_fields = ("recorded_at", "health_score")
    date_hierarchy = "recorded_at"

    def supplier_name(self, obj):
        """Display supplier name."""
        return obj.supplier.name if obj.supplier else "Unknown"

    supplier_name.short_description = "Supplier"


@admin.register(ProductDefectRecord)
class ProductDefectRecordAdmin(admin.ModelAdmin):
    """Admin interface for product defect records."""

    list_display = (
        "product_name",
        "supplier_name",
        "defect_type",
        "severity_colored",
        "resolution_status",
        "defect_date",
    )
    list_filter = ("defect_type", "resolution_status", "defect_date")
    search_fields = ("product__name", "supplier__name", "description")
    readonly_fields = ("created_at", "updated_at", "defect_date")

    fieldsets = (
        ("Defect Information", {"fields": ("product", "supplier", "defect_type", "quantity_defective", "order")}),
        ("Details", {"fields": ("description", "resolution_status", "resolution_notes")}),
        ("Timeline", {"fields": ("defect_date", "resolved_at", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def product_name(self, obj):
        """Display product name."""
        return obj.product.name if obj.product else "Unknown"

    product_name.short_description = "Product"

    def supplier_name(self, obj):
        """Display supplier name."""
        return obj.supplier.name if obj.supplier else "Unknown"

    supplier_name.short_description = "Supplier"

    def severity_colored(self, obj):
        """Display severity with color coding."""
        colors = {
            "quality": "red",
            "damage": "orange",
            "missing_items": "orange",
            "other": "yellow",
        }
        color = colors.get(obj.defect_type, "gray")

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_defect_type_display())

    severity_colored.short_description = "Type"


@admin.register(SupplyChainKPI)
class SupplyChainKPIAdmin(admin.ModelAdmin):
    """Admin interface for supply chain KPIs."""

    list_display = (
        "supplier_name",
        "snapshot_date",
        "otif_rate_colored",
        "lead_time_avg",
        "inventory_turnover_ratio",
        "trend_indicator",
    )
    list_filter = ("snapshot_date", "supplier__name")
    search_fields = ("supplier__name",)
    readonly_fields = (
        "otif_rate",
        "lead_time_avg",
        "lead_time_variability",
        "inventory_turnover_ratio",
        "snapshot_date",
        "created_at",
    )
    date_hierarchy = "snapshot_date"

    fieldsets = (
        ("Supplier & Date", {"fields": ("supplier", "snapshot_date", "period_start", "period_end")}),
        ("OTIF Metrics", {"fields": ("otif_rate", "otif_previous", "otif_trend_pct")}),
        ("Lead Time Metrics", {"fields": ("lead_time_avg", "lead_time_variability", "lead_time_trend")}),
        (
            "Inventory Metrics",
            {"fields": ("inventory_turnover_ratio", "inventory_turnover_previous", "inventory_trend_pct")},
        ),
        (
            "Additional Metrics",
            {
                "fields": (
                    "stock_out_incidents",
                    "low_stock_items_count",
                    "orders_pending_count",
                    "orders_delayed_count",
                )
            },
        ),
        ("Metadata", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def supplier_name(self, obj):
        """Display supplier name."""
        return obj.supplier.name if obj.supplier else "Global"

    supplier_name.short_description = "Supplier"

    def otif_rate_colored(self, obj):
        """Display OTIF rate with color coding."""
        if obj.otif_rate >= 90:
            color = "green"
        elif obj.otif_rate >= 80:
            color = "orange"
        else:
            color = "red"

        return format_html('<span style="color: {}; font-weight: bold;">{}%</span>', color, round(obj.otif_rate, 1))

    otif_rate_colored.short_description = "OTIF Rate"

    def trend_indicator(self, obj):
        """Display trend indicator."""
        if obj.otif_trend_pct > 0:
            return format_html('<span style="color: green;">📈 +{}%</span>', round(obj.otif_trend_pct, 1))
        elif obj.otif_trend_pct < 0:
            return format_html('<span style="color: red;">📉 {}%</span>', round(obj.otif_trend_pct, 1))
        else:
            return "➡️ 0%"

    trend_indicator.short_description = "Trend"


@admin.register(AlertThreshold)
class AlertThresholdAdmin(admin.ModelAdmin):
    """Admin interface for alert threshold configuration."""

    list_display = (
        "get_alert_type_display",
        "critical_threshold",
        "warning_threshold",
        "check_frequency_minutes",
        "critical_enabled",
        "warning_enabled",
        "updated_at",
    )
    list_filter = ("alert_type", "critical_enabled", "warning_enabled")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Alert Configuration", {"fields": ("alert_type", "description")}),
        ("Critical Threshold", {"fields": ("critical_threshold", "critical_enabled")}),
        ("Warning Threshold", {"fields": ("warning_threshold", "warning_enabled")}),
        ("Execution", {"fields": ("check_frequency_minutes", "auto_resolve_hours")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_alert_type_display(self, obj):
        """Display alert type."""
        return obj.get_alert_type_display()

    get_alert_type_display.short_description = "Alert Type"


@admin.register(SupplyChainAlert)
class SupplyChainAlertAdmin(admin.ModelAdmin):
    """Admin interface for supply chain alerts."""

    list_display = (
        "title",
        "alert_type_display",
        "severity_colored",
        "status_colored",
        "triggered_at",
        "supplier_link",
        "action_buttons",
    )
    list_filter = ("alert_type", "severity", "status", "triggered_at")
    search_fields = ("title", "description", "supplier__name")
    readonly_fields = (
        "alert_type",
        "triggered_at",
        "created_at",
        "updated_at",
        "metadata",
    )
    date_hierarchy = "triggered_at"

    fieldsets = (
        ("Alert Information", {"fields": ("title", "description", "alert_type", "severity", "status")}),
        ("Scope", {"fields": ("supplier", "product")}),
        ("Management", {"fields": ("assigned_to", "acknowledged_by", "resolved_by")}),
        (
            "Timeline",
            {
                "fields": ("triggered_at", "acknowledged_at", "resolved_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
        ("Metadata", {"fields": ("metadata",), "classes": ("collapse",)}),
    )

    def alert_type_display(self, obj):
        """Display alert type."""
        return obj.get_alert_type_display()

    alert_type_display.short_description = "Type"

    def severity_colored(self, obj):
        """Display severity with color coding."""
        colors = {
            "critical": "red",
            "warning": "orange",
            "info": "blue",
        }
        color = colors.get(obj.severity, "gray")

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_severity_display())

    severity_colored.short_description = "Severity"

    def status_colored(self, obj):
        """Display status with color coding."""
        colors = {
            "active": "red",
            "acknowledged": "orange",
            "resolved": "green",
            "auto_resolved": "green",
        }
        color = colors.get(obj.status, "gray")

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"

    def supplier_link(self, obj):
        """Display supplier as link."""
        if obj.supplier:
            url = reverse("admin:producer_producer_change", args=[obj.supplier.id])
            return format_html('<a href="{}">{}</a>', url, obj.supplier.name)
        return "-"

    supplier_link.short_description = "Supplier"

    def action_buttons(self, obj):
        """Display action buttons for alert management."""
        buttons = []

        if obj.status == "active":
            buttons.append(
                format_html(
                    '<button style="background-color: #417690; color: white; padding: 5px 10px; margin: 2px; border: none; border-radius: 3px; cursor: pointer;">Acknowledge</button>'
                )
            )

        if obj.status in ["active", "acknowledged"]:
            buttons.append(
                format_html(
                    '<button style="background-color: #417690; color: white; padding: 5px 10px; margin: 2px; border: none; border-radius: 3px; cursor: pointer;">Resolve</button>'
                )
            )

        return format_html(" ".join(buttons)) if buttons else "✓ Resolved"

    action_buttons.short_description = "Actions"


@admin.register(RiskCategory)
class RiskCategoryAdmin(admin.ModelAdmin):
    """Admin interface for risk categories."""

    list_display = (
        "supplier_display",
        "snapshot_date",
        "supplier_risk_colored",
        "logistics_risk_colored",
        "demand_risk_colored",
        "inventory_risk_colored",
        "overall_risk_colored",
    )
    list_filter = ("overall_risk_level", "snapshot_date", "supplier__name")
    search_fields = ("supplier__name",)
    readonly_fields = (
        "snapshot_date",
        "supplier_risk_level",
        "logistics_risk_level",
        "demand_risk_level",
        "inventory_risk_level",
        "overall_risk_level",
        "created_at",
        "last_updated",
    )
    date_hierarchy = "snapshot_date"

    fieldsets = (
        ("Risk Assessment", {"fields": ("supplier", "snapshot_date", "overall_risk_level")}),
        (
            "Supplier Risks",
            {
                "fields": (
                    "supplier_risk_level",
                    "supplier_high_risk_count",
                    "supplier_spend_at_risk",
                    "single_source_dependencies",
                )
            },
        ),
        (
            "Logistics Risks",
            {"fields": ("logistics_risk_level", "active_shipment_delays", "avg_delay_days", "routes_with_issues")},
        ),
        (
            "Demand Risks",
            {"fields": ("demand_risk_level", "forecast_accuracy", "volatile_products_count", "stockout_incidents")},
        ),
        (
            "Inventory Risks",
            {
                "fields": (
                    "inventory_risk_level",
                    "items_below_safety_stock",
                    "overstock_items_count",
                    "total_inventory_value_at_risk",
                )
            },
        ),
        ("Overall Assessment", {"fields": ("overall_risk_score",), "classes": ("wide",)}),
        ("Metadata", {"fields": ("created_at", "last_updated"), "classes": ("collapse",)}),
    )

    def supplier_display(self, obj):
        """Display supplier name or global."""
        return obj.supplier.name if obj.supplier else "Global"

    supplier_display.short_description = "Supplier"

    def supplier_risk_colored(self, obj):
        """Display supplier risk with color."""
        return self._risk_colored(obj.supplier_risk_level)

    supplier_risk_colored.short_description = "Supplier"

    def logistics_risk_colored(self, obj):
        """Display logistics risk with color."""
        return self._risk_colored(obj.logistics_risk_level)

    logistics_risk_colored.short_description = "Logistics"

    def demand_risk_colored(self, obj):
        """Display demand risk with color."""
        return self._risk_colored(obj.demand_risk_level)

    demand_risk_colored.short_description = "Demand"

    def inventory_risk_colored(self, obj):
        """Display inventory risk with color."""
        return self._risk_colored(obj.inventory_risk_level)

    inventory_risk_colored.short_description = "Inventory"

    def overall_risk_colored(self, obj):
        """Display overall risk with color."""
        return self._risk_colored(obj.overall_risk_level)

    overall_risk_colored.short_description = "Overall"

    def _risk_colored(self, risk_level):
        """Helper to display risk level with color."""
        colors = {
            "low": "green",
            "medium": "orange",
            "high": "red",
        }
        color = colors.get(risk_level, "gray")

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, risk_level.upper())


class RiskDrillDownInline(admin.TabularInline):
    """Inline admin for risk drill-down items."""

    model = RiskDrillDown
    extra = 0
    readonly_fields = ("item_id", "created_at")
    fields = ("item_name", "item_type", "risk_type", "status", "metric_value")


@admin.register(RiskDrillDown)
class RiskDrillDownAdmin(admin.ModelAdmin):
    """Admin interface for risk drill-down details."""

    list_display = (
        "item_name",
        "risk_category_link",
        "status_colored",
        "metric_value",
        "created_at",
    )
    list_filter = ("status", "created_at", "risk_category__supplier", "risk_type", "item_type")
    search_fields = ("item_name", "item_id")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Item Information", {"fields": ("risk_category", "item_name", "item_id", "item_type")}),
        ("Risk Assessment", {"fields": ("risk_type", "status", "metric_value", "threshold")}),
        ("Details", {"fields": ("details",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def risk_category_link(self, obj):
        """Display risk category as link."""
        url = reverse("admin:risk_riskcategory_change", args=[obj.risk_category.id])
        return format_html('<a href="{}">{}</a>', url, obj.risk_category)

    risk_category_link.short_description = "Category"

    def status_colored(self, obj):
        """Display status with color."""
        colors = {
            "critical": "red",
            "at_risk": "orange",
            "warning": "orange",
        }
        color = colors.get(obj.status, "green")

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"
