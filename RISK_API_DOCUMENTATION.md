# Risk Management API Documentation

**Base URL:** `/api/v1/`

**Authentication:** Token-based (Include `Authorization: Bearer <token>` in header)

**Response Format:** JSON

---

## 1. Supplier Scorecard Endpoints

### 1.1 List All Scorecards
**Endpoint:** `GET /supplier-scorecards/`

**Authentication:** Required

**Permissions:**
- Admins: See all suppliers
- Suppliers: See only their own scorecard
- Others: Empty list

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `health_status` | string | Filter by status: `healthy`, `monitor`, `critical` | `health_status=critical` |
| `supplier__name` | string | Filter by supplier name | `supplier__name=Acme` |
| `ordering` | string | Sort by field (prefix `-` for desc) | `ordering=-health_score` |

**Response (200 OK):**
```json
{
  "count": 45,
  "next": "http://api/v1/supplier-scorecards/?page=2",
  "previous": null,
  "results": [
    {
      "supplier_id": 1,
      "supplier_name": "Acme Manufacturing",
      "health_score": 85.5,
      "health_status": "healthy",
      "health_status_display": "Healthy (80-100)",
      "on_time_delivery_pct": 92.5,
      "quality_performance_pct": 98.0,
      "lead_time_consistency_pct": 88.5,
      "payment_reliability_pct": 100.0,
      "total_orders": 150,
      "on_time_orders": 139,
      "defect_count": 3,
      "avg_lead_time_days": 7.2,
      "lead_time_variance": 1.5,
      "late_payments_count": 0,
      "is_healthy": true,
      "is_critical": false,
      "last_calculated": "2026-01-20T00:00:00Z",
      "calculation_period_start": "2025-10-22",
      "created_at": "2025-10-22T10:30:00Z",
      "updated_at": "2026-01-20T00:00:00Z"
    }
  ]
}
```

---

### 1.2 Get Specific Scorecard
**Endpoint:** `GET /supplier-scorecards/{id}/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Scorecard ID |

**Response (200 OK):**
```json
{
  "supplier_id": 1,
  "supplier_name": "Acme Manufacturing",
  "health_score": 85.5,
  "health_status": "healthy",
  "health_status_display": "Healthy (80-100)",
  "on_time_delivery_pct": 92.5,
  "quality_performance_pct": 98.0,
  "lead_time_consistency_pct": 88.5,
  "payment_reliability_pct": 100.0,
  "total_orders": 150,
  "on_time_orders": 139,
  "defect_count": 3,
  "avg_lead_time_days": 7.2,
  "lead_time_variance": 1.5,
  "late_payments_count": 0,
  "is_healthy": true,
  "is_critical": false,
  "last_calculated": "2026-01-20T00:00:00Z",
  "calculation_period_start": "2025-10-22",
  "created_at": "2025-10-22T10:30:00Z",
  "updated_at": "2026-01-20T00:00:00Z"
}
```

**Error Responses:**
- `404 Not Found`: Scorecard doesn't exist or user doesn't have access

---

### 1.3 Get Current User's Scorecard
**Endpoint:** `GET /supplier-scorecards/current/`

**Authentication:** Required

**Description:** Returns the authenticated user's supplier scorecard. For admins, returns null with a message.

**Response (200 OK):**
```json
{
  "supplier_id": 1,
  "supplier_name": "Acme Manufacturing",
  "health_score": 85.5,
  "health_status": "healthy",
  "health_status_display": "Healthy (80-100)",
  "on_time_delivery_pct": 92.5,
  "quality_performance_pct": 98.0,
  "lead_time_consistency_pct": 88.5,
  "payment_reliability_pct": 100.0,
  "total_orders": 150,
  "on_time_orders": 139,
  "defect_count": 3,
  "avg_lead_time_days": 7.2,
  "lead_time_variance": 1.5,
  "late_payments_count": 0,
  "is_healthy": true,
  "is_critical": false,
  "last_calculated": "2026-01-20T00:00:00Z",
  "calculation_period_start": "2025-10-22",
  "created_at": "2025-10-22T10:30:00Z",
  "updated_at": "2026-01-20T00:00:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "No scorecard found for your supplier"
}
```

---

### 1.4 Get 90-Day History
**Endpoint:** `GET /supplier-scorecards/{id}/history/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Scorecard ID |

