# Supply Chain Risk Management Dashboard - Deep Dive Implementation Plan

## Executive Summary

This document provides a comprehensive implementation strategy for integrating the Risk Management Dashboard into your existing Django/DRF supply chain backend. The plan maps core features to your current architecture, leveraging existing patterns for Orders, Sales, Deliveries, and Celery-based automation.

---

## Part 1: System Architecture Analysis

### 1.1 Current System Components

#### **Data Layers**
Your system has multi-layered order/sales tracking:

```
User → Producer (Supplier)
  ↓
Order (producer.models.Order)
  ├─ Customer
  ├─ Product
  ├─ Status: pending → approved → shipped → delivered
  ├─ order_date, delivery_date
  └─ total_price, notes

Sale (producer.models.Sale)
  ├─ Order (FK)
  ├─ quantity, sale_price
  ├─ payment_status
  ├─ payment (FK to Payment model)
  └─ user

Delivery (transport.models.Delivery)
  ├─ sale (FK) or marketplace_sale (FK)
  ├─ transporter (FK to Transporter)
  ├─ status: available → assigned → picked_up → in_transit → delivered
  ├─ requested_pickup_date, requested_delivery_date
  ├─ picked_up_at, delivered_at, cancelled_at
  └─ delivery_fee, distance_km

Payment (producer.models.Payment)
  ├─ order (FK)
  ├─ amount, method, status
  └─ gateway_token
```

**Key Insight**: You have **two parallel order systems**:
- **Producer Orders**: B2B wholesale orders (Producer → Customer)
- **Marketplace Orders**: Marketplace purchases (implemented in `market.models.MarketplaceSale`)

#### **Automation Infrastructure**
Your system uses **Celery Beat** for periodic tasks:

```
CELERY_BROKER_URL = Redis
CELERY_RESULT_BACKEND = Redis
CELERY_TIMEZONE = UTC

Beat Schedule Examples:
- move_large_stock_to_stocklist: Every 3 hours
- recalc_inventory_parameters: Every hour
- send_scheduled_notifications: Every 5 minutes
- periodic_delivery_reminders: Every 15 minutes
- periodic_cleanup_deliveries: Daily at 1 AM
```

#### **Notification System**
You have an advanced **notification rules engine**:

```
NotificationRule (notification.models.NotificationRule)
  ├─ Trigger Events: order_created, delivery_assigned, delivery_completed, etc.
  ├─ Conditions: field, operator (eq, ne, gt, gte, lt, etc.), value
  ├─ Template (FK to NotificationTemplate)
  └─ target_users, delay_minutes, priority

NotificationTemplate
  ├─ template_type: push, email, sms, in_app
  ├─ title_template, body_template (supports {variable} placeholders)
  └─ variables: list of available context fields

UserNotificationPreference
  ├─ push_enabled, email_enabled, sms_enabled, in_app_enabled
  ├─ event_specific preferences
  ├─ quiet_hours
  └─ timezone
```

#### **Inventory Tracking**
Product inventory with predictive analytics:

```
Product (producer.models.Product)
  ├─ stock: current quantity
  ├─ lead_time_days
  ├─ avg_daily_demand, stddev_daily_demand (calculated)
  ├─ safety_stock, reorder_point, reorder_quantity (calculated)
  ├─ projected_stockout_date_field
  └─ updated via recalc_inventory_parameters task

StockHistory (producer.models.StockHistory)
  ├─ product, date, quantity_in, quantity_out
  ├─ stock_after, notes
  └─ Immutable after creation (audit trail)

StockList
  ├─ Product overflow tracking
  └─ is_pushed_to_marketplace
```

---

## Part 2: Risk Management Feature Mapping

### 2.1 Supplier Health Scorecard

#### **Data Sources in Your System**

| Metric | Current Implementation | Data Model |
|--------|----------------------|-----------|
| On-Time Delivery % | Order.delivery_date vs. actual delivery completion | Order + Delivery |
| Quality Performance | Not yet tracked, needs implementation | New: Product Defect/Return tracking |
| Lead Time Consistency | Product.lead_time_days + actual variance | Product + StockHistory |
| Payment History | Payment.status tracking | Payment model |
| Communication Response | Not yet tracked | New: Communication tracking |

#### **Implementation Strategy**

**Step 1: Create New Models** (Add to `producer/models.py`)

```python
class SupplierScorecard(models.Model):
    """
    Tracks supplier performance metrics and calculated health scores.
    Updated daily by Celery task.
    """
    supplier = models.OneToOneField(Producer, on_delete=models.CASCADE, related_name='scorecard')
    
    # Score Metrics (0-100)
    on_time_delivery_pct = models.FloatField(default=0)  # Percentage of orders delivered on-time
    quality_performance_pct = models.FloatField(default=100)  # 100% - defect_rate
    lead_time_consistency_pct = models.FloatField(default=100)  # Consistency rating
    payment_reliability_pct = models.FloatField(default=100)  # On-time payment %
    
    # Weighted Health Score
    health_score = models.FloatField(default=80)  # Overall score (0-100)
    health_status = models.CharField(
        max_length=20,
        choices=[
            ('healthy', 'Healthy (80-100)'),
            ('monitor', 'Monitor (60-79)'),
            ('critical', 'Critical (0-59)'),
        ],
        default='healthy'
    )
    
    # Supporting Metrics
    total_orders = models.IntegerField(default=0)
    on_time_orders = models.IntegerField(default=0)
    defect_count = models.IntegerField(default=0)
    avg_lead_time_days = models.FloatField(default=0)
    lead_time_variance = models.FloatField(default=0)  # std dev
    late_payments_count = models.IntegerField(default=0)
    
    # Timestamps
    last_calculated = models.DateTimeField(auto_now=True)
    calculation_period_start = models.DateField()  # Start of 90-day window
    
    class Meta:
        verbose_name = "Supplier Scorecard"
        verbose_name_plural = "Supplier Scorecards"

class SupplierScoreHistory(models.Model):
    """
    Historical tracking of supplier scores for trend analysis (90-day retention).
    """
    supplier = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name='score_history')
    health_score = models.FloatField()
    health_status = models.CharField(max_length=20)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Supplier Score History"
        verbose_name_plural = "Supplier Score Histories"
        indexes = [
            models.Index(fields=['supplier', 'recorded_at']),
        ]

class ProductDefectRecord(models.Model):
    """
    Track product defects/returns for quality metrics.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='defect_records')
    supplier = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name='defect_records')
    
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    defect_date = models.DateTimeField(auto_now_add=True)
    defect_type = models.CharField(
        max_length=50,
        choices=[
            ('quality', 'Quality Issue'),
            ('damage', 'Damage'),
            ('missing_items', 'Missing Items'),
            ('other', 'Other'),
        ]
    )
    quantity_defective = models.IntegerField()
    description = models.TextField()
    resolution_status = models.CharField(
        max_length=20,
        choices=[
            ('open', 'Open'),
            ('resolved', 'Resolved'),
            ('escalated', 'Escalated'),
        ],
        default='open'
    )
    
    class Meta:
        verbose_name = "Product Defect Record"
        verbose_name_plural = "Product Defect Records"
```

