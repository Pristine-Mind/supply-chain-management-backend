# GEO_MODEL_FIELDS_GUIDE.md
## Missing Model Fields & Features Analysis

This document outlines all the model fields and features referenced in GEO_PRACTICAL_EXAMPLES.md that need to be added to your existing models.

---

## Summary of Missing Features

### 1. Producer Model Fields (NEW)
- `service_radius_km` - Maximum delivery distance from producer location

### 2. MarketplaceProduct Model Fields (NEW)
- `enable_geo_restrictions` - Enable/disable geo-based restrictions
- `max_delivery_distance_km` - Maximum delivery distance
- `available_delivery_zones` - JSONField list of available zone IDs
- `seller_geo_point` - PointField for seller location
- `seller_location_lat` - Float field for latitude
- `seller_location_lon` - Float field for longitude
- `sale_restricted_to_regions` - JSONField list of SaleRegion IDs

### 3. Product Model Relationship (VERIFY)
- Check if `product__stock__gt=0` works (verify stock field exists)
- Check if `product__category__name` works (verify category relationship)

### 4. New Models to Create (IF NEEDED)
- `UserLocationCache` - Quick-access user location cache
- `DeliveryPartner` - Delivery partner model with zones
- `Delivery` - Order delivery tracking model

---

## Detailed Field Specifications

### Producer Model Additions

```python
# Add to producer/models.py

class Producer(models.Model):
    # ... existing fields ...
    
    service_radius_km = models.PositiveIntegerField(
        default=500,
        verbose_name=_("Service Radius (km)"),
        help_text=_("Maximum distance from seller location for delivery"),
    )
```

**Purpose:** Define seller's delivery capability range
**Type:** PositiveIntegerField
**Default:** 500 km (nationwide)
**Used in:** Product filtering, deliverability checks

---

### MarketplaceProduct Model Additions

#### 1. Geo Restrictions Enable/Disable
```python
enable_geo_restrictions = models.BooleanField(
    default=False,
    verbose_name=_("Enable Geo Restrictions"),
    help_text=_("Restrict sales to specific geographic zones"),
)
```

**Purpose:** Flag to enable geographic restrictions
**Type:** BooleanField
**Default:** False (no restrictions)

#### 2. Maximum Delivery Distance
```python
max_delivery_distance_km = models.PositiveIntegerField(
    null=True,
    blank=True,
    verbose_name=_("Max Delivery Distance (km)"),
    help_text=_("Maximum distance from seller location"),
)
```

**Purpose:** Set max delivery distance for product
**Type:** PositiveIntegerField
**Default:** None (inherited from seller)

#### 3. Available Delivery Zones
```python
available_delivery_zones = models.JSONField(
    default=list,
    blank=True,
    verbose_name=_("Available Delivery Zones"),
    help_text=_("List of GeographicZone IDs where product is deliverable"),
)
```

**Purpose:** Restrict product to specific zones
**Type:** JSONField
**Format:** [1, 3, 5] (list of zone IDs)
**Example:**
```python
product.available_delivery_zones = [
    zone_kathmandu.id,
    zone_pokhara.id,
]
```

#### 4. Seller Geographic Point
```python
seller_geo_point = models.PointField(
    null=True,
    blank=True,
    srid=4326,
    verbose_name=_("Seller Geographic Point"),
    help_text=_("Auto-synced from producer location"),
)
```

**Purpose:** GIS point for spatial queries
**Type:** PointField (GIS)
**Auto-updated:** Yes, synced from Producer.location on save
**Used in:** Distance calculations, spatial filters

#### 5. Seller Location Latitude
```python
seller_location_lat = models.FloatField(
    null=True,
    blank=True,
    verbose_name=_("Seller Location Latitude"),
    help_text=_("Denormalized for easier access"),
)
```

**Purpose:** Denormalized latitude for easier queries
**Type:** FloatField
**Range:** -90 to 90
**Auto-updated:** Yes

#### 6. Seller Location Longitude
```python
seller_location_lon = models.FloatField(
    null=True,
    blank=True,
    verbose_name=_("Seller Location Longitude"),
    help_text=_("Denormalized for easier access"),
)
```

