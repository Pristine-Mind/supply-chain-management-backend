import logging
import statistics
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import (
    Avg,
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    Sum,
    When,
)
from django.db.models.functions import TruncDate
from django.utils import timezone

from notification.models import Notification
from producer.models import Order, Product, Sale, StockHistory
from producer.risk_models import (
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


@shared_task(bind=True, max_retries=3)
def calculate_supplier_health_scores(self):
    """
    Calculate supplier health scores based on performance metrics.

    Triggered: Daily at midnight
    Metrics:
    - On-Time Delivery (50%): % of orders delivered on-time
    - Quality Performance (30%): 100% - defect_rate
    - Lead Time Consistency (20%): Variance from promised lead time

    Score Range: 0-100
    - 80-100: Healthy (Green)
    - 60-79: Monitor (Yellow)
    - 0-59: Critical (Red)
    """
    logger.info("Starting supplier health score calculation...")

    try:
        from producer.models import Producer

        cutoff_90 = timezone.now().date() - timedelta(days=90)
        cutoff_14 = timezone.now().date() - timedelta(days=14)
        suppliers = Producer.objects.filter(is_active=True)

        total_updated = 0
        total_errors = 0

        for supplier in suppliers:
            try:
                # 1. Calculate On-Time Delivery %
                total_orders = Order.objects.filter(user=supplier.user, order_date__date__gte=cutoff_90).count()

                on_time_pct = 100.0
                on_time_count = 0

                if total_orders > 0:
                    # Orders where delivery_date <= order_date + 7 days (default promise)
                    on_time_count = Order.objects.filter(
                        user=supplier.user,
                        order_date__date__gte=cutoff_90,
                        delivery_date__isnull=False,
                        delivery_date__lte=F("order_date") + timedelta(days=7),
                    ).count()

                    on_time_pct = (on_time_count / total_orders) * 100

                # 2. Calculate Quality Performance % (100% - defect_rate)
                total_defects = (
                    ProductDefectRecord.objects.filter(supplier=supplier, defect_date__date__gte=cutoff_90).aggregate(
                        total=Sum("quantity_defective")
                    )["total"]
                    or 0
                )

                total_sold = (
                    Sale.objects.filter(user=supplier.user, sale_date__date__gte=cutoff_90).aggregate(total=Sum("quantity"))[
                        "total"
                    ]
                    or 1
                )

                quality_pct = 100.0 - ((total_defects / total_sold * 100) if total_sold > 0 else 0)
                quality_pct = max(0, min(100, quality_pct))  # Clamp between 0-100

                # 3. Calculate Lead Time Consistency
                sales_lead_times = (
                    Sale.objects.filter(user=supplier.user, sale_date__date__gte=cutoff_90)
                    .annotate(
                        actual_lead_days=ExpressionWrapper(
                            (F("created_at") - F("order__order_date")) / timedelta(days=1), output_field=FloatField()
                        )
                    )
                    .values_list("actual_lead_days", flat=True)
                )

                consistency_pct = 100.0
                avg_lead_time = 0.0
                lead_time_var = 0.0

                if sales_lead_times:
                    lead_times = list(sales_lead_times)
                    avg_lead_time = statistics.mean(lead_times)
                    lead_time_var = statistics.pstdev(lead_times) if len(lead_times) > 1 else 0
                    # Consistency score: lower variance = higher score
                    # If variance > 5 days, it's concerning
                    consistency_pct = max(0, 100 - (lead_time_var * 5))

                # 4. Payment Reliability
                payment_reliability_pct = 95.0  # Placeholder - implement if payment tracking exists

                # 5. Calculate Weighted Health Score
                health_score = (on_time_pct * 0.50) + (quality_pct * 0.30) + (consistency_pct * 0.20)

                # Determine status
                if health_score >= 80:
                    status = "healthy"
                elif health_score >= 60:
                    status = "monitor"
                else:
                    status = "critical"

                # 6. Update or create scorecard
                with transaction.atomic():
                    scorecard, created = SupplierScorecard.objects.update_or_create(
                        supplier=supplier,
                        defaults={
                            "health_score": round(health_score, 2),
                            "health_status": status,
                            "total_orders": total_orders,
                            "on_time_orders": on_time_count,
                            "on_time_delivery_pct": round(on_time_pct, 2),
                            "quality_performance_pct": round(quality_pct, 2),
                            "lead_time_consistency_pct": round(consistency_pct, 2),
                            "payment_reliability_pct": payment_reliability_pct,
                            "defect_count": int(total_defects),
                            "avg_lead_time_days": round(avg_lead_time, 2),
                            "lead_time_variance": round(lead_time_var, 2),
                            "calculation_period_start": cutoff_90,
                        },
                    )

                    # 7. Store historical snapshot
                    SupplierScoreHistory.objects.create(
                        supplier=supplier,
                        health_score=round(health_score, 2),
                        health_status=status,
                        on_time_delivery_pct=round(on_time_pct, 2),
                        quality_performance_pct=round(quality_pct, 2),
                        lead_time_consistency_pct=round(consistency_pct, 2),
                    )

                    total_updated += 1
                    logger.info(f"Updated scorecard for {supplier.name}: " f"{health_score:.2f} ({status})")

            except Exception as e:
                logger.error(f"Error calculating score for {supplier.name}: {e}", exc_info=True)
                total_errors += 1
                continue

        result = f"Calculated health scores: {total_updated} updated, {total_errors} errors"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in calculate_supplier_health_scores: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=3)