**Step 2: Create Celery Task** (Add to `producer/tasks.py`)

```python
@shared_task(bind=True, max_retries=3)
def calculate_supplier_health_scores():
    """
    Daily task (midnight) to calculate supplier health scores.
    Triggered by Celery Beat.
    """
    logger.info("Starting supplier health score calculation...")
    
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models import Count, Q, Avg
    from .models import SupplierScorecard, SupplierScoreHistory, ProductDefectRecord
    
    cutoff_90 = timezone.now() - timedelta(days=90)
    cutoff_14 = timezone.now() - timedelta(days=14)
    
    suppliers = Producer.objects.all()
    
    for supplier in suppliers:
        try:
            # 1. Calculate On-Time Delivery %
            total_orders = Order.objects.filter(
                user=supplier.user,
                order_date__gte=cutoff_90
            ).count()
            
            if total_orders > 0:
                # Orders delivered on-time (delivery_date <= requested)
                on_time_orders = Order.objects.filter(
                    user=supplier.user,
                    order_date__gte=cutoff_90,
                    delivery_date__isnull=False
                ).annotate(
                    is_on_time=Case(
                        When(delivery_date__lte=F('order_date') + timedelta(days=Product.lead_time_days)),
                        then=Value(1)
                    )
                ).aggregate(count=Count('id', filter=Q(is_on_time=1)))
                
                on_time_pct = (on_time_orders['count'] / total_orders) * 100
            else:
                on_time_pct = 100
            
            # 2. Calculate Quality Performance % (100% - defect_rate)
            defects = ProductDefectRecord.objects.filter(
                supplier=supplier,
                defect_date__gte=cutoff_90
            ).count()
            
            total_sold = Sale.objects.filter(
                user=supplier.user,
                sale_date__gte=cutoff_90
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            quality_pct = 100 - ((defects / total_sold * 100) if total_sold > 0 else 0)
            quality_pct = max(0, quality_pct)
            
            # 3. Calculate Lead Time Consistency
            # Get variance of actual vs promised lead times
            lead_times = Sale.objects.filter(
                user=supplier.user,
                sale_date__gte=cutoff_90
            ).annotate(
                actual_lead_days=ExpressionWrapper(
                    (F('created_at') - F('order__order_date')) / timedelta(days=1),
                    output_field=FloatField()
                )
            ).values_list('actual_lead_days', flat=True)
            
            if lead_times:
                avg_lead_time = statistics.mean(lead_times)
                lead_time_var = statistics.pstdev(lead_times) if len(lead_times) > 1 else 0
                # Consistency: lower variance = higher score
                # If variance > 5 days, it's concerning
                consistency_pct = max(0, 100 - (lead_time_var * 5))
            else:
                avg_lead_time = 0
                lead_time_var = 0
                consistency_pct = 100
            
            # 4. Weighted Health Score
            # On-Time Delivery (50%) + Quality (30%) + Lead Time Consistency (20%)
            health_score = (
                on_time_pct * 0.50 +
                quality_pct * 0.30 +
                consistency_pct * 0.20
            )
            
            # Determine status
            if health_score >= 80:
                status = 'healthy'
            elif health_score >= 60:
                status = 'monitor'
            else:
                status = 'critical'
            
            # 5. Update or create scorecard
            scorecard, created = SupplierScorecard.objects.update_or_create(
                supplier=supplier,
                defaults={
                    'health_score': round(health_score, 2),
                    'health_status': status,
                    'total_orders': total_orders,
                    'on_time_orders': on_time_orders.get('count', 0),
                    'on_time_delivery_pct': round(on_time_pct, 2),
                    'quality_performance_pct': round(quality_pct, 2),
                    'lead_time_consistency_pct': round(consistency_pct, 2),
                    'avg_lead_time_days': round(avg_lead_time, 2),
                    'lead_time_variance': round(lead_time_var, 2),
                    'calculation_period_start': cutoff_90.date(),
                }
            )
            
            # 6. Store historical snapshot
            SupplierScoreHistory.objects.create(
                supplier=supplier,
                health_score=health_score,
                health_status=status
            )
            
            # 7. Trigger alerts if status dropped or is critical
            if scorecard.health_status == 'critical':
                trigger_supplier_alert(supplier, 'critical', health_score)
            
            logger.info(f"Updated scorecard for {supplier.name}: {health_score:.2f} ({status})")
            
        except Exception as e:
            logger.error(f"Error calculating score for {supplier.name}: {e}")
            continue
    
    return f"Calculated health scores for {suppliers.count()} suppliers"
```

---

### 2.2 Key Performance Indicators (KPIs) Dashboard

#### **Implementation Strategy**

**Step 1: Create KPI Model** (Add to `producer/models.py`)

```python
class SupplyChainKPI(models.Model):
    """
    Daily snapshot of key supply chain metrics.
    Supports multi-tenant (per-supplier) or global reporting.
    """
    supplier = models.ForeignKey(
        Producer,
        on_delete=models.CASCADE,
        related_name='kpi_snapshots',
        null=True,
        blank=True,
        help_text="NULL = global/aggregate KPIs"
    )
    
    # OTIF Rate (On-Time In-Full)
    otif_rate = models.FloatField(default=0)  # Percentage
    otif_previous = models.FloatField(default=0)  # Previous period for trend
    otif_trend_pct = models.FloatField(default=0)  # % change
    
    # Lead Time Variability
    lead_time_variability = models.FloatField(default=0)  # Std dev in days
    lead_time_avg = models.FloatField(default=0)  # Average days
    lead_time_trend = models.FloatField(default=0)  # Change in variability
    
    # Inventory Turnover
    inventory_turnover_ratio = models.FloatField(default=0)
    inventory_turnover_previous = models.FloatField(default=0)
    inventory_trend_pct = models.FloatField(default=0)
    
    # Additional Metrics
    stock_out_incidents = models.IntegerField(default=0)
    low_stock_items_count = models.IntegerField(default=0)
    orders_pending_count = models.IntegerField(default=0)
    orders_delayed_count = models.IntegerField(default=0)
    
    # Metadata
    period_start = models.DateField()
    period_end = models.DateField()
    snapshot_date = models.DateField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Supply Chain KPI"
        verbose_name_plural = "Supply Chain KPIs"
        indexes = [
            models.Index(fields=['supplier', 'snapshot_date']),
            models.Index(fields=['snapshot_date']),
        ]
```