**Response (200 OK):**
```json
[
  {
    "supplier_name": "Acme Manufacturing",
    "health_score": 85.5,
    "health_status": "healthy",
    "health_status_display": "Healthy (80-100)",
    "on_time_delivery_pct": 92.5,
    "quality_performance_pct": 98.0,
    "lead_time_consistency_pct": 88.5,
    "recorded_at": "2026-01-20T00:00:00Z"
  },
  {
    "supplier_name": "Acme Manufacturing",
    "health_score": 84.2,
    "health_status": "healthy",
    "health_status_display": "Healthy (80-100)",
    "on_time_delivery_pct": 91.5,
    "quality_performance_pct": 97.8,
    "lead_time_consistency_pct": 87.5,
    "recorded_at": "2026-01-19T00:00:00Z"
  }
]
```

---

### 1.5 Compare Multiple Scorecards
**Endpoint:** `GET /supplier-scorecards/comparison/`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `supplier_ids` | string (comma-separated) | Supplier IDs to compare (optional, defaults to top 10) | `supplier_ids=1,2,3` |

**Response (200 OK):**
```json
[
  {
    "supplier_id": 1,
    "supplier_name": "Acme Manufacturing",
    "health_score": 85.5,
    "health_status": "healthy",
    "on_time_delivery_pct": 92.5,
    "quality_performance_pct": 98.0,
    "lead_time_consistency_pct": 88.5,
    "payment_reliability_pct": 100.0,
    "is_healthy": true,
    "is_critical": false
  },
  {
    "supplier_id": 2,
    "supplier_name": "Global Parts Ltd",
    "health_score": 72.3,
    "health_status": "monitor",
    "on_time_delivery_pct": 75.0,
    "quality_performance_pct": 88.0,
    "lead_time_consistency_pct": 70.2,
    "payment_reliability_pct": 95.0,
    "is_healthy": false,
    "is_critical": false
  }
]
```

---

## 2. Supply Chain KPI Endpoints

### 2.1 List KPI Snapshots
**Endpoint:** `GET /kpis/`

**Authentication:** Required

**Permissions:**
- Admins: See all KPIs
- Suppliers: See only their KPIs
- Others: Empty list

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `supplier__name` | string | Filter by supplier name | `supplier__name=Acme` |
| `snapshot_date` | date | Filter by date (YYYY-MM-DD) | `snapshot_date=2026-01-20` |
| `ordering` | string | Sort field (prefix `-` for desc) | `ordering=-snapshot_date` |

**Response (200 OK):**
```json
{
  "count": 120,
  "next": "http://api/v1/kpis/?page=2",
  "previous": null,
  "results": [
    {
      "supplier_name": "Acme Manufacturing",
      "otif_rate": 94.5,
      "otif_previous": 93.2,
      "otif_trend_pct": 1.4,
      "lead_time_variability": 1.2,
      "lead_time_avg": 7.5,
      "lead_time_trend": -0.3,
      "inventory_turnover_ratio": 12.5,
      "inventory_turnover_previous": 12.2,
      "inventory_trend_pct": 2.5,
      "stock_out_incidents": 2,
      "low_stock_items_count": 5,
      "orders_pending_count": 12,
      "orders_delayed_count": 1,
      "period_start": "2026-01-20",
      "period_end": "2026-01-20",
      "snapshot_date": "2026-01-20",
      "created_at": "2026-01-20T10:30:00Z"
    }
  ]
}
```

---