@shared_task(bind=True, max_retries=3)
def calculate_supply_chain_kpis(self, supplier_id=None):
    """
    Calculate OTIF, Lead Time Variability, and Inventory Turnover.

    Triggered: Every 6 hours
    Supports per-supplier or global calculation.
    """
    logger.info(f"Calculating KPIs for supplier={supplier_id}")

    try:
        from producer.models import Producer

        today = timezone.now().date()
        period_30 = today - timedelta(days=30)
        period_60 = today - timedelta(days=60)

        # Get suppliers to process
        if supplier_id:
            suppliers = Producer.objects.filter(id=supplier_id, is_active=True)
        else:
            suppliers = Producer.objects.filter(is_active=True)

        total_created = 0

        for supplier in suppliers:
            try:
                # 1. OTIF Rate Calculation
                orders_30 = Order.objects.filter(user=supplier.user, order_date__date__gte=period_30)

                otif_orders = 0
                if orders_30.exists():
                    # On-Time AND In-Full
                    otif_orders = orders_30.filter(
                        delivery_date__isnull=False,
                        delivery_date__lte=F("order_date") + timedelta(days=7),
                    ).count()

                otif_rate = (otif_orders / orders_30.count() * 100) if orders_30.exists() else 100.0

                # Previous period
                orders_60_90 = Order.objects.filter(
                    user=supplier.user, order_date__date__gte=period_60, order_date__date__lt=period_30
                )

                otif_orders_prev = 0
                if orders_60_90.exists():
                    otif_orders_prev = orders_60_90.filter(
                        delivery_date__isnull=False,
                        delivery_date__lte=F("order_date") + timedelta(days=7),
                    ).count()

                otif_previous = (otif_orders_prev / orders_60_90.count() * 100) if orders_60_90.exists() else 100.0
                otif_trend = ((otif_rate - otif_previous) / otif_previous * 100) if otif_previous > 0 else 0

                # 2. Lead Time Variability
                sales_30 = (
                    Sale.objects.filter(user=supplier.user, sale_date__date__gte=period_30)
                    .annotate(
                        actual_lead_days=ExpressionWrapper(
                            (F("created_at") - F("order__order_date")) / timedelta(days=1), output_field=FloatField()
                        )
                    )
                    .values_list("actual_lead_days", flat=True)
                )

                lead_time_avg = 0.0
                lead_time_var = 0.0

                if sales_30:
                    lead_times = list(sales_30)
                    lead_time_avg = statistics.mean(lead_times)
                    lead_time_var = statistics.pstdev(lead_times) if len(lead_times) > 1 else 0

                # Previous period
                sales_60_90 = (
                    Sale.objects.filter(user=supplier.user, sale_date__date__gte=period_60, sale_date__date__lt=period_30)
                    .annotate(
                        actual_lead_days=ExpressionWrapper(
                            (F("created_at") - F("order__order_date")) / timedelta(days=1), output_field=FloatField()
                        )
                    )
                    .values_list("actual_lead_days", flat=True)
                )

                lead_time_var_prev = 0.0
                if sales_60_90:
                    lead_times_prev = list(sales_60_90)
                    lead_time_var_prev = statistics.pstdev(lead_times_prev) if len(lead_times_prev) > 1 else 0

                lead_time_trend = lead_time_var - lead_time_var_prev

                # 3. Inventory Turnover
                cogs = (
                    Sale.objects.filter(user=supplier.user, sale_date__date__gte=period_30).aggregate(
                        total=Sum(ExpressionWrapper(F("sale_price") * F("quantity"), output_field=FloatField()))
                    )["total"]
                    or 0
                )

                avg_inventory = (
                    Product.objects.filter(user=supplier.user).aggregate(
                        total=Sum(ExpressionWrapper(F("stock") * F("cost_price"), output_field=FloatField()))
                    )["total"]
                    or 1
                )

                inventory_turnover = float(cogs / avg_inventory) if avg_inventory > 0 else 0.0

                # Previous period
                cogs_prev = (
                    Sale.objects.filter(
                        user=supplier.user, sale_date__date__gte=period_60, sale_date__date__lt=period_30
                    ).aggregate(total=Sum(ExpressionWrapper(F("sale_price") * F("quantity"), output_field=FloatField())))[
                        "total"
                    ]
                    or 0
                )

                inventory_turnover_prev = float(cogs_prev / avg_inventory) if avg_inventory > 0 else 0.0
                inventory_trend = (
                    ((inventory_turnover - inventory_turnover_prev) / inventory_turnover_prev * 100)
                    if inventory_turnover_prev > 0
                    else 0
                )

                # 4. Additional metrics
                stock_outs = StockHistory.objects.filter(
                    product__user=supplier.user, date__gte=period_30, quantity_in=0, quantity_out__gt=0, stock_after=0
                ).count()

                low_stock = Product.objects.filter(user=supplier.user, stock__lt=F("reorder_point")).count()

                pending_orders = Order.objects.filter(user=supplier.user, status__in=["pending", "approved"]).count()

                delayed_orders = Order.objects.filter(
                    user=supplier.user, delivery_date__isnull=False, delivery_date__lt=timezone.now()
                ).count()

                # 5. Store KPI snapshot
                with transaction.atomic():
                    SupplyChainKPI.objects.create(
                        supplier=supplier,
                        otif_rate=round(otif_rate, 2),
                        otif_previous=round(otif_previous, 2),
                        otif_trend_pct=round(otif_trend, 2),
                        lead_time_variability=round(lead_time_var, 2),
                        lead_time_avg=round(lead_time_avg, 2),
                        lead_time_trend=round(lead_time_trend, 2),
                        inventory_turnover_ratio=round(inventory_turnover, 2),
                        inventory_turnover_previous=round(inventory_turnover_prev, 2),
                        inventory_trend_pct=round(inventory_trend, 2),
                        stock_out_incidents=stock_outs,
                        low_stock_items_count=low_stock,
                        orders_pending_count=pending_orders,
                        orders_delayed_count=delayed_orders,
                        period_start=period_30,
                        period_end=today,
                    )
                    total_created += 1
                    logger.info(f"KPI snapshot created for {supplier.name}")

            except Exception as e:
                logger.error(f"Error calculating KPIs for {supplier.name}: {e}", exc_info=True)
                continue

        result = f"KPI calculation completed: {total_created} snapshots created"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in calculate_supply_chain_kpis: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=3)


