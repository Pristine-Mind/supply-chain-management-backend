# Risk Management System - Technical Architecture & Integration Guide

## System Overview Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    RISK MANAGEMENT DASHBOARD                     │
│                        (Frontend Layer)                          │
└────────────────────┬──────────────────────────────────────────┬──┘
                     │                                           │
         ┌───────────▼─────────────┐            ┌───────────────▼────────┐
         │   API Endpoints         │            │  WebSocket Events      │
         │                         │            │  (Real-time updates)   │
         │ - /api/v1/scorecard/   │            │                        │
         │ - /api/v1/kpis/        │            │ - Alert triggered      │
         │ - /api/v1/alerts/      │            │ - Score updated        │
         │ - /api/v1/risks/       │            │ - Status changed       │
         └───────────┬─────────────┘            └───────────────────────┘
                     │
        ┌────────────▼────────────┐
        │   Django REST Framework  │
        │   (DRF Layer)            │
        │                          │
        │ ┌──────────────────────┐ │
        │ │ ViewSets & Serializers│ │
        │ │ - Authentication     │ │
        │ │ - Permissions        │ │
        │ │ - Pagination         │ │
        │ │ - Filtering          │ │
        │ └──────────────────────┘ │
        └────────────┬──────────────┘
                     │
        ┌────────────▼──────────────────────────────────┐
        │         Django Models & QuerySets             │
        │      (Application Business Logic)             │
        │                                               │
        │  ┌──────────────────────────────────────────┐ │
        │  │  New Models:                             │ │
        │  │  • SupplierScorecard                     │ │
        │  │  • SupplierScoreHistory                  │ │
        │  │  • SupplyChainKPI                        │ │
        │  │  • SupplyChainAlert                      │ │
        │  │  • AlertThreshold                        │ │
        │  │  • RiskCategory                          │ │
        │  │  • RiskDrillDown                         │ │
        │  │  • ProductDefectRecord                   │ │
        │  └──────────────────────────────────────────┘ │
        │  ┌──────────────────────────────────────────┐ │
        │  │  Existing Models (Leverage):             │ │
        │  │  • Producer                              │ │
        │  │  • Product                               │ │
        │  │  • Order                                 │ │
        │  │  • Sale                                  │ │
        │  │  • Delivery                              │ │
        │  │  • Payment                               │ │
        │  │  • StockHistory                          │ │
        │  └──────────────────────────────────────────┘ │
        └────────────┬──────────────────────────────────┘
                     │
        ┌────────────▼──────────────────────────────────┐
        │      Celery Task Queue & Beat Scheduler        │
        │                                               │
        │  CELERY_BROKER_URL: Redis                    │
        │  CELERY_RESULT_BACKEND: Redis                │
        │                                               │
        │  Periodic Tasks:                             │
        │  ┌────────────────────────────────────────┐  │
        │  │ Midnight (00:00)                       │  │
        │  │ → calculate_supplier_health_scores()   │  │
        │  └────────────────────────────────────────┘  │
        │  ┌────────────────────────────────────────┐  │
        │  │ Every 6 Hours                          │  │
        │  │ → calculate_supply_chain_kpis()        │  │
        │  │ → periodic_delivery_reminders()        │  │
        │  └────────────────────────────────────────┘  │
        │  ┌────────────────────────────────────────┐  │
        │  │ Every 2 Hours                          │  │
        │  │ → check_supplier_health_alerts()       │  │
        │  │ → check_otif_alerts()                  │  │
        │  │ → check_stock_alerts()                 │  │
        │  └────────────────────────────────────────┘  │
        │  ┌────────────────────────────────────────┐  │
        │  │ Every 15 Minutes                       │  │
        │  │ → check_stock_alerts()                 │  │
        │  └────────────────────────────────────────┘  │
        │  ┌────────────────────────────────────────┐  │
        │  │ Daily at 2 AM                          │  │
        │  │ → auto_resolve_alerts()                │  │
        │  │ → cleanup_old_notifications()          │  │
        │  └────────────────────────────────────────┘  │
        │  ┌────────────────────────────────────────┐  │
        │  │ Daily at 6 AM                          │  │
        │  │ → calculate_risk_categories()          │  │
        │  └────────────────────────────────────────┘  │
        │                                               │
        │  Task Distribution:                          │
        │  ┌─────────────┐  ┌─────────────┐           │
        │  │ Worker 1    │  │ Worker N    │           │
        │  │ (CPU-bound) │  │ (I/O-bound) │           │
        │  └─────────────┘  └─────────────┘           │
        └────────────┬──────────────────────────────────┘
                     │
        ┌────────────▼──────────────────────────────────┐
        │          PostgreSQL Database                  │
        │                                               │
        │  New Tables:                                 │
        │  • producer_supplierscorecardcard             │
        │  • producer_supplierscorecardhistory         │
        │  • producer_supplychainskpi                   │
        │  • producer_supplychanalert                   │
        │  • producer_alertthreshold                    │
        │  • producer_riskcategory                      │
        │  • producer_riskdrilldown                     │
        │  • producer_productdefectrecord               │
        │                                               │
        │  Indexes:                                    │
        │  • (supplier_id, snapshot_date)              │
        │  • (alert_type, severity, status)            │
        │  • (supplier_id, recorded_at)                │
        │                                               │
        │  Data Retention:                             │
        │  • Historical data: 90 days                   │
        │  • Alerts: 180 days                          │
        │  • Snapshots: 365 days                       │
        └────────────┬──────────────────────────────────┘
                     │
        ┌────────────▼──────────────────────────────────┐
        │             Redis Cache Layer                 │
        │                                               │
        │  Cache Keys:                                 │
        │  • supplier:{id}:scorecard (TTL: 3600s)     │
        │  • supplier:{id}:kpi (TTL: 1800s)           │
        │  • supplier:{id}:alerts (TTL: 600s)         │
        │  • risk:categories (TTL: 7200s)             │
        │                                               │
        │  Pub/Sub Channels:                          │
        │  • risk:alerts:new                           │
        │  • risk:scorecard:updated                    │
        │  • risk:kpi:updated                          │
        └────────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### 1. Supplier Health Score Calculation Flow