### 2.2 Get Specific KPI
**Endpoint:** `GET /kpis/{id}/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | KPI ID |

**Response (200 OK):**
```json
{
  "supplier_name": "Acme Manufacturing",
  "otif_rate": 94.5,
  "otif_previous": 93.2,
  "otif_trend_pct": 1.4,
  "lead_time_variability": 1.2,
  "lead_time_avg": 7.5,
  "lead_time_trend": -0.3,
  "inventory_turnover_ratio": 12.5,
  "inventory_turnover_previous": 12.2,
  "inventory_trend_pct": 2.5,
  "stock_out_incidents": 2,
  "low_stock_items_count": 5,
  "orders_pending_count": 12,
  "orders_delayed_count": 1,
  "period_start": "2026-01-20",
  "period_end": "2026-01-20",
  "snapshot_date": "2026-01-20",
  "created_at": "2026-01-20T10:30:00Z"
}
```

---

### 2.3 Get Latest KPI (Current)
**Endpoint:** `GET /kpis/current/`

**Authentication:** Required

**Description:** Returns the most recent KPI snapshot for the authenticated supplier.

**Response (200 OK):**
```json
{
  "supplier_name": "Acme Manufacturing",
  "otif_rate": 94.5,
  "otif_previous": 93.2,
  "otif_trend_pct": 1.4,
  "lead_time_variability": 1.2,
  "lead_time_avg": 7.5,
  "lead_time_trend": -0.3,
  "inventory_turnover_ratio": 12.5,
  "inventory_turnover_previous": 12.2,
  "inventory_trend_pct": 2.5,
  "stock_out_incidents": 2,
  "low_stock_items_count": 5,
  "orders_pending_count": 12,
  "orders_delayed_count": 1,
  "period_start": "2026-01-20",
  "period_end": "2026-01-20",
  "snapshot_date": "2026-01-20",
  "created_at": "2026-01-20T10:30:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "No KPI data found"
}
```

---

### 2.4 Get 30-Day Trends
**Endpoint:** `GET /kpis/trends/`

**Authentication:** Required

**Description:** Returns KPI snapshots for the last 30 days.

**Response (200 OK):**
```json
[
  {
    "supplier_name": "Acme Manufacturing",
    "otif_rate": 94.5,
    "otif_previous": 93.2,
    "otif_trend_pct": 1.4,
    "lead_time_variability": 1.2,
    "lead_time_avg": 7.5,
    "lead_time_trend": -0.3,
    "inventory_turnover_ratio": 12.5,
    "inventory_turnover_previous": 12.2,
    "inventory_trend_pct": 2.5,
    "stock_out_incidents": 2,
    "low_stock_items_count": 5,
    "orders_pending_count": 12,
    "orders_delayed_count": 1,
    "period_start": "2026-01-20",
    "period_end": "2026-01-20",
    "snapshot_date": "2026-01-20",
    "created_at": "2026-01-20T10:30:00Z"
  },
  {
    "supplier_name": "Acme Manufacturing",
    "otif_rate": 93.8,
    "otif_previous": 92.5,
    "otif_trend_pct": 1.4,
    "lead_time_variability": 1.3,
    "lead_time_avg": 7.8,
    "lead_time_trend": -0.1,
    "inventory_turnover_ratio": 12.2,
    "inventory_turnover_previous": 11.9,
    "inventory_trend_pct": 2.5,
    "stock_out_incidents": 3,
    "low_stock_items_count": 6,
    "orders_pending_count": 15,
    "orders_delayed_count": 2,
    "period_start": "2026-01-19",
    "period_end": "2026-01-19",
    "snapshot_date": "2026-01-19",
    "created_at": "2026-01-19T10:30:00Z"
  }
]
```

---

## 3. Supply Chain Alert Endpoints

### 3.1 List Alerts
**Endpoint:** `GET /alerts/`

**Authentication:** Required

**Permissions:**
- Admins: See all alerts
- Suppliers: See only their alerts
- Others: Empty list

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `alert_type` | string | Filter by type | `alert_type=otif_violation` |
| `severity` | string | Filter: `critical`, `warning`, `info` | `severity=critical` |
| `status` | string | Filter: `active`, `acknowledged`, `resolved`, `auto_resolved` | `status=active` |
| `supplier__name` | string | Filter by supplier name | `supplier__name=Acme` |
| `search` | string | Search in title/description | `search=delay` |
| `ordering` | string | Sort by field | `ordering=-triggered_at` |

**Response (200 OK):**
```json
{
  "count": 45,
  "next": "http://api/v1/alerts/?page=2",
  "previous": null,
  "results": [
    {
      "alert_id": "ALR-2026-001",
      "alert_type": "otif_violation",
      "alert_type_display": "OTIF Violation",
      "severity": "critical",
      "severity_display": "Critical",
      "status": "active",
      "status_display": "Active",
      "title": "Critical OTIF Violation - Acme Manufacturing",
      "description": "OTIF rate dropped below 90% threshold",
      "supplier_name": "Acme Manufacturing",
      "product_name": null,
      "metric_value": 87.5,
      "threshold_value": 90.0,
      "triggered_at": "2026-01-20T14:30:00Z",
      "acknowledged_at": null,
      "resolved_at": null,
      "assigned_to_username": "admin",
      "is_notified": true,
      "notification_channels": ["email", "sms"],
      "metadata": {
        "supplier_id": 1,
        "period": "last_30_days",
        "affected_orders": 42
      },
      "created_at": "2026-01-20T14:30:00Z",
      "updated_at": "2026-01-20T14:30:00Z"
    }
  ]
}
```

---

### 3.2 Get Specific Alert
**Endpoint:** `GET /alerts/{id}/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Alert ID |