**Purpose:** Denormalized longitude for easier queries
**Type:** FloatField
**Range:** -180 to 180
**Auto-updated:** Yes

#### 7. Sale Restricted to Regions
```python
sale_restricted_to_regions = models.JSONField(
    default=list,
    blank=True,
    verbose_name=_("Sale Restricted to Regions"),
    help_text=_("List of SaleRegion IDs with restrictions"),
)
```

**Purpose:** Link to SaleRegion models with restrictions
**Type:** JSONField
**Format:** [1, 2] (list of SaleRegion IDs)
**Example:**
```python
product.sale_restricted_to_regions = [luxury_region.id]
```

---

## Implementation Order

### Step 1: Add Fields to Producer Model
**File:** `producer/models.py`

```python
service_radius_km = models.PositiveIntegerField(
    default=500,
    verbose_name=_("Service Radius (km)"),
)
```

### Step 2: Add Fields to MarketplaceProduct Model
**File:** `producer/models.py`

Add all 7 fields listed above in the MarketplaceProduct class.

### Step 3: Update save() Method
**File:** `producer/models.py`

Auto-sync seller location fields:

```python
def save(self, *args, **kwargs):
    # Sync seller geo point from producer
    if self.product.producer and self.product.producer.location:
        self.seller_geo_point = self.product.producer.location
        self.seller_location_lat = self.product.producer.location.y
        self.seller_location_lon = self.product.producer.location.x
    
    super().save(*args, **kwargs)
```

### Step 4: Create Migrations
```bash
python manage.py makemigrations producer
python manage.py migrate producer
```

---

## Field Validation & Constraints

### Latitude Validation
```python
from django.core.validators import MinValueValidator, MaxValueValidator

seller_location_lat = models.FloatField(
    null=True,
    blank=True,
    validators=[
        MinValueValidator(-90),
        MaxValueValidator(90),
    ],
)
```

### Longitude Validation
```python
seller_location_lon = models.FloatField(
    null=True,
    blank=True,
    validators=[
        MinValueValidator(-180),
        MaxValueValidator(180),
    ],
)
```

### Available Zones Validation
```python
def clean(self):
    """Validate zone IDs exist"""
    if self.available_delivery_zones:
        from geo.models import GeographicZone
        invalid_ids = [
            zid for zid in self.available_delivery_zones
            if not GeographicZone.objects.filter(id=zid).exists()
        ]
        if invalid_ids:
            raise ValidationError(
                f"Invalid zone IDs: {invalid_ids}"
            )
```

---

## Optional: Additional Models

### UserLocationCache (Optional but Recommended)
```python
# Optional: Quick-access location cache
class UserLocationCache(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    latitude = models.FloatField()
    longitude = models.FloatField()
    geo_point = models.PointField(srid=4326)
    zone = models.ForeignKey(GeographicZone, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Location Cache"
        indexes = [
            GistIndex(fields=["geo_point"]),
        ]
```

**Purpose:** Fast access to latest user location
**Benefits:** No need to query snapshots
**Trade-off:** Extra table, but faster queries

### DeliveryPartner (Optional but Recommended)
```python
# Optional: For delivery partner assignment
class DeliveryPartner(models.Model):
    name = models.CharField(max_length=100)
    zones = models.ManyToManyField(GeographicZone)
    current_load = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Delivery Partner"
```

**Purpose:** Assign delivery partners by zone
**Benefits:** Load balancing, zone coverage
**Used in:** Delivery assignment logic

---

## Migration Strategy

### Approach 1: Add All at Once (Recommended)
1. Add all fields to both models
2. Create single migration
3. Run migration
4. Update admin to show new fields
5. No data loss, backward compatible

### Approach 2: Add Incrementally
1. First iteration: Add Producer.service_radius_km
2. Second iteration: Add MarketplaceProduct geo fields
3. Each creates separate migration
4. Better for staged rollout

### Migration File Preview
```python
# auto-generated migrations

class Migration(migrations.Migration):
    dependencies = [
        ('producer', '0001_previous'),
    ]

    operations = [
        # Producer fields
        migrations.AddField(
            model_name='producer',
            name='service_radius_km',
            field=models.PositiveIntegerField(default=500),
        ),
        
        # MarketplaceProduct fields
        migrations.AddField(
            model_name='marketplaceproduct',
            name='enable_geo_restrictions',
            field=models.BooleanField(default=False),
        ),
        
        # ... more fields ...
    ]
```

