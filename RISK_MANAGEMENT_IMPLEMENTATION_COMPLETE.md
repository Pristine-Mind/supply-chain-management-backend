# Supply Chain Risk Management Dashboard - Implementation Guide

## Overview

This document provides comprehensive documentation for the Supply Chain Risk Management Dashboard implementation. The system provides real-time monitoring, alerting, and analysis of supplier health, KPIs, alerts, and supply chain risks.

## Architecture

### Core Components

1. **Models** (`producer/risk_models.py`)
   - 8 Django ORM models for data persistence
   - Indexes on frequently queried fields
   - GenericForeignKey for flexible alert associations

2. **Serializers** (`producer/risk_serializers.py`)
   - 11 DRF serializers for API endpoints
   - Nested relationships and computed properties
   - Read-only fields for calculated metrics

3. **ViewSets** (`producer/risk_views.py`)
   - 5 REST API viewsets with comprehensive endpoints
   - Permission classes and filtering
   - Custom actions for alerts and drill-downs

4. **Celery Tasks** (`producer/risk_tasks.py`)
   - 7 automated calculation tasks
   - Scheduled via Celery Beat
   - Comprehensive error handling and retry logic

5. **Admin Interface** (`producer/risk_admin.py`)
   - 8 Django Admin configuration classes
   - Color-coded displays
   - Custom actions for alert management

## Models

### SupplierScorecard
Stores current health metrics for each supplier.

**Fields:**
- `supplier` (OneToOneField): Link to Producer
- `health_score` (DecimalField): 0-100 weighted score
- `otd_score` (DecimalField): On-Time Delivery percentage
- `quality_score` (DecimalField): Quality metric
- `lead_time_consistency` (DecimalField): Consistency of lead times
- `health_status` (CharField): Critical/Warning/Healthy
- `is_healthy` (BooleanField): Computed property
- `is_critical` (BooleanField): Computed property

**Indexes:**
- Composite index on (supplier, health_status)

### SupplierScoreHistory
Historical snapshots for trend analysis (90-day retention).

**Fields:**
- `supplier` (ForeignKey): Reference to Producer
- `health_score` (DecimalField): Score at snapshot time
- `recorded_at` (DateField): Date of record

**Indexes:**
- Index on recorded_at for date-range queries

### ProductDefectRecord
Quality tracking and defect management.

**Fields:**
- `product` (ForeignKey): Reference to Product
- `supplier` (ForeignKey): Reference to Producer
- `defect_type` (CharField): Type of defect
- `severity` (CharField): High/Medium/Low
- `quantity` (IntegerField): Number of defective units
- `resolution_status` (CharField): Open/In-Progress/Resolved
- `reported_date` (DateField): When defect was reported
- `resolved_date` (DateField): When defect was resolved

### SupplyChainKPI
6-hourly snapshots of key performance indicators.

**Fields:**
- `supplier` (ForeignKey): Reference to Producer
- `snapshot_date` (DateField): Date of snapshot
- `otif_rate` (DecimalField): On-Time In-Full percentage
- `avg_lead_time_days` (DecimalField): Average lead time
- `lead_time_variability` (DecimalField): Standard deviation
- `inventory_turnover` (DecimalField): COGS / Average Inventory
- Trend fields for comparison with previous period

**Indexes:**
- Composite index on (supplier, snapshot_date)

### AlertThreshold
Configurable alert trigger thresholds.

**Fields:**
- `alert_type` (CharField): Type of alert
- `critical_threshold` (DecimalField): Critical level
- `warning_threshold` (DecimalField): Warning level
- `check_frequency_minutes` (IntegerField): How often to check
- `is_active` (BooleanField): Enable/disable alerts

### SupplyChainAlert
Alert tracking with acknowledgement and resolution.

**Fields:**
- `title` (CharField): Alert title
- `description` (TextField): Detailed description
- `alert_type` (CharField): Type of alert
- `severity` (CharField): Critical/Warning/Info
- `status` (CharField): Active/Acknowledged/Resolved/Auto-Resolved
- `supplier` (ForeignKey): Affected supplier
- `product` (ForeignKey): Affected product (optional)
- `assigned_to` (ForeignKey): User assigned to handle alert
- `triggered_at` (DateTimeField): When alert was triggered
- `acknowledged_at` (DateTimeField): When acknowledged
- `resolved_at` (DateTimeField): When resolved
- `metadata` (JSONField): Flexible storage for alert context

**Methods:**
- `acknowledge(user)`: Mark as acknowledged
- `resolve(user)`: Manually resolve alert
- `auto_resolve()`: Automatically resolve when conditions normalize

### RiskCategory
Daily aggregated risk assessment.