# ============================================================================
# ALERT CHECKING AND TRIGGERING
# ============================================================================


@shared_task(bind=True, max_retries=2)
def check_supplier_health_alerts(self):
    """
    Check supplier health scores and trigger alerts.

    Triggered: Every 2 hours
    Critical: score < 60
    Warning: score dropped > 10 points in a week
    """
    logger.info("Checking supplier health alerts...")

    try:
        alerts_created = 0

        for scorecard in SupplierScorecard.objects.all():
            try:
                # Critical: score < 60
                if scorecard.health_score < 60:
                    # Check if alert already exists
                    existing = SupplyChainAlert.objects.filter(
                        supplier=scorecard.supplier, alert_type="supplier_health", status__in=["active", "acknowledged"]
                    ).first()

                    if not existing:
                        alert = SupplyChainAlert.objects.create(
                            alert_type="supplier_health",
                            severity="critical",
                            title=f"⚠️ Critical: {scorecard.supplier.name} Health Score {scorecard.health_score:.1f}/100",
                            description=f"""
                            Supplier {scorecard.supplier.name} has entered CRITICAL status.

                            Health Score: {scorecard.health_score:.1f}/100

                            Performance Breakdown:
                            • On-Time Delivery: {scorecard.on_time_delivery_pct:.1f}%
                            • Quality Performance: {scorecard.quality_performance_pct:.1f}%
                            • Lead Time Consistency: {scorecard.lead_time_consistency_pct:.1f}%
                            • Payment Reliability: {scorecard.payment_reliability_pct:.1f}%

                            Immediate review and corrective action required.
                                                        """,
                            supplier=scorecard.supplier,
                            metric_value=scorecard.health_score,
                            threshold_value=60,
                            notification_channels=["email", "push", "in_app"],
                            metadata={
                                "previous_score": None,
                                "on_time_delivery": scorecard.on_time_delivery_pct,
                                "quality_performance": scorecard.quality_performance_pct,
                                "lead_time_consistency": scorecard.lead_time_consistency_pct,
                            },
                        )
                        _trigger_alert_notification(alert, scorecard.supplier.user)
                        alerts_created += 1

                # Warning: score dropped > 10 points in a week
                week_ago = timezone.now() - timedelta(days=7)
                previous_scores = SupplierScoreHistory.objects.filter(
                    supplier=scorecard.supplier, recorded_at__gte=week_ago
                ).order_by("recorded_at")

                if previous_scores.exists():
                    oldest_score = previous_scores.first().health_score
                    score_drop = oldest_score - scorecard.health_score

                    if score_drop > 10:
                        existing = SupplyChainAlert.objects.filter(
                            supplier=scorecard.supplier,
                            alert_type="supplier_health",
                            status__in=["active", "acknowledged"],
                            severity="warning",
                        ).first()

                        if not existing:
                            alert = SupplyChainAlert.objects.create(
                                alert_type="supplier_health",
                                severity="warning",
                                title=f"⚠️ Warning: {scorecard.supplier.name} Health Declining",
                                description=f"""
                                    Supplier health score has declined significantly.

                                    Previous (7 days ago): {oldest_score:.1f}
                                    Current: {scorecard.health_score:.1f}
                                    Decline: {score_drop:.1f} points

                                    Monitor closely for further deterioration.
                                """,
                                supplier=scorecard.supplier,
                                metric_value=scorecard.health_score,
                                threshold_value=oldest_score,
                                notification_channels=["email", "in_app"],
                                metadata={
                                    "previous_score": round(oldest_score, 2),
                                    "score_drop": round(score_drop, 2),
                                },
                            )
                            _trigger_alert_notification(alert, scorecard.supplier.user)
                            alerts_created += 1

            except Exception as e:
                logger.error(f"Error checking alerts for {scorecard.supplier.name}: {e}", exc_info=True)
                continue

        result = f"Supplier health alerts checked: {alerts_created} created"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in check_supplier_health_alerts: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=2)


