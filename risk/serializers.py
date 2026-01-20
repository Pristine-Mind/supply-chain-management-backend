from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

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


class SupplierScorecardSerializer(serializers.ModelSerializer):
    """Serializer for SupplierScorecard model."""

    supplier_id = serializers.IntegerField(source="supplier.id", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    health_status_display = serializers.CharField(source="get_health_status_display", read_only=True)
    is_healthy = serializers.SerializerMethodField()
    is_critical = serializers.SerializerMethodField()

    class Meta:
        model = SupplierScorecard
        fields = [
            "supplier_id",
            "supplier_name",
            "health_score",
            "health_status",
            "health_status_display",
            "on_time_delivery_pct",
            "quality_performance_pct",
            "lead_time_consistency_pct",
            "payment_reliability_pct",
            "total_orders",
            "on_time_orders",
            "defect_count",
            "avg_lead_time_days",
            "lead_time_variance",
            "late_payments_count",
            "is_healthy",
            "is_critical",
            "last_calculated",
            "calculation_period_start",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_healthy(self, obj):
        """Check if supplier is healthy."""
        return obj.is_healthy

    def get_is_critical(self, obj):
        """Check if supplier is critical."""
        return obj.is_critical


class SupplierScoreHistorySerializer(serializers.ModelSerializer):
    """Serializer for SupplierScoreHistory model."""

    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    health_status_display = serializers.CharField(source="get_health_status_display", read_only=True)

    class Meta:
        model = SupplierScoreHistory
        fields = [
            "supplier_name",
            "health_score",
            "health_status",
            "health_status_display",
            "on_time_delivery_pct",
            "quality_performance_pct",
            "lead_time_consistency_pct",
            "recorded_at",
        ]
        read_only_fields = fields


class ProductDefectRecordSerializer(serializers.ModelSerializer):
    """Serializer for ProductDefectRecord model."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True, allow_null=True)
    defect_type_display = serializers.CharField(source="get_defect_type_display", read_only=True)
    resolution_status_display = serializers.CharField(source="get_resolution_status_display", read_only=True)

    class Meta:
        model = ProductDefectRecord
        fields = [
            "product_name",
            "supplier_name",
            "order_number",
            "defect_type",
            "defect_type_display",
            "quantity_defective",
            "description",
            "resolution_status",
            "resolution_status_display",
            "resolved_at",
            "resolution_notes",
            "defect_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["defect_date", "created_at", "updated_at"]


class SupplyChainKPISerializer(serializers.ModelSerializer):
    """Serializer for SupplyChainKPI model."""

    supplier_name = serializers.CharField(source="supplier.name", read_only=True, allow_null=True)

    class Meta:
        model = SupplyChainKPI
        fields = [
            "supplier_name",
            "otif_rate",
            "otif_previous",
            "otif_trend_pct",
            "lead_time_variability",
            "lead_time_avg",
            "lead_time_trend",
            "inventory_turnover_ratio",
            "inventory_turnover_previous",
            "inventory_trend_pct",
            "stock_out_incidents",
            "low_stock_items_count",
            "orders_pending_count",
            "orders_delayed_count",
            "period_start",
            "period_end",
            "snapshot_date",
            "created_at",
        ]
        read_only_fields = fields


class AlertThresholdSerializer(serializers.ModelSerializer):
    """Serializer for AlertThreshold model."""

    alert_type_display = serializers.CharField(source="get_alert_type_display", read_only=True)

    class Meta:
        model = AlertThreshold
        fields = [
            "alert_type",
            "alert_type_display",
            "critical_threshold",
            "critical_enabled",
            "warning_threshold",
            "warning_enabled",
            "check_frequency_minutes",
            "auto_resolve_hours",
            "description",
            "created_at",
            "updated_at",
        ]


class SupplyChainAlertSerializer(serializers.ModelSerializer):
    """Serializer for SupplyChainAlert model."""

    alert_type_display = serializers.CharField(source="get_alert_type_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, allow_null=True)
    product_name = serializers.CharField(source="product.name", read_only=True, allow_null=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True, allow_null=True)

    class Meta:
        model = SupplyChainAlert
        fields = [
            "alert_id",
            "alert_type",
            "alert_type_display",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "title",
            "description",
            "supplier_name",
            "product_name",
            "metric_value",
            "threshold_value",
            "triggered_at",
            "acknowledged_at",
            "resolved_at",
            "assigned_to_username",
            "is_notified",
            "notification_channels",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "alert_id",
            "triggered_at",
            "created_at",
            "updated_at",
            "alert_type_display",
            "severity_display",
            "status_display",
            "supplier_name",
            "product_name",
            "assigned_to_username",
        ]


class RiskDrillDownSerializer(serializers.ModelSerializer):
    """Serializer for RiskDrillDown model."""

    risk_type_display = serializers.CharField(source="get_risk_type_display", read_only=True)
    item_type_display = serializers.CharField(source="get_item_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RiskDrillDown
        fields = [
            "risk_type",
            "risk_type_display",
            "item_type",
            "item_type_display",
            "item_id",
            "item_name",
            "metric_value",
            "threshold",
            "status",
            "status_display",
            "details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RiskCategorySerializer(serializers.ModelSerializer):
    """Serializer for RiskCategory model."""

    supplier_name = serializers.CharField(source="supplier.name", read_only=True, allow_null=True)
    drill_downs = RiskDrillDownSerializer(many=True, read_only=True)
    supplier_risk_level_display = serializers.CharField(source="get_supplier_risk_level_display", read_only=True)
    logistics_risk_level_display = serializers.CharField(source="get_logistics_risk_level_display", read_only=True)
    demand_risk_level_display = serializers.CharField(source="get_demand_risk_level_display", read_only=True)
    inventory_risk_level_display = serializers.CharField(source="get_inventory_risk_level_display", read_only=True)
    overall_risk_level_display = serializers.CharField(source="get_overall_risk_level_display", read_only=True)

    class Meta:
        model = RiskCategory
        fields = [
            "supplier_name",
            "supplier_risk_level",
            "supplier_risk_level_display",
            "supplier_high_risk_count",
            "supplier_spend_at_risk",
            "single_source_dependencies",
            "logistics_risk_level",
            "logistics_risk_level_display",
            "active_shipment_delays",
            "avg_delay_days",
            "routes_with_issues",
            "demand_risk_level",
            "demand_risk_level_display",
            "forecast_accuracy",
            "volatile_products_count",
            "stockout_incidents",
            "inventory_risk_level",
            "inventory_risk_level_display",
            "items_below_safety_stock",
            "overstock_items_count",
            "total_inventory_value_at_risk",
            "overall_risk_score",
            "overall_risk_level",
            "overall_risk_level_display",
            "drill_downs",
            "snapshot_date",
            "last_updated",
            "created_at",
        ]
        read_only_fields = fields


class RiskDashboardSummarySerializer(serializers.Serializer):
    """Summary dashboard serializer combining all risk metrics."""

    timestamp = serializers.DateTimeField(read_only=True)
    supplier_scorecard = SupplierScorecardSerializer(read_only=True)
    kpis = SupplyChainKPISerializer(read_only=True)
    active_alerts = serializers.SerializerMethodField()
    risk_overview = RiskCategorySerializer(read_only=True)

    def get_active_alerts(self, obj):
        """Get count of active alerts by severity."""
        return {
            "critical": obj.get("critical_alerts", 0),
            "warning": obj.get("warning_alerts", 0),
            "info": obj.get("info_alerts", 0),
            "total": obj.get("total_alerts", 0),
        }