```
Daily Trigger (Midnight)
       │
       ▼
┌─────────────────────────────────────────┐
│ calculate_supplier_health_scores()      │
│ (producer/tasks.py)                     │
└─────────────┬───────────────────────────┘
              │
              ├─────────────────────────────┐
              │                             │
              ▼                             ▼
    ┌──────────────────┐      ┌──────────────────┐
    │ Fetch Orders     │      │ Fetch Sales      │
    │ (90-day window)  │      │ (90-day window)  │
    │                  │      │                  │
    │ From:            │      │ From:            │
    │ Order.objects    │      │ Sale.objects     │
    │ .filter()        │      │ .filter()        │
    └────────┬─────────┘      └────────┬─────────┘
             │                         │
             ├────────────────────────┬┘
             │                        │
             ▼                        ▼
    ┌─────────────────────────────────────┐
    │ Calculate Metrics                   │
    │ 1. On-Time Delivery % (50%)          │
    │    = orders_on_time / total_orders   │
    │                                      │
    │ 2. Quality Performance % (30%)       │
    │    = 100% - defect_rate              │
    │                                      │
    │ 3. Lead Time Consistency % (20%)     │
    │    = 100 - (variance × 5)            │
    └─────────────┬───────────────────────┘
                  │
                  ▼
    ┌─────────────────────────────────────┐
    │ Calculate Weighted Score             │
    │                                      │
    │ Health Score =                       │
    │   (OTD% × 0.50) +                    │
    │   (QP% × 0.30) +                     │
    │   (LTC% × 0.20)                      │
    │                                      │
    │ Range: 0-100                         │
    │ Healthy: 80-100 (Green)              │
    │ Monitor: 60-79 (Yellow)              │
    │ Critical: 0-59 (Red)                 │
    └─────────────┬───────────────────────┘
                  │
                  ▼
    ┌─────────────────────────────────────┐
    │ Store Results                        │
    │                                      │
    │ SupplierScorecard.objects            │
    │ .update_or_create()                  │
    │                                      │
    │ SupplierScoreHistory.objects         │
    │ .create()  ← Historical record       │
    └─────────────┬───────────────────────┘
                  │
                  ▼
    ┌─────────────────────────────────────┐
    │ Check for Alerts                     │
    │                                      │
    │ IF score < 60:                       │
    │   → trigger_supplier_alert()         │
    │   → send_notification()              │
    │   → cache_update()                   │
    └─────────────────────────────────────┘
```