**Response (200 OK):**
```json
{
  "alert_id": "ALR-2026-001",
  "alert_type": "otif_violation",
  "alert_type_display": "OTIF Violation",
  "severity": "critical",
  "severity_display": "Critical",
  "status": "active",
  "status_display": "Active",
  "title": "Critical OTIF Violation - Acme Manufacturing",
  "description": "OTIF rate dropped below 90% threshold",
  "supplier_name": "Acme Manufacturing",
  "product_name": null,
  "metric_value": 87.5,
  "threshold_value": 90.0,
  "triggered_at": "2026-01-20T14:30:00Z",
  "acknowledged_at": null,
  "resolved_at": null,
  "assigned_to_username": "admin",
  "is_notified": true,
  "notification_channels": ["email", "sms"],
  "metadata": {
    "supplier_id": 1,
    "period": "last_30_days",
    "affected_orders": 42
  },
  "created_at": "2026-01-20T14:30:00Z",
  "updated_at": "2026-01-20T14:30:00Z"
}
```

---

### 3.3 Acknowledge Alert
**Endpoint:** `POST /alerts/{id}/acknowledge/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Alert ID |

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "alert_id": "ALR-2026-001",
  "alert_type": "otif_violation",
  "alert_type_display": "OTIF Violation",
  "severity": "critical",
  "severity_display": "Critical",
  "status": "acknowledged",
  "status_display": "Acknowledged",
  "title": "Critical OTIF Violation - Acme Manufacturing",
  "description": "OTIF rate dropped below 90% threshold",
  "supplier_name": "Acme Manufacturing",
  "product_name": null,
  "metric_value": 87.5,
  "threshold_value": 90.0,
  "triggered_at": "2026-01-20T14:30:00Z",
  "acknowledged_at": "2026-01-20T15:00:00Z",
  "resolved_at": null,
  "assigned_to_username": "admin",
  "is_notified": true,
  "notification_channels": ["email", "sms"],
  "metadata": {
    "supplier_id": 1,
    "period": "last_30_days",
    "affected_orders": 42
  },
  "created_at": "2026-01-20T14:30:00Z",
  "updated_at": "2026-01-20T15:00:00Z"
}
```

---

### 3.4 Resolve Alert
**Endpoint:** `POST /alerts/{id}/resolve/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Alert ID |

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "alert_id": "ALR-2026-001",
  "alert_type": "otif_violation",
  "alert_type_display": "OTIF Violation",
  "severity": "critical",
  "severity_display": "Critical",
  "status": "resolved",
  "status_display": "Resolved",
  "title": "Critical OTIF Violation - Acme Manufacturing",
  "description": "OTIF rate dropped below 90% threshold",
  "supplier_name": "Acme Manufacturing",
  "product_name": null,
  "metric_value": 87.5,
  "threshold_value": 90.0,
  "triggered_at": "2026-01-20T14:30:00Z",
  "acknowledged_at": "2026-01-20T15:00:00Z",
  "resolved_at": "2026-01-20T16:00:00Z",
  "assigned_to_username": "admin",
  "is_notified": true,
  "notification_channels": ["email", "sms"],
  "metadata": {
    "supplier_id": 1,
    "period": "last_30_days",
    "affected_orders": 42
  },
  "created_at": "2026-01-20T14:30:00Z",
  "updated_at": "2026-01-20T16:00:00Z"
}
```

---

### 3.5 Get Active Alerts
**Endpoint:** `GET /alerts/active/`

**Authentication:** Required

**Description:** Returns all alerts with status `active` or `acknowledged`.

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `alert_type` | string | Filter by type | `alert_type=otif_violation` |
| `severity` | string | Filter: `critical`, `warning`, `info` | `severity=critical` |
| `supplier__name` | string | Filter by supplier | `supplier__name=Acme` |