**Step 2: Celery Task for KPI Calculation** (Add to `producer/tasks.py`)

```python
@shared_task(bind=True)
def calculate_supply_chain_kpis(self, supplier_id=None):
    """
    Calculate OTIF, Lead Time Variability, Inventory Turnover.
    Can be run globally or per-supplier.
    
    Frequency: Every 6 hours
    """
    from datetime import timedelta, date
    from django.utils import timezone
    from django.db.models import Count, Sum, Avg, Q, F
    import statistics
    
    logger.info(f"Calculating KPIs for supplier={supplier_id}")
    
    # Define comparison periods
    today = timezone.now().date()
    period_30 = today - timedelta(days=30)
    period_60 = today - timedelta(days=60)
    period_90 = today - timedelta(days=90)
    
    # Get suppliers to process
    if supplier_id:
        suppliers = Producer.objects.filter(id=supplier_id)
    else:
        suppliers = Producer.objects.filter(is_active=True)
    
    for supplier in suppliers:
        try:
            # 1. OTIF Rate Calculation
            # On-Time: delivered within promised date
            # In-Full: complete quantity delivered
            
            orders_30 = Order.objects.filter(
                user=supplier.user,
                order_date__date__gte=period_30
            )
            
            otif_orders = orders_30.annotate(
                is_on_time=Case(
                    When(
                        delivery_date__isnull=False,
                        delivery_date__lte=F('order_date') + timedelta(days=7),  # Assume 7-day promise
                        then=Value(True)
                    ),
                    default=Value(False),
                    output_field=BooleanField()
                ),
                is_complete=Case(
                    When(quantity=F('sale__quantity'), then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                )
            ).filter(is_on_time=True, is_complete=True).count()
            
            otif_rate = (otif_orders / orders_30.count() * 100) if orders_30.exists() else 100
            
            # Compare to previous 30-day period
            orders_60_90 = Order.objects.filter(
                user=supplier.user,
                order_date__date__gte=period_60,
                order_date__date__lt=period_30
            )
            
            otif_orders_prev = orders_60_90.annotate(
                is_on_time=Case(When(delivery_date__lte=F('order_date') + timedelta(days=7), then=Value(True)), default=Value(False), output_field=BooleanField()),
                is_complete=Case(When(quantity=F('sale__quantity'), then=Value(True)), default=Value(False), output_field=BooleanField())
            ).filter(is_on_time=True, is_complete=True).count()
            
            otif_previous = (otif_orders_prev / orders_60_90.count() * 100) if orders_60_90.exists() else 100
            otif_trend = ((otif_rate - otif_previous) / otif_previous * 100) if otif_previous > 0 else 0
            
            # 2. Lead Time Variability
            sales_30 = Sale.objects.filter(
                user=supplier.user,
                sale_date__date__gte=period_30
            ).annotate(
                actual_lead_days=ExpressionWrapper(
                    (F('created_at') - F('order__order_date')) / timedelta(days=1),
                    output_field=FloatField()
                )
            ).values_list('actual_lead_days', flat=True)
            
            if sales_30:
                lead_time_avg = statistics.mean(sales_30)
                lead_time_var = statistics.pstdev(sales_30) if len(sales_30) > 1 else 0
            else:
                lead_time_avg = 0
                lead_time_var = 0
            
            # Previous period
            sales_60_90 = Sale.objects.filter(
                user=supplier.user,
                sale_date__date__gte=period_60,
                sale_date__date__lt=period_30
            ).annotate(
                actual_lead_days=ExpressionWrapper(
                    (F('created_at') - F('order__order_date')) / timedelta(days=1),
                    output_field=FloatField()
                )
            ).values_list('actual_lead_days', flat=True)
            
            if sales_60_90:
                lead_time_var_prev = statistics.pstdev(sales_60_90) if len(sales_60_90) > 1 else 0
            else:
                lead_time_var_prev = 0
            
            lead_time_trend = lead_time_var - lead_time_var_prev
            
            # 3. Inventory Turnover
            # COGS / Average Inventory Value
            cogs = Sale.objects.filter(
                user=supplier.user,
                sale_date__date__gte=period_30
            ).aggregate(total=Sum(F('sale_price') * F('quantity')))['total'] or 0
            
            # Average inventory value = sum of (product.stock * unit_cost)
            avg_inventory = Product.objects.filter(
                user=supplier.user
            ).aggregate(
                total=Sum(F('stock') * F('cost_price'))
            )['total'] or 1  # Avoid division by zero
            
            inventory_turnover = cogs / avg_inventory if avg_inventory > 0 else 0
            
            # Previous period
            cogs_prev = Sale.objects.filter(
                user=supplier.user,
                sale_date__date__gte=period_60,
                sale_date__date__lt=period_30
            ).aggregate(total=Sum(F('sale_price') * F('quantity')))['total'] or 0
            
            inventory_turnover_prev = cogs_prev / avg_inventory if avg_inventory > 0 else 0
            inventory_trend = ((inventory_turnover - inventory_turnover_prev) / inventory_turnover_prev * 100) if inventory_turnover_prev > 0 else 0
            
            # 4. Additional metrics
            stock_outs = StockHistory.objects.filter(
                product__user=supplier.user,
                date__gte=period_30,
                quantity_in=0,
                quantity_out__gt=0,
                stock_after=0
            ).count()
            
            low_stock = Product.objects.filter(
                user=supplier.user,
                stock__lt=F('reorder_point')
            ).count()
            
            pending_orders = Order.objects.filter(
                user=supplier.user,
                status__in=['pending', 'approved']
            ).count()
            
            delayed_orders = Order.objects.filter(
                user=supplier.user,
                delivery_date__isnull=False,
                delivery_date__lt=timezone.now()
            ).count()
            
            # 5. Store KPI snapshot
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
            
            logger.info(f"KPI snapshot created for {supplier.name}")
            
        except Exception as e:
            logger.error(f"Error calculating KPIs for {supplier.name}: {e}")
            self.retry(exc=e, countdown=60)
```

---

### 2.3 Basic Alert System

#### **Implementation Strategy**

**Step 1: Create Alert Models** (Add to `producer/models.py`)