### 2. Alert Generation & Notification Flow

```
Threshold Check (Every 2 Hours)
       │
       ▼
┌──────────────────────────────────┐
│ check_supplier_health_alerts()   │
│ check_otif_alerts()              │
│ check_stock_alerts()             │
└────────────┬─────────────────────┘
             │
             ▼
    ┌────────────────────────────────┐
    │ Fetch Current Metrics           │
    │                                 │
    │ SupplierScorecard.objects       │
    │ SupplyChainKPI.objects          │
    │ Product.objects (low stock)     │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────┐
    │ Compare vs Thresholds           │
    │                                 │
    │ IF score < 60 AND no alert:     │
    │   → CREATE alert (critical)     │
    │                                 │
    │ ELIF score dropped > 10 pts:    │
    │   → CREATE alert (warning)      │
    │                                 │
    │ ELIF otif < 90%:                │
    │   → CREATE alert (critical)     │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │ SupplyChainAlert.objects.create()  │
    │                                    │
    │ Fields:                            │
    │ • alert_type                       │
    │ • severity (critical/warning/info) │
    │ • title, description               │
    │ • supplier_id, product_id          │
    │ • metric_value, threshold_value    │
    │ • status = 'active'                │
    │ • is_notified = False              │
    │ • notification_channels = [...]    │
    └────────────┬───────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────┐
    │ trigger_alert_notification()    │
    │                                 │
    │ IF 'email' in channels:         │
    │   → send_email()                │
    │                                 │
    │ IF 'push' in channels:          │
    │   → push_notification()         │
    │                                 │
    │ IF 'in_app' in channels:        │
    │   → Notification.objects.create │
    │                                 │
    │ Notification.objects.create()   │
    │ with:                           │
    │ • user                          │
    │ • title, message                │
    │ • action_url → dashboard        │
    │ • notification_type = severity  │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────┐
    │ Update Alert Status             │
    │                                 │
    │ alert.is_notified = True        │
    │ alert.save()                    │
    │                                 │
    │ Cache Update:                   │
    │ redis.lpush('active_alerts',    │
    │   alert_id)                     │
    │ redis.expire(key, 1800)         │
    └────────────────────────────────┘
```

### 3. Alert Auto-Resolution Flow

```
Daily Trigger (2 AM)
       │
       ▼
┌──────────────────────────────────┐
│ auto_resolve_alerts()            │
└────────────┬─────────────────────┘
             │
             ▼
    ┌────────────────────────────────┐
    │ Fetch Active Alerts             │
    │ triggered_at < 24 hours ago      │
    │ status IN ('active',             │
    │           'acknowledged')        │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────┐
    │ For Each Alert:                 │
    │                                 │
    │ IF alert_type == 'supplier':   │
    │   → check SupplierScorecard     │
    │     latest_score >= 60?         │
    │                                 │
    │ IF alert_type == 'otif':       │
    │   → check SupplyChainKPI        │
    │     latest_otif >= 90%?         │
    │                                 │
    │ IF alert_type == 'stock':      │
    │   → check Product.stock         │
    │     >= reorder_point?           │
    └────────────┬────────────────────┘
                 │
                 ├─────────────────┬──────────────────┐
                 │                 │                  │
        Condition Met      Condition Not Met     Error
             │                  │                  │
             ▼                  ▼                  ▼
    ┌──────────────────┐   │  Continue  │   ├─ Log Error
    │ alert.status =   │   │  monitoring│   └─ Skip Alert
    │ 'auto_resolved'  │   │            │
    │ alert.resolved_at│   │            │
    │ = now()          │   │            │
    │ alert.save()     │   │            │
    │                  │   │            │
    │ Cache:           │   │            │
    │ redis.delete(    │   │            │
    │  f'alert:{id}')  │   │            │
    └──────────────────┘   │            │
             │             │            │
             └─────────────┴────────────┘
```

---

## Data Model Relationships