@shared_task(bind=True, max_retries=2)
def check_otif_alerts(self):
    """
    Check OTIF rates and trigger alerts if falling below threshold.

    Triggered: Every 2 hours
    Critical: OTIF < 90%
    Warning: OTIF trending down > 5%
    """
    logger.info("Checking OTIF alerts...")

    try:
        alerts_created = 0
        threshold = AlertThreshold.objects.filter(alert_type="otif").first()
        critical_threshold = threshold.critical_threshold if threshold else 90

        today = timezone.now().date()
        kpis = SupplyChainKPI.objects.filter(supplier__isnull=False, snapshot_date=today)

        for kpi in kpis:
            try:
                # Critical: OTIF < 90%
                if kpi.otif_rate < critical_threshold and kpi.otif_previous >= critical_threshold:
                    existing = SupplyChainAlert.objects.filter(
                        supplier=kpi.supplier, alert_type="otif", status__in=["active", "acknowledged"], severity="critical"
                    ).first()

                    if not existing:
                        alert = SupplyChainAlert.objects.create(
                            alert_type="otif",
                            severity="critical",
                            title=f"🔴 Critical OTIF Alert: {kpi.supplier.name} ({kpi.otif_rate:.1f}%)",
                            description=f"""
                                On-Time In-Full rate has dropped below {critical_threshold}%.

                                Current: {kpi.otif_rate:.1f}%
                                Previous: {kpi.otif_previous:.1f}%
                                Change: {kpi.otif_trend_pct:+.1f}%

                                Investigate root causes immediately.
                            """,
                            supplier=kpi.supplier,
                            metric_value=kpi.otif_rate,
                            threshold_value=critical_threshold,
                            notification_channels=["email", "push", "in_app"],
                            metadata={
                                "otif_rate": kpi.otif_rate,
                                "previous_rate": kpi.otif_previous,
                                "trend_pct": kpi.otif_trend_pct,
                            },
                        )
                        _trigger_alert_notification(alert, kpi.supplier.user)
                        alerts_created += 1

                # Warning: trending downward
                elif kpi.otif_trend_pct < -5 and kpi.otif_previous >= critical_threshold:
                    existing = SupplyChainAlert.objects.filter(
                        supplier=kpi.supplier, alert_type="otif", status__in=["active", "acknowledged"], severity="warning"
                    ).first()

                    if not existing:
                        alert = SupplyChainAlert.objects.create(
                            alert_type="otif",
                            severity="warning",
                            title=f"🟡 Warning: {kpi.supplier.name} OTIF Trending Down",
                            description=f"""
                                OTIF rate is declining: {kpi.otif_previous:.1f}% → {kpi.otif_rate:.1f}%
                                Trend: {kpi.otif_trend_pct:.1f}%

                                Monitor for continued deterioration.
                            """,
                            supplier=kpi.supplier,
                            notification_channels=["email", "in_app"],
                            metadata={
                                "otif_rate": kpi.otif_rate,
                                "trend_pct": kpi.otif_trend_pct,
                            },
                        )
                        _trigger_alert_notification(alert, kpi.supplier.user)
                        alerts_created += 1

            except Exception as e:
                logger.error(f"Error checking OTIF for {kpi.supplier.name}: {e}", exc_info=True)
                continue

        result = f"OTIF alerts checked: {alerts_created} created"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in check_otif_alerts: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=2)