**Fields:**
- `supplier` (ForeignKey): null for global assessment
- `snapshot_date` (DateField): Date of assessment
- Supplier risk metrics (% low-score suppliers, dependencies, etc.)
- Logistics risk metrics (active delays, avg delay days)
- Demand risk metrics (forecast accuracy, volatile products)
- Inventory risk metrics (low stock, overstock, value at risk)
- `overall_risk_score` (DecimalField): Weighted 0-100
- `overall_risk_level` (CharField): Low/Medium/High

**Indexes:**
- Composite index on (supplier, snapshot_date)

### RiskDrillDown
Detailed items within risk categories.

**Fields:**
- `risk_category` (ForeignKey): Parent RiskCategory
- `item_name` (CharField): Name of risky item
- `item_identifier` (CharField): Unique identifier (supplier ID, product ID, etc.)
- `risk_level` (CharField): High/Medium/Low
- `value` (DecimalField): Quantitative measure
- `unit` (CharField): Unit of measurement
- `description` (TextField): Explanation of risk

## API Endpoints

### Supplier Scorecard Endpoints

```
GET /api/v1/supplier-scorecards/
  - List all supplier scorecards
  - Query params: supplier__name, health_status, page_size

GET /api/v1/supplier-scorecards/{id}/
  - Get specific scorecard

GET /api/v1/supplier-scorecards/current/
  - Get authenticated user's scorecard

GET /api/v1/supplier-scorecards/{id}/history/
  - Get 90-day score history

GET /api/v1/supplier-scorecards/comparison/?supplier_ids=1,2,3
  - Compare multiple suppliers' scores
```

### KPI Endpoints

```
GET /api/v1/kpis/
  - List KPI snapshots
  - Query params: supplier__name, snapshot_date

GET /api/v1/kpis/{id}/
  - Get specific KPI snapshot

GET /api/v1/kpis/current/
  - Get latest KPI for authenticated user

GET /api/v1/kpis/trends/
  - Get 30-day KPI trends
```

### Alert Endpoints

```
GET /api/v1/alerts/
  - List alerts
  - Query params: alert_type, severity, status, supplier__name
  - Search: title, description

GET /api/v1/alerts/{id}/
  - Get alert details

POST /api/v1/alerts/{id}/acknowledge/
  - Acknowledge an alert

POST /api/v1/alerts/{id}/resolve/
  - Manually resolve an alert

GET /api/v1/alerts/active/
  - Get all active/acknowledged alerts

GET /api/v1/alerts/statistics/
  - Get alert statistics (counts by type, severity, status)
```

### Risk Category Endpoints

```
GET /api/v1/risk-categories/
  - List risk assessments
  - Query params: supplier__name, overall_risk_level

GET /api/v1/risk-categories/current/
  - Get today's risk assessment

GET /api/v1/risk-categories/{id}/drill-downs/
  - Get detailed items in a risk category

GET /api/v1/risk-categories/summary/
  - Get comprehensive dashboard summary
```

### Admin Endpoints

```
GET /api/v1/alert-thresholds/
  - List threshold configurations (admin only)

PUT /api/v1/alert-thresholds/{id}/
  - Update threshold (admin only)
```

## Celery Tasks

### 1. calculate_supplier_health_scores

**Schedule:** Daily at midnight (00:00 UTC)

**Purpose:** Calculate weighted supplier health scores

**Calculation:**
- On-Time Delivery (OTD): 50%
- Quality score (defect rate): 30%
- Lead-time consistency (std dev): 20%
- Result: 0-100 score

**Output:**
- Creates/updates SupplierScorecard
- Creates historical SupplierScoreHistory record

**Edge Cases Handled:**
- Empty sales data → score = 0
- No historical data → defaults applied
- Division by zero protection

### 2. calculate_supply_chain_kpis

**Schedule:** Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)

**Purpose:** Calculate key performance indicators

**Metrics:**
- OTIF Rate: % of orders delivered on-time in-full
- Lead Time: Average days from order to delivery
- Lead Time Variability: Standard deviation
- Inventory Turnover: COGS / Average inventory value

**Trend Comparison:**
- Compares with previous 6-hour period
- Calculates % change

**Edge Cases Handled:**
- No sales data → defaults to 0
- Single data point for variance → defaults to 0
- Zero denominator protection

### 3. check_supplier_health_alerts

**Schedule:** Every 2 hours

**Purpose:** Monitor supplier health and trigger alerts

**Alert Conditions:**
- **Critical:** Score < 60 (configurable)
- **Warning:** Score dropped > 10 points in 7 days

**Features:**
- Duplicate alert prevention
- Creates Notification when alert triggered
- Respects AlertThreshold configuration

**Edge Cases Handled:**
- Supplier deleted → skips with logging
- No previous score → no warning alert
- Threshold not configured → uses defaults