```
┌──────────────────┐
│    Producer      │ (Supplier)
│  (B2B Supplier)  │
└────────┬─────────┘
         │ 1:1
         ├──────────────────────────────────┐
         │                                  │
         │                     ┌────────────▼──────────┐
         │                     │ SupplierScorecard    │
         │                     │ (Latest scores)      │
         │                     │ • health_score       │
         │                     │ • on_time_delivery   │
         │                     │ • quality_perf       │
         │                     │ • lead_time_cons     │
         │                     └────────────┬──────────┘
         │                                  │ 1:N
         │                     ┌────────────▼──────────┐
         │                     │SupplierScoreHistory  │
         │                     │ (Historical records) │
         │                     │ (90-day retention)   │
         │                     └──────────────────────┘
         │
         │ 1:N
         ├──────────────────────────────────┐
         │                                  │
         ▼                                  │
    ┌─────────┐                            │
    │ Product │                            │
    │   1:N   │                            │
    └────┬────┘                            │
         │                                 │
         │ 1:N                             │
         ├─────────────────┐               │
         │                 │               │
         ▼                 ▼               │
   ┌────────┐        ┌────────────┐       │
   │ Order  │        │StockHistory│       │
   │  1:N   │        │ (90-day)   │       │
   └────┬───┘        └────────────┘       │
        │                                 │
        │ 1:N                             │
        ▼                                 │
   ┌────────┐                             │
   │ Sale   │                             │
   │  1:1   │                             │
   └────┬───┘                             │
        │                                 │
        │ 1:N                             │
        ▼                                 │
   ┌──────────┐                           │
   │Delivery  │                           │
   │  1:N     │                           │
   └──────────┘                           │
                                          │
         ┌────────────────────────────────┘
         │
         │ 1:N
         ▼
   ┌──────────────────┐
   │SupplyChainAlert  │
   │ • alert_type     │
   │ • severity       │
   │ • status         │
   │ • triggered_at   │
   └──────────────────┘

   ┌──────────────────┐
   │SupplyChainKPI    │
   │ (6-hourly)       │
   │ • otif_rate      │
   │ • lead_time_var  │
   │ • inv_turnover   │
   └──────────────────┘

   ┌──────────────────┐
   │RiskCategory      │
   │ (Daily at 6 AM)  │
   │ • supplier_risk  │
   │ • logistics_risk │
   │ • demand_risk    │
   │ • inventory_risk │
   │ • overall_score  │
   └──────┬───────────┘
          │ 1:N
          ▼
   ┌──────────────────┐
   │RiskDrillDown     │
   │ (Detail items)   │
   │ • risk_type      │
   │ • item_type      │
   │ • metric_value   │
   └──────────────────┘

   ┌──────────────────┐
   │ProductDefect     │
   │Record            │
   │ • defect_type    │
   │ • qty_defective  │
   │ • resolution     │
   └──────────────────┘

   ┌──────────────────┐
   │AlertThreshold    │
   │ (Configurable)   │
   │ • alert_type     │
   │ • critical_val   │
   │ • warning_val    │
   │ • check_freq     │
   └──────────────────┘
```

---

## Task Execution Timeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    24-HOUR TASK SCHEDULE                        │
└─────────────────────────────────────────────────────────────────┘

00:00 ─ Midnight
├─ ✅ calculate_supplier_health_scores()
│  └─ Duration: ~30-60 seconds
│  └─ Output: SupplierScorecard, SupplierScoreHistory
│
01:00 ─ 1 AM
├─ ✅ periodic_cleanup_deliveries() [from existing]
│
02:00 ─ 2 AM
├─ ✅ auto_resolve_alerts()
│  └─ Check if conditions normalized
│  └─ Mark as 'auto_resolved'
│
│  ✅ cleanup_old_notifications() [from existing]
│
04:00 ─ 4 AM
├─ ✅ update_device_token_status_task() [from existing]
│
06:00 ─ 6 AM
├─ ✅ calculate_risk_categories()
│  └─ Aggregate data from all modules
│  └─ Output: RiskCategory, RiskDrillDown records
│
│  ✅ generate_notification_analytics_task() [from existing]
│
────────────────────────────────────────────────────────────────

Every 2 Hours (00, 02, 04, 06, 08, 10, 12, 14, 16, 18, 20, 22)
├─ ✅ check_supplier_health_alerts()
│  └─ Critical: score < 60
│  └─ Warning: score dropped > 10 points
│
├─ ✅ check_otif_alerts()
│  └─ Critical: OTIF < 90%
│  └─ Warning: trending down > 5%
│
└─ ✅ check_stock_alerts()
   └─ Critical: items below safety stock
   └─ Warning: lead time increasing