@shared_task(bind=True, max_retries=2)
def check_stock_alerts(self):
    """
    Check inventory levels and trigger stock alerts.

    Triggered: Every 15 minutes
    Critical: Items below safety stock
    Warning: Items approaching reorder point
    """
    logger.info("Checking stock alerts...")

    try:
        alerts_created = 0

        # Critical: below safety stock
        critical_products = Product.objects.filter(stock__lt=F("safety_stock")).select_related("user")

        for product in critical_products:
            try:
                # Check if alert already exists
                existing = SupplyChainAlert.objects.filter(
                    product=product, alert_type="stock_low", status__in=["active", "acknowledged"]
                ).first()

                if not existing:
                    alert = SupplyChainAlert.objects.create(
                        alert_type="stock_low",
                        severity="critical",
                        title=f"🔴 Critical: {product.name} Below Safety Stock",
                        description=f"""
                            Product {product.name} has fallen below safety stock level.

                            Current Stock: {product.stock}
                            Safety Stock: {product.safety_stock}
                            Deficit: {product.safety_stock - product.stock}

                            Reorder immediately to maintain service level.
                        """,
                        product=product,
                        supplier=None,
                        metric_value=float(product.stock),
                        threshold_value=float(product.safety_stock),
                        notification_channels=["email", "push", "in_app"],
                        metadata={
                            "current_stock": product.stock,
                            "safety_stock": product.safety_stock,
                            "reorder_point": product.reorder_point,
                        },
                    )
                    _trigger_alert_notification(alert, product.user)
                    alerts_created += 1

            except Exception as e:
                logger.error(f"Error creating stock alert for {product.name}: {e}", exc_info=True)
                continue

        result = f"Stock alerts checked: {alerts_created} created"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in check_stock_alerts: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=2)