---

## Admin Interface Updates

### Producer Admin
```python
# producer/admin.py

class ProducerAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'contact', 'email', 'address'),
        }),
        ('Geographic Information', {
            'fields': ('location', 'service_radius_km'),
            'classes': ('collapse',),
        }),
    )
```

### MarketplaceProduct Admin
```python
# producer/admin.py

class MarketplaceProductAdmin(admin.ModelAdmin):
    fieldsets = (
        # ... existing ...
        ('Geographic Restrictions', {
            'fields': (
                'enable_geo_restrictions',
                'max_delivery_distance_km',
                'available_delivery_zones',
                'sale_restricted_to_regions',
            ),
            'classes': ('collapse',),
            'description': 'Configure geographic-based sales restrictions',
        }),
        ('Seller Location (Auto)', {
            'fields': (
                'seller_geo_point',
                'seller_location_lat',
                'seller_location_lon',
            ),
            'classes': ('collapse',),
            'description': 'Auto-synced from producer location',
        }),
    )
    
    readonly_fields = [
        'seller_geo_point',
        'seller_location_lat',
        'seller_location_lon',
    ]
```

---

## Testing Checklist

After adding fields:

- [ ] Migrations create without errors
- [ ] Fields show in admin interface
- [ ] seller_geo_point auto-syncs on save
- [ ] Available zones validation works
- [ ] GIS queries use new fields
- [ ] Distance calculations work
- [ ] Zone detection works
- [ ] Product filtering by zone works
- [ ] Backward compatible (old products still work)

---

## Code Examples Using New Fields

### Example 1: Check Deliverability
```python
from geo.services import GeoProductFilterService

service = GeoProductFilterService()
can_deliver, reason = service.can_deliver_to_location(
    product,
    latitude=27.7172,
    longitude=85.3240,
    seller_latitude=product.seller_location_lat,
    seller_longitude=product.seller_location_lon,
)
```

### Example 2: Filter by Zone
```python
from django.db.models import Q

products = MarketplaceProduct.objects.filter(
    Q(available_delivery_zones__contains=[zone.id]) |
    Q(enable_geo_restrictions=False),
    is_available=True,
)
```

### Example 3: Get Products Within Distance
```python
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models import Distance

point = Point(85.3240, 27.7172, srid=4326)
products = MarketplaceProduct.objects.filter(
    seller_geo_point__distance_lte=(point, 'km', 50),
    is_available=True,
).order_by('seller_geo_point__distance')
```

---

## Backward Compatibility

All new fields are:
- `null=True, blank=True` (optional)
- Have sensible defaults
- Don't affect existing queries
- Backward compatible

**No data migration needed.**

---

## Performance Considerations

### Indexes Needed
```python
# In model Meta class
class Meta:
    indexes = [
        GistIndex(fields=['seller_geo_point']),
    ]
```

### Database Queries Optimized
- Use `seller_geo_point` for distance queries (GIS optimized)
- Use `seller_location_lat/lon` for simple comparisons
- Cache zone lists in available_delivery_zones

### Query Optimization
```python
# Good - uses GIS index
products = MarketplaceProduct.objects.filter(
    seller_geo_point__distance_lte=(point, Distance(km=50))
)

# Acceptable - no index but simple
products = MarketplaceProduct.objects.filter(
    seller_location_lat__range=(min_lat, max_lat),
    seller_location_lon__range=(min_lon, max_lon),
)
```

---

## Next Steps

1. ✓ Review this guide
2. Add Producer fields (2 minutes)
3. Add MarketplaceProduct fields (10 minutes)
4. Update save() method (5 minutes)
5. Create migrations (2 minutes)
6. Run migrations (1 minute)
7. Update admin (10 minutes)
8. Test endpoints (10 minutes)

**Total Time:** ~40 minutes

---

**Status:** Ready to implement
**Priority:** HIGH (Blocks GEO_PRACTICAL_EXAMPLES functionality)
**Complexity:** LOW (Just field additions)