```python
class SupplyChainAlert(models.Model):
    """
    Automated alerts for supply chain risks and anomalies.
    """
    ALERT_TYPE_CHOICES = [
        ('supplier_health', 'Supplier Health Alert'),
        ('otif', 'OTIF Rate Alert'),
        ('lead_time', 'Lead Time Alert'),
        ('stock_low', 'Low Stock Alert'),
        ('stock_out', 'Stock Out Alert'),
        ('delayed_order', 'Delayed Order'),
        ('quality_issue', 'Quality Issue'),
        ('inventory_variance', 'Inventory Variance'),
    ]
    
    SEVERITY_CHOICES = [
        ('critical', 'Critical - Immediate Action'),
        ('warning', 'Warning - Review Soon'),
        ('info', 'Info - FYI'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('auto_resolved', 'Auto-Resolved'),
    ]
    
    # Identification
    alert_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Content
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Context (generic FK for flexibility)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')
    
    # Supplier/Product affected
    supplier = models.ForeignKey(Producer, on_delete=models.CASCADE, null=True, blank=True, related_name='supply_chain_alerts')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts')
    
    # Metric values
    metric_value = models.FloatField(null=True, blank=True)
    threshold_value = models.FloatField(null=True, blank=True)
    
    # Timeline
    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    auto_resolve_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Alert automatically resolved if condition normalizes for 24 hours"
    )
    
    # Recipient
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, help_text="Additional context (previous_value, trend, etc.)")
    is_notified = models.BooleanField(default=False)
    notification_channels = models.JSONField(default=list, help_text="['email', 'push', 'in_app']")
    
    class Meta:
        verbose_name = "Supply Chain Alert"
        verbose_name_plural = "Supply Chain Alerts"
        indexes = [
            models.Index(fields=['supplier', 'severity', 'status']),
            models.Index(fields=['alert_type', 'triggered_at']),
            models.Index(fields=['status', 'triggered_at']),
        ]
        ordering = ['-triggered_at']
    
    def acknowledge(self, user):
        """Mark alert as acknowledged."""
        self.status = 'acknowledged'
        self.acknowledged_at = timezone.now()
        self.assigned_to = user
        self.save()
    
    def resolve(self, user=None):
        """Manually resolve alert."""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        if user:
            self.assigned_to = user
        self.save()
    
    def __str__(self):
        return f"{self.alert_type} - {self.title} ({self.severity})"

class AlertThreshold(models.Model):
    """
    Configurable thresholds for alert generation.
    Allows admins to tune alert sensitivity.
    """
    alert_type = models.CharField(max_length=50, unique=True, choices=SupplyChainAlert.ALERT_TYPE_CHOICES)
    
    # Critical threshold
    critical_threshold = models.FloatField(help_text="Value that triggers CRITICAL alert")
    critical_enabled = models.BooleanField(default=True)
    
    # Warning threshold
    warning_threshold = models.FloatField(help_text="Value that triggers WARNING alert")
    warning_enabled = models.BooleanField(default=True)
    
    # Check frequency
    check_frequency_minutes = models.IntegerField(default=120, help_text="How often to check (for periodic checks)")
    
    # Auto-resolve window
    auto_resolve_hours = models.IntegerField(default=24, help_text="Auto-resolve if condition normalizes for N hours")
    
    # Description for UI
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Alert Threshold Configuration"
        verbose_name_plural = "Alert Threshold Configurations"
    
    def __str__(self):
        return f"Thresholds for {self.alert_type}"
```

**Step 2: Alert Generation Tasks** (Add to `producer/tasks.py`)

```python
@shared_task(bind=True)
def check_supplier_health_alerts():
    """
    Daily (every 2 hours) check supplier health scores against thresholds.
    Critical: score < 60
    Warning: score dropped > 10 points in a week
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.contrib.contenttypes.models import ContentType
    
    logger.info("Checking supplier health alerts...")
    
    scorecard_ct = ContentType.objects.get_for_model(SupplierScorecard)
    
    for scorecard in SupplierScorecard.objects.all():
        try:
            # Critical: score < 60
            if scorecard.health_score < 60:
                # Check if alert already exists and is active
                existing = SupplyChainAlert.objects.filter(
                    supplier=scorecard.supplier,
                    alert_type='supplier_health',
                    status__in=['active', 'acknowledged']
                ).first()
                
                if not existing:
                    alert = SupplyChainAlert.objects.create(
                        alert_type='supplier_health',
                        severity='critical',
                        title=f"Critical: {scorecard.supplier.name} Health Score at {scorecard.health_score:.1f}",
                        description=f"""
                            Supplier {scorecard.supplier.name} has a critical health score of {scorecard.health_score:.1f}/100.
                            
                            On-Time Delivery: {scorecard.on_time_delivery_pct:.1f}%
                            Quality Performance: {scorecard.quality_performance_pct:.1f}%
                            Lead Time Consistency: {scorecard.lead_time_consistency_pct:.1f}%
                            
                            Immediate review and action required.
                        """,
                        supplier=scorecard.supplier,
                        content_type=scorecard_ct,
                        object_id=scorecard.id,
                        metric_value=scorecard.health_score,
                        threshold_value=60,
                        notification_channels=['email', 'push', 'in_app'],
                    )
                    
                    # Send notification
                    trigger_alert_notification(alert, scorecard.supplier.user)
            
            # Warning: score dropped > 10 points in a week
            week_ago = timezone.now() - timedelta(days=7)
            previous_score = SupplierScoreHistory.objects.filter(
                supplier=scorecard.supplier,
                recorded_at__gte=week_ago
            ).order_by('recorded_at').first()
            
            if previous_score and (previous_score.health_score - scorecard.health_score) > 10:
                existing = SupplyChainAlert.objects.filter(
                    supplier=scorecard.supplier,
                    alert_type='supplier_health',
                    status__in=['active', 'acknowledged'],
                    severity='warning'
                ).first()
                
                if not existing:
                    alert = SupplyChainAlert.objects.create(
                        alert_type='supplier_health',
                        severity='warning',
                        title=f"Warning: {scorecard.supplier.name} Health Declined {previous_score.health_score - scorecard.health_score:.1f} Points",
                        description=f"Health score declined from {previous_score.health_score:.1f} to {scorecard.health_score:.1f} in the last 7 days.",
                        supplier=scorecard.supplier,
                        severity='warning',
                        notification_channels=['email', 'in_app'],
                    )
                    
                    trigger_alert_notification(alert, scorecard.supplier.user)
        
        except Exception as e:
            logger.error(f"Error checking alerts for {scorecard.supplier.name}: {e}")
            continue
    
    return "Supplier health alerts checked"

@shared_task(bind=True)
def check_otif_alerts():
    """
    Check OTIF rates and trigger alerts if falling below 90%.
    """
    logger.info("Checking OTIF alerts...")
    
    for kpi in SupplyChainKPI.objects.filter(
        supplier__isnull=False,
        snapshot_date=timezone.now().date()
    ):
        try:
            if kpi.otif_rate < 90 and kpi.otif_previous >= 90:
                # Alert: just dropped below 90%
                alert = SupplyChainAlert.objects.create(
                    alert_type='otif',
                    severity='critical',
                    title=f"Critical: {kpi.supplier.name} OTIF Rate Below 90% ({kpi.otif_rate:.1f}%)",
                    description=f"On-Time In-Full rate dropped from {kpi.otif_previous:.1f}% to {kpi.otif_rate:.1f}%.",
                    supplier=kpi.supplier,
                    metric_value=kpi.otif_rate,
                    threshold_value=90,
                    notification_channels=['email', 'push', 'in_app'],
                )
                trigger_alert_notification(alert, kpi.supplier.user)
            
            elif kpi.otif_trend_pct < -5 and kpi.otif_previous >= 90:
                # Warning: trending downward for 2+ periods
                alert = SupplyChainAlert.objects.create(
                    alert_type='otif',
                    severity='warning',
                    title=f"Warning: {kpi.supplier.name} OTIF Trending Down ({kpi.otif_trend_pct:.1f}%)",
                    description=f"OTIF declining: {kpi.otif_previous:.1f}% → {kpi.otif_rate:.1f}%",
                    supplier=kpi.supplier,
                    notification_channels=['email', 'in_app'],
                )
                trigger_alert_notification(alert, kpi.supplier.user)
        
        except Exception as e:
            logger.error(f"Error checking OTIF for {kpi.supplier.name}: {e}")
            continue
    
    return "OTIF alerts checked"

@shared_task(bind=True)
def auto_resolve_alerts():
    """
    Daily task to auto-resolve alerts if condition normalizes for 24 hours.
    """
    from datetime import timedelta
    from django.utils import timezone
    
    logger.info("Auto-resolving normalized alerts...")
    
    resolution_window = timezone.now() - timedelta(hours=24)
    
    alerts_to_check = SupplyChainAlert.objects.filter(
        status__in=['active', 'acknowledged'],
        triggered_at__lt=resolution_window
    )
    
    for alert in alerts_to_check:
        try:
            # Check if condition still exists
            should_resolve = False
            
            if alert.alert_type == 'supplier_health':
                scorecard = SupplierScorecard.objects.filter(
                    supplier=alert.supplier
                ).order_by('-last_calculated').first()
                
                if scorecard and scorecard.health_score >= 60:
                    should_resolve = True
            
            elif alert.alert_type == 'otif':
                kpi = SupplyChainKPI.objects.filter(
                    supplier=alert.supplier
                ).order_by('-snapshot_date').first()
                
                if kpi and kpi.otif_rate >= 90:
                    should_resolve = True
            
            if should_resolve:
                alert.status = 'auto_resolved'
                alert.resolved_at = timezone.now()
                alert.save()
                logger.info(f"Auto-resolved alert: {alert.alert_id}")
        
        except Exception as e:
            logger.error(f"Error auto-resolving alert {alert.alert_id}: {e}")
            continue
    
    return f"Checked {alerts_to_check.count()} alerts for auto-resolution"

def trigger_alert_notification(alert, user):
    """
    Send notification for alert using existing notification system.
    """
    from notification.models import NotificationRule, Notification
    
    try:
        # Create in-app notification
        Notification.objects.create(
            user=user,
            title=alert.title,
            message=alert.description,
            notification_type=alert.severity,
            related_id=alert.alert_id,
            action_url=f"/dashboard/alerts/{alert.alert_id}/",
        )
        
        alert.is_notified = True
        alert.save()
        
        logger.info(f"Notification sent for alert {alert.alert_id}")
    
    except Exception as e:
        logger.error(f"Error sending alert notification: {e}")
```