@shared_task(bind=True, max_retries=2)
def auto_resolve_alerts(self):
    """
    Auto-resolve alerts when conditions normalize for 24 hours.

    Triggered: Daily at 2 AM
    """
    logger.info("Auto-resolving normalized alerts...")

    try:
        resolution_window = timezone.now() - timedelta(hours=24)

        alerts_to_check = SupplyChainAlert.objects.filter(
            status__in=["active", "acknowledged"], triggered_at__lt=resolution_window
        )

        total_resolved = 0

        for alert in alerts_to_check:
            try:
                should_resolve = False

                if alert.alert_type == "supplier_health":
                    scorecard = SupplierScorecard.objects.filter(supplier=alert.supplier).first()

                    if scorecard and scorecard.health_score >= 60:
                        should_resolve = True

                elif alert.alert_type == "otif":
                    kpi = SupplyChainKPI.objects.filter(supplier=alert.supplier).order_by("-snapshot_date").first()

                    if kpi and kpi.otif_rate >= 90:
                        should_resolve = True

                elif alert.alert_type == "stock_low":
                    product = alert.product
                    if product and product.stock >= product.safety_stock:
                        should_resolve = True

                if should_resolve:
                    alert.auto_resolve()
                    total_resolved += 1
                    logger.info(f"Auto-resolved alert: {alert.alert_id}")

            except Exception as e:
                logger.error(f"Error auto-resolving alert {alert.alert_id}: {e}", exc_info=True)
                continue

        result = f"Auto-resolution completed: {total_resolved} alerts resolved"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in auto_resolve_alerts: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=2)