Every 6 Hours (00, 06, 12, 18)
├─ ✅ calculate_supply_chain_kpis()
│  └─ OTIF, Lead Time Variability, Inventory Turnover
│  └─ Compare to previous periods
│
└─ ✅ periodic_delivery_reminders() [from existing]

Every 15 Minutes (starting :00)
└─ ✅ periodic_delivery_reminders() [from existing]

Every 5 Minutes
└─ ✅ send_scheduled_notifications_task() [from existing]

Every 2 Minutes
└─ ✅ process_notification_queue_task() [from existing]

─────────────────────────────────────────────────────────────────
Total Tasks Running: 30 (7 new + 23 existing)
Peak Load: 6 AM (3 concurrent tasks)
Estimated Worker CPU: ~15-20% average
Estimated Memory: ~200-300MB per worker
─────────────────────────────────────────────────────────────────
```

---

## Caching Strategy

```
┌──────────────────────────────────────────────┐
│          REDIS CACHE STRUCTURE                │
├──────────────────────────────────────────────┤
│ Key Prefix: risk:                            │
└──────────────────────────────────────────────┘

1. Scorecard Cache
   ┌──────────────────────────────────────────┐
   │ supplier:{id}:scorecard                   │
   │ Type: JSON String                        │
   │ TTL: 3600 seconds (1 hour)               │
   │ Size: ~500 bytes                         │
   │ Updated: Every score calculation         │
   │ Hit Rate Target: 95%                     │
   │                                          │
   │ Content:                                 │
   │ {                                        │
   │   "health_score": 85.5,                  │
   │   "status": "healthy",                   │
   │   "on_time_delivery": 92,                │
   │   "quality": 98,                         │
   │   "lead_time_consistency": 85,           │
   │   "calculated_at": "2024-01-20T00:00Z"  │
   │ }                                        │
   └──────────────────────────────────────────┘

2. KPI Cache
   ┌──────────────────────────────────────────┐
   │ supplier:{id}:kpi:current                │
   │ Type: JSON String                        │
   │ TTL: 1800 seconds (30 minutes)           │
   │ Size: ~1KB                               │
   │ Updated: Every 6 hours (task)            │
   │ Also cached on fetch (30 min refresh)    │
   │                                          │
   │ supplier:{id}:kpi:trends:30d             │
   │ Type: JSON Array                         │
   │ TTL: 7200 seconds (2 hours)              │
   │ Size: ~5KB                               │
   │ Updated: When new KPI created            │
   └──────────────────────────────────────────┘

3. Alert Cache
   ┌──────────────────────────────────────────┐
   │ supplier:{id}:alerts:active              │
   │ Type: Redis List                         │
   │ TTL: 600 seconds (10 minutes)            │
   │ Count: 1-50 items                        │
   │ Updated: Every alert trigger/resolution  │
   │                                          │
   │ alert:{id}:details                       │
   │ Type: JSON String                        │
   │ TTL: 86400 seconds (24 hours)            │
   │ Size: ~500-1KB per alert                 │
   └──────────────────────────────────────────┘

4. Risk Categories Cache
   ┌──────────────────────────────────────────┐
   │ risk:categories:current                  │
   │ Type: JSON String                        │
   │ TTL: 7200 seconds (2 hours)              │
   │ Size: ~2KB                               │
   │ Updated: Daily at 6 AM                   │
   │                                          │
   │ risk:{id}:drilldowns                     │
   │ Type: JSON Array                         │
   │ TTL: 7200 seconds (2 hours)              │
   │ Size: ~5-10KB                            │
   └──────────────────────────────────────────┘

5. Threshold Cache
   ┌──────────────────────────────────────────┐
   │ thresholds:all                           │
   │ Type: JSON Map                           │
   │ TTL: 86400 seconds (24 hours)            │
   │ Size: ~1KB                               │
   │ Updated: When admin changes config       │
   │ Read: Every task execution               │
   └──────────────────────────────────────────┘

6. Metrics Aggregation Cache
   ┌──────────────────────────────────────────┐
   │ metrics:aggregated:{date}                │
   │ Type: JSON String                        │
   │ TTL: 3600 seconds (1 hour)               │
   │ Size: ~2KB                               │
   │ Purpose: Dashboard summary endpoint      │
   │ Updated: Every hour or on demand         │
   └──────────────────────────────────────────┘

