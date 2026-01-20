"""
Management command to load initial data for risk management models.

Creates default alert thresholds and initial risk categories.
Safe to run multiple times - uses get_or_create to prevent duplicates.

Usage:
    python manage.py load_risk_data
    python manage.py load_risk_data --reset  (deletes existing data first)
    python manage.py load_risk_data -v 2     (verbose output)
"""

import logging
import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from producer.models import Order, Producer, Product
from risk.models import (
    AlertThreshold,
    ProductDefectRecord,
    RiskCategory,
    RiskDrillDown,
    SupplierScorecard,
    SupplierScoreHistory,
    SupplyChainAlert,
    SupplyChainKPI,
)
from transport.models import Delivery, TransportStatus

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to seed risk management database with initial data."""

    help = "Load initial data for risk management models (alert thresholds, risk categories)"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing alert thresholds before loading new data",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        self.verbose = options.get("verbosity", 1) > 1
        reset = options.get("reset", False)

        self.stdout.write(self.style.SUCCESS("Starting risk data initialization..."))

        try:
            if reset:
                self.reset_data()

            self.load_alert_thresholds()
            self.load_initial_risk_categories()
            self.load_supplier_scorecards()
            self.load_supplier_score_history()
            self.load_product_defects()
            self.load_kpi_data()
            self.load_alerts()
            self.load_risk_drill_downs()

            self.stdout.write(self.style.SUCCESS("✓ Risk data initialization completed successfully!"))

        except Exception as e:
            logger.error(f"Error loading risk data: {e}", exc_info=True)
            raise CommandError(f"Failed to load risk data: {e}")

    def reset_data(self):
        """Delete existing alert thresholds."""
        self.stdout.write(self.style.WARNING("Resetting existing risk data..."))
        models = [
            RiskDrillDown,
            SupplyChainAlert,
            SupplyChainKPI,
            ProductDefectRecord,
            SupplierScoreHistory,
            RiskCategory,
            SupplierScorecard,
            AlertThreshold,
        ]
        total_deleted = 0
        for model in models:
            count = model.objects.all().delete()[0]
            total_deleted += count
            if self.verbose:
                self.stdout.write(f"  Deleted {count} {model.__name__} records")
        self.stdout.write(self.style.SUCCESS(f"  Deleted {total_deleted} total risk records"))

    def load_alert_thresholds(self):
        """Create default alert thresholds."""
        self.stdout.write("\nLoading alert thresholds...")

        thresholds = [
            {
                "alert_type": "supplier_health",
                "critical_threshold": 60,
                "warning_threshold": 70,
                "check_frequency_minutes": 120,
                "auto_resolve_hours": 24,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when supplier health score drops below critical or warning threshold",
            },
            {
                "alert_type": "otif",
                "critical_threshold": 90,
                "warning_threshold": 95,
                "check_frequency_minutes": 120,
                "auto_resolve_hours": 24,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when On-Time In-Full rate drops below thresholds",
            },
            {
                "alert_type": "lead_time",
                "critical_threshold": 15,  # days
                "warning_threshold": 10,  # days
                "check_frequency_minutes": 360,  # 6 hours
                "auto_resolve_hours": 24,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when average lead time exceeds thresholds",
            },
            {
                "alert_type": "stock_low",
                "critical_threshold": 50,  # units or %
                "warning_threshold": 100,  # units or %
                "check_frequency_minutes": 15,
                "auto_resolve_hours": 12,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when stock approaches safety stock levels",
            },
            {
                "alert_type": "stock_out",
                "critical_threshold": 0,
                "warning_threshold": 0,
                "check_frequency_minutes": 15,
                "auto_resolve_hours": 6,
                "critical_enabled": True,
                "warning_enabled": False,
                "description": "Alert when stock reaches zero (stock out)",
            },
            {
                "alert_type": "delayed_order",
                "critical_threshold": 5,  # days late
                "warning_threshold": 2,  # days late
                "check_frequency_minutes": 60,
                "auto_resolve_hours": 24,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when orders are delayed beyond estimated delivery date",
            },
            {
                "alert_type": "quality_issue",
                "critical_threshold": 5,  # % defect rate
                "warning_threshold": 2,  # % defect rate
                "check_frequency_minutes": 360,
                "auto_resolve_hours": 72,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when defect rate exceeds thresholds",
            },
            {
                "alert_type": "inventory_variance",
                "critical_threshold": 20,  # % variance
                "warning_threshold": 10,  # % variance
                "check_frequency_minutes": 1440,  # daily
                "auto_resolve_hours": 48,
                "critical_enabled": True,
                "warning_enabled": True,
                "description": "Alert when inventory variance exceeds acceptable levels",
            },
        ]

        created_count = 0
        updated_count = 0

        for threshold_data in thresholds:
            obj, created = AlertThreshold.objects.get_or_create(
                alert_type=threshold_data["alert_type"],
                defaults={
                    "critical_threshold": threshold_data["critical_threshold"],
                    "warning_threshold": threshold_data["warning_threshold"],
                    "check_frequency_minutes": threshold_data["check_frequency_minutes"],
                    "auto_resolve_hours": threshold_data["auto_resolve_hours"],
                    "critical_enabled": threshold_data["critical_enabled"],
                    "warning_enabled": threshold_data["warning_enabled"],
                    "description": threshold_data["description"],
                },
            )

            if created:
                created_count += 1
                if self.verbose:
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Created: {obj.get_alert_type_display()}"))
            else:
                updated_count += 1
                if self.verbose:
                    self.stdout.write(self.style.WARNING(f"  ~ Exists: {obj.get_alert_type_display()}"))

        self.stdout.write(
            self.style.SUCCESS(f"  ✓ Alert thresholds: {created_count} created, {updated_count} already exist")
        )

    def load_initial_risk_categories(self):
        """Create initial global risk category entry."""
        self.stdout.write("\nLoading initial risk categories...")

        today = timezone.now().date()

        # Create global risk category if it doesn't exist
        obj, created = RiskCategory.objects.get_or_create(
            supplier__isnull=True,
            snapshot_date=today,
            defaults={
                "supplier_risk_level": "low",
                "supplier_high_risk_count": 0,
                "supplier_spend_at_risk": Decimal("0.00"),
                "single_source_dependencies": 0,
                "logistics_risk_level": "low",
                "active_shipment_delays": 0,
                "avg_delay_days": 0.0,
                "routes_with_issues": 0,
                "demand_risk_level": "low",
                "forecast_accuracy": 100.0,
                "volatile_products_count": 0,
                "stockout_incidents": 0,
                "inventory_risk_level": "low",
                "items_below_safety_stock": 0,
                "overstock_items_count": 0,
                "total_inventory_value_at_risk": Decimal("0.00"),
                "overall_risk_score": 0.0,
                "overall_risk_level": "low",
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS("  ✓ Created: Global risk category"))
        else:
            self.stdout.write(self.style.WARNING("  ~ Global risk category already exists"))

        suppliers = Producer.objects.filter(scorecard__isnull=True)
        initialized_count = 0

        for supplier in suppliers:
            SupplierScorecard.objects.get_or_create(
                supplier=supplier,
                defaults={
                    "on_time_delivery_pct": 0.0,
                    "quality_performance_pct": 100.0,
                    "lead_time_consistency_pct": 100.0,
                    "payment_reliability_pct": 100.0,
                    "health_score": 75.0,
                    "health_status": "monitor",
                    "total_orders": 0,
                    "on_time_orders": 0,
                    "defect_count": 0,
                    "avg_lead_time_days": 0.0,
                    "lead_time_variance": 0.0,
                    "late_payments_count": 0,
                    "calculation_period_start": today,
                },
            )
            initialized_count += 1
            if self.verbose:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Initialized: {supplier.name} scorecard"))

        if initialized_count > 0:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Supplier scorecards: {initialized_count} initialized"))
        else:
            self.stdout.write(self.style.WARNING("  ~ All suppliers already have scorecards"))

    def load_supplier_scorecards(self):
        """Update supplier scorecards with varied data."""
        self.stdout.write("\nUpdating supplier scorecards with test data...")

        suppliers = Producer.objects.all()
        updated_count = 0

        for supplier in suppliers:
            try:
                scorecard = SupplierScorecard.objects.get(supplier=supplier)

                # Generate varied scores
                otd = random.uniform(70, 99)
                quality = random.uniform(90, 100)
                lead_time = random.uniform(75, 100)
                payment = random.uniform(95, 100)

                # Calculate weighted health score
                health = (otd * 0.5) + (quality * 0.3) + (lead_time * 0.15) + (payment * 0.05)

                scorecard.on_time_delivery_pct = round(otd, 2)
                scorecard.quality_performance_pct = round(quality, 2)
                scorecard.lead_time_consistency_pct = round(lead_time, 2)
                scorecard.payment_reliability_pct = round(payment, 2)
                scorecard.health_score = round(health, 2)

                # Set health status
                if health >= 80:
                    scorecard.health_status = "healthy"
                elif health >= 60:
                    scorecard.health_status = "monitor"
                else:
                    scorecard.health_status = "critical"

                # Add supporting metrics
                scorecard.total_orders = random.randint(10, 500)
                scorecard.on_time_orders = int(scorecard.total_orders * (otd / 100))
                scorecard.defect_count = random.randint(0, int(scorecard.total_orders * 0.1))
                scorecard.avg_lead_time_days = round(random.uniform(2, 15), 2)
                scorecard.lead_time_variance = round(random.uniform(0.5, 5), 2)
                scorecard.late_payments_count = random.randint(0, 5)

                scorecard.save()
                updated_count += 1

                if self.verbose:
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ {supplier.name}: health={health:.1f} ({scorecard.health_status})")
                    )
            except SupplierScorecard.DoesNotExist:
                if self.verbose:
                    self.stdout.write(self.style.WARNING(f"  ~ Scorecard not found for {supplier.name}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Updated {updated_count} supplier scorecards"))

    def load_supplier_score_history(self):
        """Create historical score data for trend analysis."""
        self.stdout.write("\nCreating supplier score history (90-day trend)...")

        suppliers = Producer.objects.all()
        created_count = 0

        # Create 90 days of history
        for supplier in suppliers:
            try:
                scorecard = SupplierScorecard.objects.get(supplier=supplier)
                base_score = scorecard.health_score

                for days_ago in range(1, 91):  # 90 days back
                    record_date = timezone.now() - timedelta(days=days_ago)

                    # Add some variation to scores
                    variation = random.uniform(-5, 5)
                    health_score = max(0, min(100, base_score + variation))

                    # Determine status
                    if health_score >= 80:
                        status = "healthy"
                    elif health_score >= 60:
                        status = "monitor"
                    else:
                        status = "critical"

                    SupplierScoreHistory.objects.get_or_create(
                        supplier=supplier,
                        recorded_at=record_date,
                        defaults={
                            "health_score": round(health_score, 2),
                            "health_status": status,
                            "on_time_delivery_pct": round(
                                max(0, min(100, scorecard.on_time_delivery_pct + random.uniform(-3, 3))), 2
                            ),
                            "quality_performance_pct": round(
                                max(0, min(100, scorecard.quality_performance_pct + random.uniform(-2, 2))), 2
                            ),
                            "lead_time_consistency_pct": round(
                                max(0, min(100, scorecard.lead_time_consistency_pct + random.uniform(-3, 3))), 2
                            ),
                        },
                    )
                    created_count += 1

                if self.verbose:
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {supplier.name}: 90 days of history"))
            except SupplierScorecard.DoesNotExist:
                pass

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {created_count} history records"))

    def load_product_defects(self):
        """Create product defect records for quality tracking."""
        self.stdout.write("\nCreating product defect records...")

        suppliers = Producer.objects.all()
        products = Product.objects.all()[:20]  # Limit to first 20 products
        defect_types = ["quality", "damage", "missing_items", "other"]
        created_count = 0

        if not products:
            self.stdout.write(self.style.WARNING("  ~ No products found, skipping defect records"))
            return

        for _ in range(100):  # Create 100 defect records
            try:
                supplier = random.choice(suppliers)
                product = random.choice(products)
                defect_type = random.choice(defect_types)

                SupplyChainAlert.objects.create(
                    product=product,
                    supplier=supplier,
                    defect_type=defect_type,
                    quantity_defective=random.randint(1, 50),
                    description=f"{defect_type.replace('_', ' ').title()} detected in {product.name}",
                    resolution_status=random.choice(["open", "resolved", "escalated"]),
                    resolved_at=timezone.now() - timedelta(days=random.randint(1, 30)) if random.random() > 0.3 else None,
                    resolution_notes=f"Issue resolved by quality team" if random.random() > 0.3 else "",
                )
                created_count += 1
            except Exception as e:
                if self.verbose:
                    logger.error(f"Error creating defect record: {e}")

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {created_count} defect records"))

    def load_kpi_data(self):
        """Create KPI snapshots for performance tracking."""
        self.stdout.write("\nCreating supply chain KPI snapshots...")

        suppliers = Producer.objects.all()
        created_count = 0

        # Create current and historical KPI data
        for supplier in suppliers:
            try:
                # Create KPI for each 6-hour period in the last 30 days
                for days_ago in range(0, 30):
                    for hour_offset in [0, 6, 12, 18]:
                        period_end = timezone.now() - timedelta(days=days_ago, hours=hour_offset)
                        period_start = period_end - timedelta(hours=6)

                        otif = round(random.uniform(85, 98), 2)
                        lead_time = round(random.uniform(3, 12), 2)
                        turnover = round(random.uniform(8, 20), 2)

                        SupplyChainKPI.objects.get_or_create(
                            supplier=supplier,
                            period_start=period_start.date(),
                            period_end=period_end.date(),
                            defaults={
                                "otif_rate": otif,
                                "otif_previous": round(random.uniform(85, 98), 2),
                                "otif_trend_pct": round(random.uniform(-5, 5), 2),
                                "lead_time_avg": lead_time,
                                "lead_time_variability": round(random.uniform(0.5, 3), 2),
                                "lead_time_trend": round(random.uniform(-1, 1), 2),
                                "inventory_turnover_ratio": turnover,
                                "inventory_turnover_previous": round(random.uniform(8, 20), 2),
                                "inventory_trend_pct": round(random.uniform(-10, 10), 2),
                                "stock_out_incidents": random.randint(0, 5),
                                "low_stock_items_count": random.randint(0, 20),
                                "orders_pending_count": random.randint(0, 50),
                                "orders_delayed_count": random.randint(0, 10),
                            },
                        )
                        created_count += 1

                if self.verbose:
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {supplier.name}: 30 days of KPI data"))
            except Exception as e:
                if self.verbose:
                    logger.error(f"Error creating KPI for {supplier.name}: {e}")

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {created_count} KPI snapshots"))

    def load_alerts(self):
        """Create sample supply chain alerts."""
        self.stdout.write("\nCreating supply chain alerts...")

        suppliers = list(Producer.objects.all())
        alert_types = [
            "supplier_health",
            "otif",
            "lead_time",
            "stock_low",
            "stock_out",
            "delayed_order",
            "quality_issue",
            "inventory_variance",
        ]
        severities = ["critical", "warning", "info"]
        statuses = ["active", "acknowledged", "resolved", "auto_resolved"]
        created_count = 0

        if not suppliers:
            self.stdout.write(self.style.WARNING("  ~ No suppliers found, skipping alerts"))
            return

        for _ in range(150):  # Create 150 alerts
            try:
                supplier = random.choice(suppliers)
                alert_type = random.choice(alert_types)
                severity = random.choice(severities)
                status = random.choice(statuses)

                triggered = timezone.now() - timedelta(days=random.randint(0, 30))

                alert = SupplyChainAlert.objects.create(
                    title=f"{alert_type.replace('_', ' ').title()} alert for {supplier.name}",
                    description=f"This is an automated {severity} alert triggered by the monitoring system",
                    alert_type=alert_type,
                    severity=severity,
                    status=status,
                    supplier=supplier,
                    triggered_at=triggered,
                )

                # Add acknowledgement data if status indicates it
                if status in ["acknowledged", "resolved", "auto_resolved"]:
                    alert.acknowledged_at = triggered + timedelta(hours=random.randint(1, 12))

                if status in ["resolved", "auto_resolved"]:
                    alert.resolved_at = alert.acknowledged_at + timedelta(hours=random.randint(1, 48))

                alert.is_notified = random.random() > 0.3
                alert.metadata = {
                    "current_value": round(random.uniform(0, 100), 2),
                    "threshold": round(random.uniform(50, 100), 2),
                    "trend": random.choice(["improving", "degrading", "stable"]),
                }
                alert.save()
                created_count += 1
            except Exception as e:
                if self.verbose:
                    logger.error(f"Error creating alert: {e}")

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {created_count} alerts"))

    def load_risk_drill_downs(self):
        """Create risk drill-down items for detailed analysis."""
        self.stdout.write("\nCreating risk drill-down details...")

        risk_types = [
            "supplier_health",
            "lead_time",
            "inventory",
            "demand_forecast",
            "shipment_delay",
            "quality",
        ]
        item_types = ["supplier", "product", "route", "order", "delivery"]
        statuses = ["at_risk", "critical", "warning"]
        created_count = 0

        # Get or create risk categories
        risk_categories = list(RiskCategory.objects.all())

        if not risk_categories:
            self.stdout.write(self.style.WARNING("  ~ No risk categories found, skipping drill-downs"))
            return

        for _ in range(200):  # Create 200 drill-down items
            try:
                risk_category = random.choice(risk_categories)
                risk_type = random.choice(risk_types)
                item_type = random.choice(item_types)
                status = random.choice(statuses)

                RiskDrillDown.objects.create(
                    risk_category=risk_category,
                    risk_type=risk_type,
                    item_type=item_type,
                    item_id=random.randint(1, 10000),
                    item_name=f"{item_type.capitalize()} #{random.randint(100, 999)}",
                    metric_value=round(random.uniform(0, 100), 2),
                    threshold=round(random.uniform(50, 100), 2),
                    status=status,
                    details={
                        "reason": f"Risk due to {risk_type.replace('_', ' ')}",
                        "impact": random.choice(["high", "medium", "low"]),
                        "recommendation": "Monitor closely and take corrective action",
                        "last_checked": timezone.now().isoformat(),
                    },
                )
                created_count += 1
            except Exception as e:
                if self.verbose:
                    logger.error(f"Error creating drill-down: {e}")

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {created_count} drill-down items"))