---

### 2.4 Risk Categories Overview

#### **Implementation Strategy**

**Step 1: Create Risk Category Model** (Add to `producer/models.py`)

```python
class RiskCategory(models.Model):
    """
    High-level risk assessment across different categories.
    Updated daily at 6 AM.
    """
    class RiskLevel(models.TextChoices):
        LOW = 'low', 'Low Risk'
        MEDIUM = 'medium', 'Medium Risk'
        HIGH = 'high', 'High Risk'
    
    # Supplier Risk
    supplier_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default='low')
    supplier_high_risk_count = models.IntegerField(default=0)  # Score < 70
    supplier_spend_at_risk = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # $ amount
    single_source_dependencies = models.IntegerField(default=0)  # Products from single supplier
    
    # Logistics Risk
    logistics_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default='low')
    active_shipment_delays = models.IntegerField(default=0)  # Count of delayed deliveries
    avg_delay_days = models.FloatField(default=0)
    routes_with_issues = models.IntegerField(default=0)
    
    # Demand Risk
    demand_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default='low')
    forecast_accuracy = models.FloatField(default=0)  # % accuracy
    volatile_products_count = models.IntegerField(default=0)  # High variability
    stockout_incidents = models.IntegerField(default=0)  # Last 30 days
    
    # Inventory Risk
    inventory_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default='low')
    items_below_safety_stock = models.IntegerField(default=0)
    overstock_items_count = models.IntegerField(default=0)  # > 180 days supply
    total_inventory_value_at_risk = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Overall Risk Score (0-100)
    overall_risk_score = models.FloatField(default=0)
    overall_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default='low')
    
    # Metadata
    supplier = models.ForeignKey(
        Producer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='risk_categories',
        help_text="NULL = global/aggregate risks"
    )
    snapshot_date = models.DateField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Risk Category"
        verbose_name_plural = "Risk Categories"
        indexes = [
            models.Index(fields=['supplier', 'snapshot_date']),
            models.Index(fields=['overall_risk_level']),
        ]
    
    def __str__(self):
        return f"Risk Categories - {self.snapshot_date}"

class RiskDrillDown(models.Model):
    """
    Detailed list items for risk categories.
    e.g., list of suppliers at risk, products with low stock, etc.
    """
    class ItemType(models.TextChoices):
        SUPPLIER = 'supplier', 'Supplier'
        PRODUCT = 'product', 'Product'
        ROUTE = 'route', 'Route'
        ORDER = 'order', 'Order'
        DELIVERY = 'delivery', 'Delivery'
    
    risk_category = models.ForeignKey(RiskCategory, on_delete=models.CASCADE, related_name='drill_downs')
    risk_type = models.CharField(
        max_length=50,
        choices=[
            ('supplier_health', 'Supplier Health'),
            ('lead_time', 'Lead Time'),
            ('inventory', 'Inventory'),
            ('demand_forecast', 'Demand Forecast'),
            ('shipment_delay', 'Shipment Delay'),
            ('quality', 'Quality Issue'),
        ]
    )
    
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    item_id = models.PositiveIntegerField()  # ID of supplier, product, etc.
    item_name = models.CharField(max_length=255)
    
    # Context
    metric_value = models.FloatField()
    threshold = models.FloatField()
    status = models.CharField(
        max_length=20,
        choices=[('at_risk', 'At Risk'), ('critical', 'Critical'), ('warning', 'Warning')]
    )
    
    # Additional details
    details = models.JSONField(default=dict)  # Flexible field for extra context
    
    class Meta:
        verbose_name = "Risk Drill Down"
        verbose_name_plural = "Risk Drill Downs"
        indexes = [
            models.Index(fields=['risk_category', 'risk_type']),
        ]
```

