# User-Based QuerySet Filtering Implementation

## Overview
Implemented row-level security across all risk management ViewSets to ensure data isolation based on authenticated user identity.

## Implementation Details

### Core Filtering Logic
All ViewSets now implement `get_queryset()` method with the following access control pattern:

```python
def get_queryset(self):
    """Filter based on user type."""
    user = self.request.user
    
    # Admins and superusers see all records
    if user.is_staff or user.is_superuser:
        return ModelName.objects.all()
    
    # Suppliers see only their own data
    if hasattr(user, "producer"):
        return ModelName.objects.filter(supplier=user.producer)
    
    # Other authenticated users see nothing
    return ModelName.objects.none()
```

### ViewSets Updated

#### 1. **SupplierScorecardViewSet**
- **Lines:** 53-65
- **Access Control:**
  - Admins: See all supplier scorecards
  - Suppliers: See only their own scorecard (via `supplier=user.producer`)
  - Others: Empty queryset
- **Impact:** Scorecard list, detail, current(), history(), and comparison() actions all respect user filtering

#### 2. **SupplyChainKPIViewSet**
- **Lines:** 136-148
- **Access Control:**
  - Admins: See all KPI snapshots
  - Suppliers: See only their own KPI data
  - Others: Empty queryset
- **Impact:** KPI list, current(), and trends() actions are now user-filtered at QuerySet level

#### 3. **SupplyChainAlertViewSet**
- **Lines:** 215-225
- **Access Control:**
  - Admins: See all alerts
  - Suppliers: See only alerts for their supplier
  - Others: Empty queryset
- **Note:** Already had `get_queryset()` implemented; verified it follows the pattern

#### 4. **AlertThresholdViewSet**
- **Lines:** 316-324
- **Access Control:**
  - All authenticated users: See all alert thresholds (system-wide configuration)
- **Note:** Thresholds are system-level configuration, not user-specific; all users need access for proper alert functioning

#### 5. **RiskCategoryViewSet**
- **Lines:** 341-354
- **Access Control:**
  - Admins: See all risk assessments (including global risk)
  - Suppliers: See only their own risk categories
  - Others: Empty queryset
- **Impact:** Risk category list, current(), and drill_downs() actions respect user filtering

## Data Isolation Model

### User Types & Access Patterns

| User Type | Supplier Data | Alert Thresholds | System Data |
|-----------|--------------|-----------------|-------------|
| Superuser/Staff | ✅ All records | ✅ All records | ✅ All records |
| Supplier (has producer) | ✅ Own data only | ✅ View all | ❌ None |
| Other Authenticated | ❌ None | ✅ View all | ❌ None |
| Unauthenticated | ❌ No access (via permission) | ❌ No access | ❌ No access |

### User-Producer Relationship
- Suppliers are linked to the system via `user.producer` attribute
- This attribute points to their `Producer` (supplier) record
- Admin users do not have this attribute (they're not producers)

## Security Benefits

1. **Multi-Tenant Isolation:** Each supplier only sees their own data
2. **ORM-Level Enforcement:** Filtering happens at database query level, not in serializers
3. **Consistent Access Control:** Same pattern across all ViewSets for maintainability
4. **Backwards Compatible:** Staff/superuser access unchanged; all historical data visible
5. **Scalable:** Adding new ViewSets uses the same proven pattern

## Testing Recommendations

### Test Scenarios

```python
# Admin user - should see all
admin_user = User.objects.create_superuser(...)
# GET /api/v1/scorecards/ → Returns all scorecards

# Supplier A
supplier_a_user = User.objects.create_user(producer=supplier_a)
# GET /api/v1/scorecards/ → Returns only supplier_a scorecard

# Supplier B
supplier_b_user = User.objects.create_user(producer=supplier_b)
# GET /api/v1/scorecards/ → Returns only supplier_b scorecard

# Regular user (no producer)
regular_user = User.objects.create_user()
# GET /api/v1/scorecards/ → Returns empty list (HTTP 200, but no data)
```

### Audit Trail
All API requests respect this filtering automatically. No manual data validation needed in views.

## Implementation Status

✅ **COMPLETE**
- All 5 ViewSets have `get_queryset()` methods
- Access control pattern applied consistently
- Supplier filtering implemented for all supplier-specific models
- Admin override implemented for oversight and management
- AlertThreshold follows system-wide access (no supplier filtering needed)

## Migration Notes

- No database migrations required
- No changes to models
- No changes to serializers
- Filters applied transparently at QuerySet level
- Existing API contracts unchanged; same endpoints, filtered results
- Staff users continue to see all data as before

## Future Enhancements

1. **Audit Logging:** Log which users accessed which data
2. **Fine-Grained Permissions:** Support product-level or region-level filtering
3. **Cross-Tenant Analytics:** Allow admins to compare filtered data across suppliers
4. **Access Requests:** Implement workflow for suppliers to request admin data access