**Response (200 OK):**
```json
{
  "count": 12,
  "next": null,
  "previous": null,
  "results": [
    {
      "alert_id": "ALR-2026-001",
      "alert_type": "otif_violation",
      "alert_type_display": "OTIF Violation",
      "severity": "critical",
      "severity_display": "Critical",
      "status": "active",
      "status_display": "Active",
      "title": "Critical OTIF Violation - Acme Manufacturing",
      "description": "OTIF rate dropped below 90% threshold",
      "supplier_name": "Acme Manufacturing",
      "product_name": null,
      "metric_value": 87.5,
      "threshold_value": 90.0,
      "triggered_at": "2026-01-20T14:30:00Z",
      "acknowledged_at": null,
      "resolved_at": null,
      "assigned_to_username": "admin",
      "is_notified": true,
      "notification_channels": ["email", "sms"],
      "metadata": {},
      "created_at": "2026-01-20T14:30:00Z",
      "updated_at": "2026-01-20T14:30:00Z"
    }
  ]
}
```

---

### 3.6 Get Alert Statistics
**Endpoint:** `GET /alerts/statistics/`

**Authentication:** Required

**Description:** Returns summary statistics of all alerts.

**Response (200 OK):**
```json
{
  "total_alerts": 150,
  "active": 12,
  "acknowledged": 5,
  "resolved": 133,
  "by_severity": {
    "critical": 8,
    "warning": 6,
    "info": 136
  },
  "by_type": {
    "otif_violation": 25,
    "quality_issue": 18,
    "delivery_delay": 42,
    "inventory_low": 38,
    "supplier_risk": 27
  },
  "last_7_days": 35
}
```

---

## 4. Alert Threshold Endpoints

### 4.1 List Alert Thresholds
**Endpoint:** `GET /alert-thresholds/`

**Authentication:** Required (Admin Only)

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `alert_type` | string | Filter by alert type | `alert_type=otif_violation` |

**Response (200 OK):**
```json
{
  "count": 8,
  "next": null,
  "previous": null,
  "results": [
    {
      "alert_type": "otif_violation",
      "alert_type_display": "OTIF Violation",
      "critical_threshold": 80.0,
      "critical_enabled": true,
      "warning_threshold": 90.0,
      "warning_enabled": true,
      "check_frequency_minutes": 60,
      "auto_resolve_hours": 24,
      "description": "Alerts when OTIF rate falls below threshold",
      "created_at": "2025-10-22T10:00:00Z",
      "updated_at": "2026-01-20T10:00:00Z"
    },
    {
      "alert_type": "quality_issue",
      "alert_type_display": "Quality Issue",
      "critical_threshold": 90.0,
      "critical_enabled": true,
      "warning_threshold": 95.0,
      "warning_enabled": true,
      "check_frequency_minutes": 120,
      "auto_resolve_hours": 48,
      "description": "Alerts when quality performance drops",
      "created_at": "2025-10-22T10:00:00Z",
      "updated_at": "2026-01-20T10:00:00Z"
    }
  ]
}
```

---

### 4.2 Get Specific Threshold
**Endpoint:** `GET /alert-thresholds/{id}/`

**Authentication:** Required (Admin Only)

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Threshold ID |

**Response (200 OK):**
```json
{
  "alert_type": "otif_violation",
  "alert_type_display": "OTIF Violation",
  "critical_threshold": 80.0,
  "critical_enabled": true,
  "warning_threshold": 90.0,
  "warning_enabled": true,
  "check_frequency_minutes": 60,
  "auto_resolve_hours": 24,
  "description": "Alerts when OTIF rate falls below threshold",
  "created_at": "2025-10-22T10:00:00Z",
  "updated_at": "2026-01-20T10:00:00Z"
}
```

---

### 4.3 Update Threshold
**Endpoint:** `PUT /alert-thresholds/{id}/`

**Authentication:** Required (Admin Only)

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Threshold ID |

**Request Body:**
```json
{
  "critical_threshold": 75.0,
  "critical_enabled": true,
  "warning_threshold": 85.0,
  "warning_enabled": true,
  "check_frequency_minutes": 45,
  "auto_resolve_hours": 20,
  "description": "Updated OTIF threshold"
}
```

**Response (200 OK):**
```json
{
  "alert_type": "otif_violation",
  "alert_type_display": "OTIF Violation",
  "critical_threshold": 75.0,
  "critical_enabled": true,
  "warning_threshold": 85.0,
  "warning_enabled": true,
  "check_frequency_minutes": 45,
  "auto_resolve_hours": 20,
  "description": "Updated OTIF threshold",
  "created_at": "2025-10-22T10:00:00Z",
  "updated_at": "2026-01-20T11:00:00Z"
}
```