**Step 2: Risk Assessment Task** (Add to `producer/tasks.py`)

```python
@shared_task(bind=True)
def calculate_risk_categories():
    """
    Daily task (6 AM) to calculate overall risk categories.
    Aggregates data from all other modules.
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models import Sum, Count, Avg, Q, F
    import statistics
    
    logger.info("Calculating risk categories...")
    
    today = timezone.now().date()
    period_30 = today - timedelta(days=30)
    period_90 = today - timedelta(days=90)
    
    # Global risk assessment (supplier=NULL)
    try:
        # 1. SUPPLIER RISK
        suppliers = Producer.objects.all()
        
        high_risk_suppliers = SupplierScorecard.objects.filter(
            health_score__lt=70
        ).count()
        
        # Spend at risk = sum of orders with high-risk suppliers in last 90 days
        spend_at_risk = Order.objects.filter(
            order_date__gte=period_90,
            user__scorecard__health_score__lt=70
        ).aggregate(total=Sum('total_price'))['total'] or 0
        
        # Single-source dependencies
        single_source_deps = Product.objects.filter(
            user__isnull=False
        ).values('id').annotate(
            supplier_count=Count('user', distinct=True)
        ).filter(supplier_count=1).count()
        
        supplier_risk_level = 'high' if high_risk_suppliers > (suppliers.count() * 0.1) else 'medium' if high_risk_suppliers > 0 else 'low'
        
        # 2. LOGISTICS RISK
        delayed_deliveries = Delivery.objects.filter(
            created_at__gte=period_30,
            status__in=['in_transit', 'available'],
            requested_delivery_date__lt=timezone.now()
        )
        
        active_delays = delayed_deliveries.count()
        avg_delay = (timezone.now() - delayed_deliveries.aggregate(Avg('requested_delivery_date'))['requested_delivery_date__avg'].date()) if active_delays > 0 else 0
        
        # Routes with issues: multiple delays on same route
        routes_with_issues = delayed_deliveries.values('pickup_address', 'delivery_address').annotate(
            delay_count=Count('id')
        ).filter(delay_count__gt=1).count()
        
        logistics_risk_level = 'high' if active_delays > 10 else 'medium' if active_delays > 0 else 'low'
        
        # 3. DEMAND RISK
        # Forecast accuracy (simplified: compare planned vs actual sales)
        products = Product.objects.all()
        
        forecast_errors = []
        volatile_products = []
        
        for product in products:
            sales_90 = Sale.objects.filter(
                order__product=product,
                sale_date__gte=period_90
            ).values_list('quantity', flat=True)
            
            if sales_90:
                actual_avg = statistics.mean(sales_90)
                # Assume planned = product.avg_daily_demand (if available)
                if hasattr(product, 'avg_daily_demand') and product.avg_daily_demand > 0:
                    error = abs(actual_avg - product.avg_daily_demand) / product.avg_daily_demand * 100
                    forecast_errors.append(error)
                
                # Volatility: coefficient of variation
                std_dev = statistics.stdev(sales_90) if len(sales_90) > 1 else 0
                cv = std_dev / actual_avg if actual_avg > 0 else 0
                if cv > 0.5:  # High variance
                    volatile_products.append(product)
        
        forecast_accuracy = 100 - (statistics.mean(forecast_errors) if forecast_errors else 0)
        
        # Stock-outs in last 30 days
        stockouts_30 = StockHistory.objects.filter(
            date__gte=period_30,
            quantity_in=0,
            quantity_out__gt=0,
            stock_after=0
        ).count()
        
        demand_risk_level = 'high' if forecast_accuracy < 80 else 'medium' if forecast_accuracy < 90 else 'low'
        
        # 4. INVENTORY RISK
        low_stock = Product.objects.filter(
            stock__lt=F('reorder_point')
        ).count()
        
        overstock = Product.objects.filter(
            stock__gt=F('lead_time_days') * F('avg_daily_demand') * 180
        ).count()
        
        # Value at risk = overstock value
        overstock_value = Product.objects.filter(
            stock__gt=F('lead_time_days') * F('avg_daily_demand') * 180
        ).aggregate(
            total=Sum(F('stock') * F('cost_price'))
        )['total'] or 0
        
        inventory_risk_level = 'high' if low_stock > (products.count() * 0.1) else 'medium' if low_stock > 0 else 'low'
        
        # 5. OVERALL RISK SCORE (weighted average)
        supplier_risk_score = 1 if supplier_risk_level == 'high' else 0.5 if supplier_risk_level == 'medium' else 0
        logistics_risk_score = 1 if logistics_risk_level == 'high' else 0.5 if logistics_risk_level == 'medium' else 0
        demand_risk_score = 1 if demand_risk_level == 'high' else 0.5 if demand_risk_level == 'medium' else 0
        inventory_risk_score = 1 if inventory_risk_level == 'high' else 0.5 if inventory_risk_level == 'medium' else 0
        
        overall_risk_score = (
            supplier_risk_score * 0.25 +
            logistics_risk_score * 0.25 +
            demand_risk_score * 0.25 +
            inventory_risk_score * 0.25
        ) * 100
        
        overall_risk_level = 'high' if overall_risk_score > 66 else 'medium' if overall_risk_score > 33 else 'low'
        
        # 6. Create/update risk category
        risk_category, created = RiskCategory.objects.update_or_create(
            supplier__isnull=True,
            snapshot_date=today,
            defaults={
                'supplier_risk_level': supplier_risk_level,
                'supplier_high_risk_count': high_risk_suppliers,
                'supplier_spend_at_risk': spend_at_risk,
                'single_source_dependencies': single_source_deps,
                'logistics_risk_level': logistics_risk_level,
                'active_shipment_delays': active_delays,
                'avg_delay_days': avg_delay,
                'routes_with_issues': routes_with_issues,
                'demand_risk_level': demand_risk_level,
                'forecast_accuracy': forecast_accuracy,
                'volatile_products_count': len(volatile_products),
                'stockout_incidents': stockouts_30,
                'inventory_risk_level': inventory_risk_level,
                'items_below_safety_stock': low_stock,
                'overstock_items_count': overstock,
                'total_inventory_value_at_risk': overstock_value,
                'overall_risk_score': round(overall_risk_score, 2),
                'overall_risk_level': overall_risk_level,
            }
        )
        
        logger.info(f"Risk assessment created: {overall_risk_level} ({overall_risk_score:.1f})")
        
        # 7. Create drill-down records
        # Supplier drill-downs
        high_risk = SupplierScorecard.objects.filter(health_score__lt=70)
        for scorecard in high_risk:
            RiskDrillDown.objects.update_or_create(
                risk_category=risk_category,
                risk_type='supplier_health',
                item_type='supplier',
                item_id=scorecard.supplier.id,
                defaults={
                    'item_name': scorecard.supplier.name,
                    'metric_value': scorecard.health_score,
                    'threshold': 70,
                    'status': 'critical' if scorecard.health_score < 60 else 'warning',
                    'details': {
                        'on_time_delivery': scorecard.on_time_delivery_pct,
                        'quality': scorecard.quality_performance_pct,
                        'lead_time': scorecard.lead_time_consistency_pct,
                    }
                }
            )
        
        # Delayed delivery drill-downs
        for delivery in delayed_deliveries[:20]:  # Limit to top 20
            RiskDrillDown.objects.update_or_create(
                risk_category=risk_category,
                risk_type='shipment_delay',
                item_type='delivery',
                item_id=delivery.id,
                defaults={
                    'item_name': f"Delivery {delivery.delivery_id}",
                    'metric_value': (timezone.now() - delivery.requested_delivery_date).days,
                    'threshold': 0,
                    'status': 'critical',
                    'details': {
                        'from': delivery.pickup_address,
                        'to': delivery.delivery_address,
                    }
                }
            )
        
        # Low stock drill-downs
        low_stock_items = Product.objects.filter(
            stock__lt=F('reorder_point')
        )[:20]
        
        for product in low_stock_items:
            RiskDrillDown.objects.update_or_create(
                risk_category=risk_category,
                risk_type='inventory',
                item_type='product',
                item_id=product.id,
                defaults={
                    'item_name': product.name,
                    'metric_value': product.stock,
                    'threshold': product.reorder_point,
                    'status': 'critical',
                    'details': {
                        'current_stock': product.stock,
                        'reorder_point': product.reorder_point,
                        'days_until_stockout': (product.stock / product.avg_daily_demand) if product.avg_daily_demand > 0 else 0,
                    }
                }
            )
        
        return f"Risk categories calculated successfully"
        
    except Exception as e:
        logger.error(f"Error calculating risk categories: {e}")
        self.retry(exc=e, countdown=300)
```