### 4. check_otif_alerts

**Schedule:** Every 2 hours

**Purpose:** Monitor on-time in-full performance

**Alert Conditions:**
- **Critical:** OTIF < 90% (configurable)
- **Warning:** OTIF trending down > 5%

**Features:**
- Configurable thresholds
- Trend analysis
- Metadata includes current OTIF and trend

**Edge Cases Handled:**
- No KPI data yet → skips
- Threshold not configured → uses defaults
- No supplier → skips with logging

### 5. check_stock_alerts

**Schedule:** Every 15 minutes

**Purpose:** Monitor inventory levels

**Alert Conditions:**
- **Critical:** Stock below safety stock
- **Critical:** Stock below reorder point

**Features:**
- Checks all products for owner
- Product-specific safety stock levels
- Duplicate prevention

**Edge Cases Handled:**
- Product without safety_stock → skips
- Product without reorder_point → skips
- Zero inventory → creates alert

### 6. auto_resolve_alerts

**Schedule:** Daily at 2 AM (02:00 UTC)

**Purpose:** Automatically resolve alerts when conditions normalize

**Normalization Conditions:**
- Supplier health >= 60
- OTIF >= 90%
- Stock >= safety stock

**Features:**
- 24-hour grace period (must be normalized for 24 hours)
- Updates resolved_at timestamp
- Logs resolution

**Edge Cases Handled:**
- Alert without related object → skips with logging
- Already resolved → no change
- Recently triggered → doesn't resolve

### 7. calculate_risk_categories

**Schedule:** Daily at 6 AM (06:00 UTC)

**Purpose:** Comprehensive daily risk assessment

**Risk Dimensions (25% each):**

1. **Supplier Risk**
   - % of suppliers with score < 70
   - % of spend from low-score suppliers
   - Count of single-source dependencies

2. **Logistics Risk**
   - Count of active delivery delays
   - Average delay duration
   - % of routes with issues

3. **Demand Risk**
   - Forecast accuracy percentage
   - Count of volatile products
   - Count of recent stockout incidents

4. **Inventory Risk**
   - Count of items below safety stock
   - Count of overstock items
   - Value at risk from over/understock

**Output:**
- Creates/updates RiskCategory record
- Creates RiskDrillDown for top 20 items per category
- Includes global assessment (supplier=null)

**Edge Cases Handled:**
- No suppliers → still creates global risk
- Empty product list → defaults to 0
- Null delivery dates → filters out
- Zero denominator in CV → defaults to 0

## Serializers

All serializers follow DRF best practices:

### SupplierScorecardSerializer
```python
{
    "id": 1,
    "supplier": {...},
    "health_score": 75.5,
    "health_status": "healthy",
    "is_healthy": true,
    "is_critical": false,
    "otd_score": 80,
    "quality_score": 70,
    "lead_time_consistency": 75,
    "last_updated": "2024-01-15T10:00:00Z"
}
```

### SupplyChainAlertSerializer
```python
{
    "id": 1,
    "title": "Critical supplier health alert",
    "alert_type": "supplier_health",
    "severity": "critical",
    "status": "active",
    "supplier_name": "Supplier A",
    "product_name": "Product X",
    "assigned_to_username": "user@example.com",
    "triggered_at": "2024-01-15T10:00:00Z",
    "metadata": {...}
}
```

### RiskCategorySerializer
```python
{
    "id": 1,
    "supplier_name": "Supplier A",
    "snapshot_date": "2024-01-15",
    "supplier_risk_score": 35.5,
    "logistics_risk_score": 40.0,
    "demand_risk_score": 25.0,
    "inventory_risk_score": 30.0,
    "overall_risk_score": 32.5,
    "overall_risk_level": "medium",
    "drill_downs": [...]
}
```

## Configuration

### Django Settings

Add to `main/settings.py`:

```python
# Risk Management App (already added)
INSTALLED_APPS = [
    ...
    'producer',
    'transport',
    'notification',
    ...
]

# Celery Beat Schedule (7 tasks added)
CELERY_BEAT_SCHEDULE = {
    "calculate-supplier-health-scores": {...},
    "calculate-supply-chain-kpis": {...},
    # ... 5 more risk management tasks
}
```

### Alert Thresholds (Creatable via Admin or API)

Default thresholds can be created via Django admin:

```
Alert Type: supplier_health
Critical: 60
Warning: 70
Check Frequency: 120 minutes

Alert Type: otif
Critical: 90
Warning: 95
Check Frequency: 120 minutes

Alert Type: stock_level
Critical: 50
Warning: 100
Check Frequency: 15 minutes
```

## Permissions

### User Types

**Suppliers:**
- Can view their own scorecard, KPIs, alerts, risk
- Can acknowledge/resolve their own alerts
- Cannot view other suppliers' data