─────────────────────────────────────────────
Estimated Total Cache Size: 50-100 MB
Cache Memory per 1000 Suppliers: ~1-2 MB
Cache Miss Rate Target: < 5%
Cache Eviction: LRU with TTL expiration
─────────────────────────────────────────────
```

---

## Concurrency & Performance

```
┌────────────────────────────────────────────────────────┐
│        CELERY WORKER CONFIGURATION                     │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Worker 1: cpu_bound                                   │
│ ├─ Calculate Tasks (score, KPI, risk)                │
│ ├─ Concurrency: 4 (processes)                         │
│ ├─ Pool: prefork                                      │
│ └─ Max Memory: 500MB                                  │
│                                                        │
│ Worker 2: io_bound                                    │
│ ├─ Alert & Notification Tasks                        │
│ ├─ Concurrency: 20 (threads)                          │
│ ├─ Pool: solo (single process)                        │
│ └─ Max Memory: 300MB                                  │
│                                                        │
│ Beat Scheduler                                        │
│ ├─ Single instance (no clustering)                    │
│ ├─ Heartbeat: 2 seconds                               │
│ └─ Max Memory: 100MB                                  │
│                                                        │
└────────────────────────────────────────────────────────┘

Performance Benchmarks:
────────────────────────────────────────────────────────

Task Name                  Input       Duration    Memory
─────────────────────────  ──────────  ─────────   ──────
calc_supplier_health       1000 sup    45s         120MB
calc_supply_chain_kpi      1000 sup    60s         150MB
check_supplier_alerts      1000 sup    15s         80MB
check_otif_alerts          1000 sup    10s         60MB
check_stock_alerts         10k prod    20s         100MB
auto_resolve_alerts        500 alerts  5s          40MB
calc_risk_categories       1000 sup    30s         90MB
─────────────────────────  ──────────  ─────────   ──────

Database Query Optimization:
────────────────────────────────────────────────────────

Indexes Created:
├─ (supplier_id, snapshot_date)
│  ├─ Supplier scorecard lookups
│  ├─ KPI queries
│  └─ Alert filtering
│
├─ (alert_type, severity, status)
│  └─ Alert dashboard queries
│
├─ (supplier_id, recorded_at)
│  └─ Score history trends
│
└─ (status, triggered_at)
   └─ Auto-resolution queries

Query Optimization:
├─ Use select_related() for FK joins
├─ Use prefetch_related() for reverse relations
├─ Batch operations (bulk_create, bulk_update)
├─ Use only() and defer() for large queries
└─ Aggregate at DB level (Sum, Avg, Count)

Connection Pool:
├─ Database: 20 connections
├─ Cache (Redis): 10 connections
└─ Timeouts: 30 seconds
```

---

## Error Handling & Monitoring

```
┌──────────────────────────────────────────────┐
│    ERROR HANDLING STRATEGY                    │
├──────────────────────────────────────────────┤
│                                              │
│ Celery Task Failures:                        │
│ ├─ Retry: 3 times (exponential backoff)     │
│ ├─ Countdown: 60, 300, 900 seconds          │
│ ├─ Log to: logger.error() with full trace   │
│ ├─ Monitor: Sentry integration (optional)   │
│ └─ Alert: Email to ops on max_retries       │
│                                              │
│ Database Errors:                             │
│ ├─ Transaction rollback on exception        │
│ ├─ Use atomic() for consistency             │
│ ├─ Retry with select_for_update()           │
│ └─ Log & continue                           │
│                                              │
│ API Errors:                                  │
│ ├─ 400: Bad request (validation)            │
│ ├─ 401: Unauthorized                        │
│ ├─ 403: Forbidden                           │
│ ├─ 404: Not found                           │
│ └─ 500: Server error (log & alert)          │
│                                              │
│ Cache Failures:                              │
│ ├─ Graceful fallback to DB query            │
│ ├─ Log miss/error                           │
│ ├─ Rebuild on next task run                 │
│ └─ Health check: redis-cli ping()           │
│                                              │
└──────────────────────────────────────────────┘

Monitoring & Alerting:
────────────────────────────────────────────────