---

## Part 3: Integration Points with Your System

### 3.1 Celery Beat Schedule Configuration

Add these to `main/settings.py` `CELERY_BEAT_SCHEDULE`:

```python
# Risk Management Tasks
"calculate-supplier-health-scores": {
    "task": "producer.tasks.calculate_supplier_health_scores",
    "schedule": crontab(minute=0, hour=0),  # Daily at midnight
},
"calculate-supply-chain-kpis": {
    "task": "producer.tasks.calculate_supply_chain_kpis",
    "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
},
"check-supplier-health-alerts": {
    "task": "producer.tasks.check_supplier_health_alerts",
    "schedule": crontab(minute=0, hour="*/2"),  # Every 2 hours
},
"check-otif-alerts": {
    "task": "producer.tasks.check_otif_alerts",
    "schedule": crontab(minute=0, hour="*/2"),  # Every 2 hours
},
"check-stock-alerts": {
    "task": "producer.tasks.check_stock_alerts",
    "schedule": crontab(minute="*/15"),  # Every 15 minutes
},
"auto-resolve-alerts": {
    "task": "producer.tasks.auto_resolve_alerts",
    "schedule": crontab(minute=0, hour=2),  # Daily at 2 AM
},
"calculate-risk-categories": {
    "task": "producer.tasks.calculate_risk_categories",
    "schedule": crontab(minute=0, hour=6),  # Daily at 6 AM
},
```

---

### 3.2 API Endpoints (DRF ViewSets)

Add to `producer/views.py`:

```python
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as http_status

class SupplierHealthScorecardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Supplier health scorecard API.
    GET /api/v1/suppliers/{id}/scorecard/
    GET /api/v1/suppliers/{id}/score-history/
    """
    queryset = SupplierScorecard.objects.all()
    serializer_class = SupplierScorecardSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current scorecard for authenticated user's supplier."""
        user = request.user
        if hasattr(user, 'producer'):
            scorecard = SupplierScorecard.objects.filter(supplier=user.producer).first()
            if scorecard:
                serializer = self.get_serializer(scorecard)
                return Response(serializer.data)
        return Response({'detail': 'No scorecard found'}, status=http_status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get 90-day score history."""
        user = request.user
        if hasattr(user, 'producer'):
            history = SupplierScoreHistory.objects.filter(
                supplier=user.producer
            ).order_by('-recorded_at')[:90]
            serializer = SupplierScoreHistorySerializer(history, many=True)
            return Response(serializer.data)
        return Response({'detail': 'No history found'}, status=http_status.HTTP_404_NOT_FOUND)

class SupplyChainKPIViewSet(viewsets.ReadOnlyModelViewSet):
    """
    KPI Dashboard API.
    GET /api/v1/kpis/current/
    GET /api/v1/kpis/trends/
    """
    queryset = SupplyChainKPI.objects.all()
    serializer_class = SupplyChainKPISerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get latest KPI snapshot."""
        user = request.user
        if hasattr(user, 'producer'):
            kpi = SupplyChainKPI.objects.filter(
                supplier=user.producer
            ).order_by('-snapshot_date').first()
            if kpi:
                serializer = self.get_serializer(kpi)
                return Response(serializer.data)
        return Response({'detail': 'No KPI found'}, status=http_status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def trends(self, request):
        """Get 30-day KPI trends."""
        from datetime import timedelta
        from django.utils import timezone
        
        user = request.user
        period = timezone.now().date() - timedelta(days=30)
        
        if hasattr(user, 'producer'):
            kpis = SupplyChainKPI.objects.filter(
                supplier=user.producer,
                snapshot_date__gte=period
            ).order_by('snapshot_date')
            serializer = self.get_serializer(kpis, many=True)
            return Response(serializer.data)
        return Response({'detail': 'No data found'}, status=http_status.HTTP_404_NOT_FOUND)

class SupplyChainAlertViewSet(viewsets.ModelViewSet):
    """
    Alert management API.
    GET /api/v1/alerts/
    POST /api/v1/alerts/{id}/acknowledge/
    POST /api/v1/alerts/{id}/resolve/
    """
    queryset = SupplyChainAlert.objects.all()
    serializer_class = SupplyChainAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['alert_type', 'severity', 'status']
    ordering = ['-triggered_at']
    
    def get_queryset(self):
        """Filter to user's supplier alerts."""
        user = self.request.user
        if hasattr(user, 'producer'):
            return SupplyChainAlert.objects.filter(
                supplier=user.producer
            )
        return SupplyChainAlert.objects.none()
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert."""
        alert = self.get_object()
        alert.acknowledge(request.user)
        serializer = self.get_serializer(alert)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Manually resolve an alert."""
        alert = self.get_object()
        alert.resolve(request.user)
        serializer = self.get_serializer(alert)
        return Response(serializer.data)

class RiskCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Risk category dashboard API.
    GET /api/v1/risk-categories/current/
    GET /api/v1/risk-categories/{id}/drill-downs/
    """
    queryset = RiskCategory.objects.all()
    serializer_class = RiskCategorySerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current risk assessment."""
        from django.utils import timezone
        
        today = timezone.now().date()
        risk = RiskCategory.objects.filter(
            supplier__isnull=True,
            snapshot_date=today
        ).first()
        
        if risk:
            serializer = self.get_serializer(risk)
            return Response(serializer.data)
        return Response({'detail': 'No risk assessment found'}, status=http_status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def drill_downs(self, request, pk=None):
        """Get detailed list for a risk category."""
        risk = self.get_object()
        drill_downs = RiskDrillDown.objects.filter(risk_category=risk)
        serializer = RiskDrillDownSerializer(drill_downs, many=True)
        return Response(serializer.data)
```