@shared_task(bind=True, max_retries=3)
def calculate_risk_categories(self, supplier_id=None):
    """
    Calculate overall risk categories and drill-down details.

    Triggered: Daily at 6 AM
    Supports per-supplier or global calculation.
    """
    logger.info(f"Calculating risk categories for supplier={supplier_id}")

    try:
        from producer.models import Producer

        today = timezone.now().date()
        period_30 = today - timedelta(days=30)
        period_90 = today - timedelta(days=90)

        # Get suppliers to process
        if supplier_id:
            suppliers = [Producer.objects.get(id=supplier_id)]
        else:
            suppliers = Producer.objects.filter(is_active=True)

        total_created = 0

        for supplier in suppliers:
            try:
                # 1. SUPPLIER RISK
                scorecard = SupplierScorecard.objects.filter(supplier=supplier).first()

                high_risk_suppliers = SupplierScorecard.objects.filter(health_score__lt=70).count()
                all_suppliers = SupplierScorecard.objects.count()

                # Spend at risk
                spend_at_risk = Order.objects.filter(
                    order_date__date__gte=period_90, user__scorecard__health_score__lt=70
                ).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")

                # Single-source dependencies
                single_source_deps = (
                    Product.objects.filter(user=supplier.user)
                    .values("id")
                    .annotate(supplier_count=Count("user", distinct=True))
                    .filter(supplier_count=1)
                    .count()
                )

                supplier_risk_pct = (high_risk_suppliers / all_suppliers * 100) if all_suppliers > 0 else 0
                supplier_risk_level = "high" if supplier_risk_pct > 20 else "medium" if supplier_risk_pct > 10 else "low"

                # 2. LOGISTICS RISK
                delayed_deliveries = Delivery.objects.filter(
                    created_at__date__gte=period_30,
                    status__in=[TransportStatus.IN_TRANSIT, TransportStatus.AVAILABLE],
                    requested_delivery_date__lt=timezone.now(),
                )

                active_delays = delayed_deliveries.count()
                avg_delay_days = 0.0

                if active_delays > 0:
                    delays = (
                        delayed_deliveries.aggregate(
                            avg_delay=Avg(
                                ExpressionWrapper(
                                    (timezone.now().date() - F("requested_delivery_date__date")), output_field=FloatField()
                                )
                            )
                        )["avg_delay"]
                        or 0
                    )
                    avg_delay_days = float(delays) if delays else 0

                # Routes with issues
                routes_with_issues = (
                    delayed_deliveries.values("pickup_address", "delivery_address")
                    .annotate(delay_count=Count("id"))
                    .filter(delay_count__gt=1)
                    .count()
                )

                logistics_risk_level = "high" if active_delays > 10 else "medium" if active_delays > 0 else "low"

                # 3. DEMAND RISK
                sales_30 = Sale.objects.filter(user=supplier.user, sale_date__date__gte=period_30)

                forecast_errors = []
                volatile_products = []

                for product in Product.objects.filter(user=supplier.user):
                    sales = sales_30.filter(order__product=product).values_list("quantity", flat=True)

                    if sales:
                        actual_avg = statistics.mean(sales)
                        if hasattr(product, "avg_daily_demand") and product.avg_daily_demand > 0:
                            error = abs(actual_avg - product.avg_daily_demand) / product.avg_daily_demand * 100
                            forecast_errors.append(error)

                        # Volatility
                        std_dev = statistics.stdev(sales) if len(sales) > 1 else 0
                        cv = std_dev / actual_avg if actual_avg > 0 else 0
                        if cv > 0.5:
                            volatile_products.append(product)

                forecast_accuracy = 100 - (statistics.mean(forecast_errors) if forecast_errors else 0)

                # Stock-outs
                stockouts_30 = StockHistory.objects.filter(
                    product__user=supplier.user, date__gte=period_30, quantity_in=0, quantity_out__gt=0, stock_after=0
                ).count()

                demand_risk_level = "high" if forecast_accuracy < 80 else "medium" if forecast_accuracy < 90 else "low"

                # 4. INVENTORY RISK
                low_stock = Product.objects.filter(user=supplier.user, stock__lt=F("reorder_point")).count()

                overstock = Product.objects.filter(
                    user=supplier.user, stock__gt=F("lead_time_days") * F("avg_daily_demand") * 180
                ).count()

                overstock_value = Product.objects.filter(
                    user=supplier.user, stock__gt=F("lead_time_days") * F("avg_daily_demand") * 180
                ).aggregate(total=Sum(ExpressionWrapper(F("stock") * F("cost_price"), output_field=FloatField())))[
                    "total"
                ] or Decimal(
                    "0.00"
                )

                inventory_risk_level = "high" if low_stock > 10 else "medium" if low_stock > 0 else "low"

                # 5. OVERALL RISK SCORE
                risk_scores = {
                    "supplier": 1 if supplier_risk_level == "high" else 0.5 if supplier_risk_level == "medium" else 0,
                    "logistics": 1 if logistics_risk_level == "high" else 0.5 if logistics_risk_level == "medium" else 0,
                    "demand": 1 if demand_risk_level == "high" else 0.5 if demand_risk_level == "medium" else 0,
                    "inventory": 1 if inventory_risk_level == "high" else 0.5 if inventory_risk_level == "medium" else 0,
                }

                overall_risk_score = (
                    (risk_scores["supplier"] * 0.25)
                    + (risk_scores["logistics"] * 0.25)
                    + (risk_scores["demand"] * 0.25)
                    + (risk_scores["inventory"] * 0.25)
                ) * 100

                overall_risk_level = "high" if overall_risk_score > 66 else "medium" if overall_risk_score > 33 else "low"

                # 6. Create/update risk category
                with transaction.atomic():
                    risk_category, created = RiskCategory.objects.update_or_create(
                        supplier=supplier,
                        snapshot_date=today,
                        defaults={
                            "supplier_risk_level": supplier_risk_level,
                            "supplier_high_risk_count": high_risk_suppliers,
                            "supplier_spend_at_risk": spend_at_risk,
                            "single_source_dependencies": single_source_deps,
                            "logistics_risk_level": logistics_risk_level,
                            "active_shipment_delays": active_delays,
                            "avg_delay_days": round(avg_delay_days, 2),
                            "routes_with_issues": routes_with_issues,
                            "demand_risk_level": demand_risk_level,
                            "forecast_accuracy": round(forecast_accuracy, 2),
                            "volatile_products_count": len(volatile_products),
                            "stockout_incidents": stockouts_30,
                            "inventory_risk_level": inventory_risk_level,
                            "items_below_safety_stock": low_stock,
                            "overstock_items_count": overstock,
                            "total_inventory_value_at_risk": overstock_value,
                            "overall_risk_score": round(overall_risk_score, 2),
                            "overall_risk_level": overall_risk_level,
                        },
                    )

                    # 7. Create drill-down records
                    # Supplier risk drill-downs
                    high_risk_scorecards = SupplierScorecard.objects.filter(health_score__lt=70)
                    for hsc in high_risk_scorecards:
                        RiskDrillDown.objects.update_or_create(
                            risk_category=risk_category,
                            risk_type="supplier_health",
                            item_type="supplier",
                            item_id=hsc.supplier.id,
                            defaults={
                                "item_name": hsc.supplier.name,
                                "metric_value": hsc.health_score,
                                "threshold": 70,
                                "status": "critical" if hsc.health_score < 60 else "warning",
                                "details": {
                                    "on_time_delivery": hsc.on_time_delivery_pct,
                                    "quality": hsc.quality_performance_pct,
                                    "lead_time": hsc.lead_time_consistency_pct,
                                },
                            },
                        )

                    total_created += 1
                    logger.info(
                        f"Risk assessment created for {supplier.name}: {overall_risk_level} ({overall_risk_score:.1f})"
                    )

            except Exception as e:
                logger.error(f"Error calculating risk for {supplier.name}: {e}", exc_info=True)
                continue

        result = f"Risk categories calculated: {total_created} created"
        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Critical error in calculate_risk_categories: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300, max_retries=3)


def _trigger_alert_notification(alert, user):
    """
    Send notification for an alert using the notification system.

    Args:
        alert (SupplyChainAlert): The alert to notify about
        user (User): The user to notify
    """
    try:
        Notification.objects.create(
            user=user,
            title=alert.title,
            message=alert.description[:500],
            notification_type=alert.severity,
            related_id=str(alert.alert_id),
            action_url=f"/api/v1/alerts/{alert.alert_id}/",
        )

        alert.is_notified = True
        alert.save(update_fields=["is_notified", "updated_at"])

        logger.info(f"Notification sent for alert {alert.alert_id}")

    except Exception as e:
        logger.error(f"Error sending alert notification for {alert.alert_id}: {e}", exc_info=True)