---

## 5. Risk Category Endpoints

### 5.1 List Risk Categories
**Endpoint:** `GET /risk-categories/`

**Authentication:** Required

**Permissions:**
- Admins: See all risk categories
- Suppliers: See only their risk categories
- Others: Empty list

**Query Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `supplier__name` | string | Filter by supplier name | `supplier__name=Acme` |
| `overall_risk_level` | string | Filter: `low`, `medium`, `high`, `critical` | `overall_risk_level=high` |
| `ordering` | string | Sort by field | `ordering=-snapshot_date` |

**Response (200 OK):**
```json
{
  "count": 45,
  "next": null,
  "previous": null,
  "results": [
    {
      "supplier_name": "Acme Manufacturing",
      "supplier_risk_level": "medium",
      "supplier_risk_level_display": "Medium",
      "supplier_high_risk_count": 2,
      "supplier_spend_at_risk": 150000.0,
      "single_source_dependencies": 3,
      "logistics_risk_level": "low",
      "logistics_risk_level_display": "Low",
      "active_shipment_delays": 1,
      "avg_delay_days": 2.5,
      "routes_with_issues": 1,
      "demand_risk_level": "medium",
      "demand_risk_level_display": "Medium",
      "forecast_accuracy": 87.5,
      "volatile_products_count": 5,
      "stockout_incidents": 2,
      "inventory_risk_level": "low",
      "inventory_risk_level_display": "Low",
      "items_below_safety_stock": 3,
      "overstock_items_count": 2,
      "total_inventory_value_at_risk": 45000.0,
      "overall_risk_score": 58.3,
      "overall_risk_level": "medium",
      "overall_risk_level_display": "Medium",
      "drill_downs": [],
      "snapshot_date": "2026-01-20",
      "last_updated": "2026-01-20T10:00:00Z",
      "created_at": "2026-01-20T10:00:00Z"
    }
  ]
}
```

---