Metrics to Track:
├─ Task Execution:
│  ├─ Duration (target: < 60s)
│  ├─ Success rate (target: > 99.5%)
│  ├─ Retry count (target: < 1%)
│  └─ Queue depth
│
├─ Data Quality:
│  ├─ Missing data points
│  ├─ Outliers in metrics
│  ├─ Stale cache (> TTL)
│  └─ DB query count
│
├─ System Health:
│  ├─ CPU usage
│  ├─ Memory usage
│  ├─ Disk I/O
│  └─ Network latency
│
└─ Business Metrics:
   ├─ Alerts generated/day
   ├─ False positive rate
   ├─ Alert resolution time
   └─ Dashboard access patterns

Alert Thresholds:
├─ Task duration > 120s → Warning
├─ Task failure rate > 5% → Critical
├─ Queue depth > 1000 → Warning
├─ Cache hit rate < 80% → Info
├─ DB connections > 80% → Warning
└─ Memory usage > 80% → Critical
```

---

## Security Considerations

```
┌──────────────────────────────────────────────┐
│    SECURITY & PERMISSION RULES                │
├──────────────────────────────────────────────┤
│                                              │
│ Authentication:                              │
│ ├─ JWT Token or Session auth                │
│ ├─ API Key for external systems             │
│ ├─ Rate limiting: 100 req/min per user      │
│ └─ Token expiry: 24 hours                   │
│                                              │
│ Authorization:                               │
│ ├─ Supplier: View own scorecard/alerts      │
│ ├─ Admin: View all + configure thresholds   │
│ ├─ Read-only: No create/update/delete       │
│ └─ Role-based access (RBAC)                 │
│                                              │
│ Data Privacy:                                │
│ ├─ Mask sensitive data in logs              │
│ ├─ Encrypt at-rest (TLS 1.3)                │
│ ├─ Audit trail for all changes              │
│ └─ GDPR compliance: retention policy        │
│                                              │
│ API Security:                                │
│ ├─ CORS: origin validation                  │
│ ├─ CSRF: token validation                   │
│ ├─ SQL injection: ORM parameterization      │
│ ├─ XSS: Django template escaping            │
│ └─ Dependency scanning (pip audit)          │
│                                              │
└──────────────────────────────────────────────┘

Recommended Permissions:
────────────────────────────────────────────────

class IsSupplierOrAdmin(permissions.BasePermission):
    """
    Supplier sees own data, admin sees all.
    """
    def has_object_permission(self, request, view, obj):
        # Admin can see everything
        if request.user.is_staff:
            return True
        
        # Supplier can see own data
        if hasattr(request.user, 'producer'):
            if obj.supplier == request.user.producer:
                return True
        
        return False
```

---

## Migration Path & Deployment

```
Pre-Deployment Checklist:
────────────────────────────────────────────────

□ Create all new models and migrations
□ Run migrations on staging
□ Test all Celery tasks locally
□ Configure Redis connection
□ Set up Celery Beat schedule
□ Create required notification templates
□ Configure alert thresholds
□ Set up logging and monitoring
□ Load historical data (if needed)
□ Test API endpoints
□ Performance testing (5000+ records)
□ Security audit (OWASP)
□ Backup database
□ Notify stakeholders

Deployment Steps:
────────────────────────────────────────────────

1. Code Deployment
   ├─ Deploy to staging
   ├─ Run migrations: python manage.py migrate
   ├─ Collect static: python manage.py collectstatic
   └─ Restart web workers

2. Celery Deployment
   ├─ Start new Celery Beat scheduler
   ├─ Start new Worker processes
   ├─ Verify task queue
   └─ Check logs for errors

3. Database Validation
   ├─ Check data integrity
   ├─ Verify index creation
   ├─ Monitor query performance
   └─ Check disk space

4. Smoke Tests
   ├─ API endpoints respond (200 OK)
   ├─ Celery tasks execute
   ├─ Notifications send
   ├─ Cache operates
   └─ Database queries < 1s

5. Production Rollout
   ├─ Deploy to production
   ├─ Monitor for 24 hours
   ├─ Check error logs
   ├─ Verify metrics collection
   └─ Announce to users

Rollback Plan:
────────────────────────────────────────────────

IF critical issues:
├─ Revert code commit
├─ Keep new tables (for data safety)
├─ Restart old Celery tasks
├─ Monitor for stability
└─ Plan hotfix
```

---

This technical architecture provides a solid foundation for scalable, reliable risk management in your supply chain system.