---

### 3.3 Notification Integration

Update your notification templates and rules:

```python
# Create notification templates
NotificationTemplate.objects.create(
    name='supplier_health_critical',
    template_type='email',
    title_template='⚠️ Supplier Health Alert: {supplier_name}',
    body_template='''
        Supplier {supplier_name} has entered CRITICAL status.
        Health Score: {health_score}/100
        
        On-Time Delivery: {on_time_delivery}%
        Quality: {quality_performance}%
        
        Please review and take action: {action_url}
    ''',
    variables=['supplier_name', 'health_score', 'on_time_delivery', 'quality_performance', 'action_url']
)

# Create notification rule
NotificationRule.objects.create(
    name='Supplier Health Critical Alert',
    trigger_event='custom',
    template=NotificationTemplate.objects.get(name='supplier_health_critical'),
    conditions=[
        {'field': 'alert_type', 'operator': 'eq', 'value': 'supplier_health'},
        {'field': 'severity', 'operator': 'eq', 'value': 'critical'},
    ],
    target_users={'role': 'supplier', 'include_admin': True},
    is_active=True,
    priority=1
)
```

---

## Part 4: Frontend Integration Points

### 4.1 API Responses Structure

**Dashboard Summary Endpoint** (`/api/v1/risk-dashboard/summary/`):

```json
{
  "timestamp": "2024-01-20T10:30:00Z",
  "supplier_scorecard": {
    "health_score": 85.5,
    "status": "healthy",
    "on_time_delivery_pct": 92,
    "quality_performance_pct": 98,
    "lead_time_consistency_pct": 85,
    "trend": "up"  // or "down", "stable"
  },
  "kpis": {
    "otif_rate": 92.5,
    "otif_trend": 2.1,
    "lead_time_variability": 3.2,
    "lead_time_trend": -0.5,
    "inventory_turnover": 6.8,
    "inventory_trend": 0.3
  },
  "active_alerts": {
    "critical": 1,
    "warning": 3,
    "info": 5
  },
  "risk_overview": {
    "supplier_risk": {
      "level": "medium",
      "count": 3,
      "spend_at_risk": 250000
    },
    "logistics_risk": {
      "level": "low",
      "delayed_shipments": 2,
      "avg_delay_days": 1.5
    },
    "demand_risk": {
      "level": "low",
      "forecast_accuracy": 87,
      "volatile_items": 5
    },
    "inventory_risk": {
      "level": "medium",
      "low_stock_items": 12,
      "overstock_items": 3,
      "value_at_risk": 45000
    }
  }
}
```

---

## Part 5: Implementation Roadmap

### Phase 1: Foundations (Week 1-2)
1. ✅ Create models (Scorecard, KPI, Alert, Risk)
2. ✅ Write calculation tasks
3. ✅ Add Celery Beat schedule
4. ✅ Create serializers
5. ✅ Add basic API endpoints

### Phase 2: Automation (Week 3)
1. ✅ Implement alert triggers
2. ✅ Set up notification integration
3. ✅ Auto-resolve logic
4. ✅ Testing of all tasks

### Phase 3: Dashboard (Week 4)
1. ✅ Frontend components
2. ✅ Real-time updates (WebSocket optional)
3. ✅ Drill-down views
4. ✅ Alert management UI

### Phase 4: Optimization (Week 5+)
1. ✅ Performance tuning
2. ✅ Caching strategy (Redis)
3. ✅ Analytics & reporting
4. ✅ Custom threshold configuration UI

---

## Part 6: Database Migrations

Create a migration file:

```bash
python manage.py makemigrations producer
python manage.py migrate
```

---

## Part 7: Testing Strategy

```python
# tests/test_risk_management.py

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from producer.tasks import (
    calculate_supplier_health_scores,
    calculate_supply_chain_kpis,
    check_supplier_health_alerts,
)

class SupplierHealthScorecardTest(TestCase):
    def setUp(self):
        self.supplier = Producer.objects.create(...)
        # Create test orders and sales
    
    def test_health_score_calculation(self):
        """Test that health score is calculated correctly."""
        calculate_supplier_health_scores()
        scorecard = SupplierScorecard.objects.get(supplier=self.supplier)
        self.assertEqual(scorecard.health_score, expected_value)
    
    def test_critical_alert_triggered(self):
        """Test that critical alert is triggered when score < 60."""
        # Set up low-performing supplier
        self.supplier.scorecard.health_score = 45
        self.supplier.scorecard.save()
        
        check_supplier_health_alerts()
        
        alert = SupplyChainAlert.objects.filter(
            supplier=self.supplier,
            severity='critical'
        ).first()
        self.assertIsNotNone(alert)
```

---

## Summary

This implementation plan provides:

✅ **Model Structure**: 8 new models tightly integrated with existing data
✅ **Celery Tasks**: 7 scheduled tasks for continuous risk monitoring
✅ **API Endpoints**: 4 ViewSets with drill-down and trend capabilities
✅ **Alert System**: Leverages existing notification engine
✅ **Scalability**: Designed for multi-tenant (per-supplier) reporting
✅ **Flexibility**: Configurable thresholds and alert sensitivity
✅ **Historical Tracking**: 90-day data retention for trend analysis

All components follow your existing patterns:
- Django ORM models with proper relationships
- DRF serializers and viewsets
- Celery tasks with error handling
- Redis-based caching potential
- Existing notification infrastructure reuse

You're ready to implement! 🚀