### 5.2 Get Specific Risk Category
**Endpoint:** `GET /risk-categories/{id}/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Risk Category ID |

**Response (200 OK):**
```json
{
  "supplier_name": "Acme Manufacturing",
  "supplier_risk_level": "medium",
  "supplier_risk_level_display": "Medium",
  "supplier_high_risk_count": 2,
  "supplier_spend_at_risk": 150000.0,
  "single_source_dependencies": 3,
  "logistics_risk_level": "low",
  "logistics_risk_level_display": "Low",
  "active_shipment_delays": 1,
  "avg_delay_days": 2.5,
  "routes_with_issues": 1,
  "demand_risk_level": "medium",
  "demand_risk_level_display": "Medium",
  "forecast_accuracy": 87.5,
  "volatile_products_count": 5,
  "stockout_incidents": 2,
  "inventory_risk_level": "low",
  "inventory_risk_level_display": "Low",
  "items_below_safety_stock": 3,
  "overstock_items_count": 2,
  "total_inventory_value_at_risk": 45000.0,
  "overall_risk_score": 58.3,
  "overall_risk_level": "medium",
  "overall_risk_level_display": "Medium",
  "drill_downs": [],
  "snapshot_date": "2026-01-20",
  "last_updated": "2026-01-20T10:00:00Z",
  "created_at": "2026-01-20T10:00:00Z"
}
```

---

### 5.3 Get Current Risk Assessment
**Endpoint:** `GET /risk-categories/current/`

**Authentication:** Required

**Description:** Returns today's risk assessment for the authenticated user.

**Response (200 OK):**
```json
{
  "supplier_name": "Acme Manufacturing",
  "supplier_risk_level": "medium",
  "supplier_risk_level_display": "Medium",
  "supplier_high_risk_count": 2,
  "supplier_spend_at_risk": 150000.0,
  "single_source_dependencies": 3,
  "logistics_risk_level": "low",
  "logistics_risk_level_display": "Low",
  "active_shipment_delays": 1,
  "avg_delay_days": 2.5,
  "routes_with_issues": 1,
  "demand_risk_level": "medium",
  "demand_risk_level_display": "Medium",
  "forecast_accuracy": 87.5,
  "volatile_products_count": 5,
  "stockout_incidents": 2,
  "inventory_risk_level": "low",
  "inventory_risk_level_display": "Low",
  "items_below_safety_stock": 3,
  "overstock_items_count": 2,
  "total_inventory_value_at_risk": 45000.0,
  "overall_risk_score": 58.3,
  "overall_risk_level": "medium",
  "overall_risk_level_display": "Medium",
  "drill_downs": [],
  "snapshot_date": "2026-01-20",
  "last_updated": "2026-01-20T10:00:00Z",
  "created_at": "2026-01-20T10:00:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "No risk assessment found for today"
}
```

---

### 5.4 Get Risk Drill-Downs (Details)
**Endpoint:** `GET /risk-categories/{id}/drill-downs/`

**Authentication:** Required

**URL Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Risk Category ID |

**Response (200 OK):**
```json
{
  "count": 15,
  "next": null,
  "previous": null,
  "results": [
    {
      "risk_type": "supplier_concentration",
      "risk_type_display": "Supplier Concentration",
      "item_type": "product",
      "item_type_display": "Product",
      "item_id": 42,
      "item_name": "Microchip A1000",
      "metric_value": 75.0,
      "threshold": 80.0,
      "status": "high_risk",
      "status_display": "High Risk",
      "details": {
        "num_suppliers": 1,
        "single_source": true,
        "recommended_suppliers": ["Supplier B", "Supplier C"]
      },
      "created_at": "2026-01-20T10:00:00Z",
      "updated_at": "2026-01-20T10:00:00Z"
    },
    {
      "risk_type": "delivery_delay",
      "risk_type_display": "Delivery Delay",
      "item_type": "shipment",
      "item_type_display": "Shipment",
      "item_id": 5001,
      "item_name": "Shipment SHP-2026-001",
      "metric_value": 5.0,
      "threshold": 3.0,
      "status": "high_risk",
      "status_display": "High Risk",
      "details": {
        "days_delayed": 5,
        "expected_delivery": "2026-01-15",
        "current_status": "in_transit",
        "reason": "weather_delay"
      },
      "created_at": "2026-01-20T10:00:00Z",
      "updated_at": "2026-01-20T10:00:00Z"
    }
  ]
}
```

---

### 5.5 Get Risk Dashboard Summary
**Endpoint:** `GET /risk-categories/summary/`

**Authentication:** Required

**Description:** Returns comprehensive dashboard with risk overview, scorecard, KPIs, and alerts.

**Response (200 OK):**
```json
{
  "timestamp": "2026-01-20T15:30:00Z",
  "supplier_scorecard": {
    "supplier_id": 1,
    "supplier_name": "Acme Manufacturing",
    "health_score": 85.5,
    "health_status": "healthy",
    "health_status_display": "Healthy (80-100)",
    "on_time_delivery_pct": 92.5,
    "quality_performance_pct": 98.0,
    "lead_time_consistency_pct": 88.5,
    "payment_reliability_pct": 100.0,
    "total_orders": 150,
    "is_healthy": true,
    "is_critical": false,
    "last_calculated": "2026-01-20T00:00:00Z"
  },
  "kpis": {
    "supplier_name": "Acme Manufacturing",
    "otif_rate": 94.5,
    "otif_trend_pct": 1.4,
    "lead_time_avg": 7.5,
    "lead_time_trend": -0.3,
    "inventory_turnover_ratio": 12.5,
    "inventory_trend_pct": 2.5,
    "stock_out_incidents": 2,
    "low_stock_items_count": 5,
    "orders_pending_count": 12,
    "orders_delayed_count": 1,
    "snapshot_date": "2026-01-20"
  },
  "critical_alerts": 2,
  "warning_alerts": 3,
  "info_alerts": 5,
  "total_alerts": 10,
  "risk_overview": {
    "supplier_name": "Acme Manufacturing",
    "supplier_risk_level": "medium",
    "supplier_risk_level_display": "Medium",
    "logistics_risk_level": "low",
    "logistics_risk_level_display": "Low",
    "demand_risk_level": "medium",
    "demand_risk_level_display": "Medium",
    "inventory_risk_level": "low",
    "inventory_risk_level_display": "Low",
    "overall_risk_score": 58.3,
    "overall_risk_level": "medium",
    "overall_risk_level_display": "Medium",
    "snapshot_date": "2026-01-20"
  }
}
```

---

## Common Response Status Codes

| Status | Meaning | Example |
|--------|---------|---------|
| 200 | Success | Data returned successfully |
| 201 | Created | Resource created successfully (POST) |
| 204 | No Content | Action completed (DELETE) |
| 400 | Bad Request | Invalid query parameters or malformed request |
| 401 | Unauthorized | Missing or invalid authentication token |
| 403 | Forbidden | User lacks permission to access resource |
| 404 | Not Found | Resource doesn't exist or no access |
| 500 | Server Error | Internal server error |

---

## Pagination

All list endpoints support pagination with the following query parameters:

| Parameter | Type | Default | Max |
|-----------|------|---------|-----|
| `page` | integer | 1 | N/A |
| `page_size` | integer | 20 | 100 |

**Example:**
```
GET /api/v1/supplier-scorecards/?page=2&page_size=50
```

**Response includes:**
```json
{
  "count": 450,
  "next": "http://api/v1/supplier-scorecards/?page=3&page_size=50",
  "previous": "http://api/v1/supplier-scorecards/?page=1&page_size=50",
  "results": [...]
}
```

---

## Filtering & Searching

### Filter Examples

**Get healthy suppliers only:**
```
GET /api/v1/supplier-scorecards/?health_status=healthy
```

**Get critical alerts for specific supplier:**
```
GET /api/v1/alerts/?severity=critical&supplier__name=Acme
```

**Get KPIs for specific date:**
```
GET /api/v1/kpis/?snapshot_date=2026-01-20
```

### Search Examples

**Search alerts by keyword:**
```
GET /api/v1/alerts/?search=delay
```

---

## Data Field Reference

### Health Status Values
- `healthy` - Score 80-100
- `monitor` - Score 60-79
- `critical` - Score 0-59

### Alert Status Values
- `active` - Alert triggered and unresolved
- `acknowledged` - Alert seen by user
- `resolved` - Manually resolved
- `auto_resolved` - Auto-resolved by system

### Alert Severity Values
- `critical` - Immediate action required
- `warning` - Should be addressed soon
- `info` - Informational only

### Alert Types
- `otif_violation` - On-time-in-full rate drops
- `quality_issue` - Quality performance drops
- `delivery_delay` - Shipment delayed
- `inventory_low` - Low stock levels
- `supplier_risk` - Supplier risk increased

### Risk Levels
- `low` - Low risk (0-30)
- `medium` - Medium risk (30-60)
- `high` - High risk (60-80)
- `critical` - Critical risk (80-100)

---

## Authentication

All endpoints require a valid JWT token. Include in request header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

To obtain a token, authenticate with the login endpoint (not documented here).

---

## Frontend Implementation Tips

1. **User-Based Filtering:** All endpoints automatically filter based on logged-in user
   - Admins see all data
   - Suppliers see only their own data
   - No need to add supplier filters manually

2. **Pagination:** Implement pagination for large datasets
   - Default page size is 20 records
   - Maximum page size is 100

3. **Real-Time Updates:** Recommend polling these endpoints every 1-5 minutes:
   - `/alerts/active/` - For active alerts
   - `/kpis/current/` - For latest KPIs
   - `/risk-categories/current/` - For current risk status

4. **Caching:** Consider caching:
   - Alert thresholds (rarely change)
   - Historical data (read-only)
   - Summary data (update every 5 minutes)

5. **Error Handling:** Always handle:
   - 404 errors (no data found)
   - 401 errors (authentication expired)
   - 500 errors (server issues)

---

## Example Frontend Implementation

### React/Vue Example - Get Current Scorecard

```javascript
// Fetch current supplier scorecard
async function getSupplierScorecard(token) {
  try {
    const response = await fetch(
      'https://api.example.com/api/v1/supplier-scorecards/current/',
      {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      throw new Error(`Error: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Failed to fetch scorecard:', error);
    return null;
  }
}

// Get active alerts
async function getActiveAlerts(token) {
  try {
    const response = await fetch(
      'https://api.example.com/api/v1/alerts/active/?page_size=50',
      {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    const data = await response.json();
    return data.results || [];
  } catch (error) {
    console.error('Failed to fetch alerts:', error);
    return [];
  }
}

// Acknowledge an alert
async function acknowledgeAlert(alertId, token) {
  try {
    const response = await fetch(
      `https://api.example.com/api/v1/alerts/${alertId}/acknowledge/`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Failed to acknowledge alert:', error);
    return null;
  }
}
```

---

**Last Updated:** January 20, 2026  
**API Version:** v1  
**Server:** Django REST Framework 4.2.15