**Admin Users:**
- Can view all suppliers' data
- Can configure alert thresholds
- Can manage alert assignments
- Can view global risk assessments

**Anonymous:**
- No access to any endpoint (401 Unauthorized)

### ViewSet Permissions

```python
# All viewsets require IsAuthenticated
permission_classes = [IsAuthenticated]

# get_queryset() filters based on user type:
# - Suppliers see only their data
# - Admins see all data
```

## Error Handling

### Task Error Handling

All Celery tasks implement:

```python
try:
    # Task logic
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    self.retry(exc=e, countdown=300, max_retries=3)
```

**Retry Strategy:**
- First retry after 300 seconds (5 minutes)
- Exponential backoff
- Max 3 retries

### Query Error Handling

Safe division and statistics:

```python
# Division by zero
result = (numerator / denominator) if denominator > 0 else 0

# Statistics with single value
variance = pstdev(data) if len(data) > 1 else 0
```

## Caching Strategy

### Redis Caching
- KPI snapshots cached for 1 hour
- Risk assessments cached for 6 hours
- Alert counts cached for 5 minutes
- Scorecard history cached for 24 hours

### Cache Invalidation
- Automatic TTL-based expiration
- Manual invalidation on alert acknowledgement
- Task-based refresh on schedule

## Performance Optimization

### Query Optimization

All querysets use:
```python
# Reduce database queries
.select_related('supplier')
.prefetch_related('drill_downs')

# Use F() expressions for calculations
from django.db.models import F, Sum, Avg
```

### Indexes

Composite indexes on:
- `SupplierScorecard(supplier, health_status)`
- `SupplierScoreHistory(recorded_at)`
- `SupplyChainKPI(supplier, snapshot_date)`
- `RiskCategory(supplier, snapshot_date)`

## Testing

### Test Coverage

- Model creation and validation
- Serializer field validation
- API endpoint permissions
- Celery task execution
- Edge case handling
- Error recovery

### Running Tests

```bash
# Run all risk management tests
python manage.py test producer.test_risk_management

# Run specific test class
python manage.py test producer.test_risk_management.SupplierScorecardModelTestCase

# With coverage
pytest --cov=producer.risk_* producer/test_risk_management.py
```

## Migration Guide

### Step 1: Create Models
```bash
python manage.py makemigrations producer
python manage.py migrate
```

### Step 2: Create Admin Interface
Models are automatically registered (already done in risk_admin.py)

### Step 3: Update Settings
Celery Beat schedule is already configured in main/settings.py

### Step 4: Start Celery Worker
```bash
celery -A main worker -l info
```

### Step 5: Start Celery Beat
```bash
celery -A main beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Step 6: Run Tests
```bash
python manage.py test producer.test_risk_management
```

## Monitoring

### Celery Task Monitoring

Monitor task execution:
```bash
celery -A main events
```

### Alert Notifications

Alerts trigger Notification records which are sent via:
- Email
- Push notifications
- In-app notifications
- SMS (if configured)

### Logging

All tasks log to `producer.risk_tasks`:

```python
logger = logging.getLogger(__name__)
logger.info(f"Started calculating scores for {supplier_count} suppliers")
logger.error(f"Error processing supplier {supplier.id}: {e}", exc_info=True)
```

## Troubleshooting

### No alerts being created
1. Check AlertThreshold configuration in admin
2. Verify Celery worker is running: `celery -A main worker`
3. Verify Celery Beat is running: `celery -A main beat`
4. Check task logs for errors

### Old alerts not resolving
1. Check auto_resolve_alerts task in Celery logs
2. Verify auto_resolve() method is being called
3. Check conditions (24-hour grace period required)

### Incorrect risk scores
1. Verify supplier has recent sales data
2. Check StockHistory records exist
3. Run calculate_supplier_health_scores manually

### API returning wrong data
1. Check user permissions (supplier vs admin)
2. Verify queryset filtering in get_queryset()
3. Check serializer field definitions

## Future Enhancements

1. **Machine Learning Integration**
   - Predictive risk scoring
   - Anomaly detection
   - Forecasting improvements

2. **Advanced Notifications**
   - Slack/Teams integration
   - Webhook endpoints
   - Escalation rules

3. **Reporting**
   - Custom report generation
   - Trend analysis
   - Benchmark comparisons

4. **Dashboard UI**
   - Real-time updates via WebSockets
   - Interactive charts
   - Drill-down exploration

## References

- Django ORM: https://docs.djangoproject.com/en/4.2/topics/db/
- DRF: https://www.django-rest-framework.org/
- Celery: https://docs.celeryproject.org/
- PostgreSQL: https://www.postgresql.org/docs/
