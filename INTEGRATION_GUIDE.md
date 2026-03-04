# INTEGRATION_GUIDE.md
## Geo App Integration Guide

This guide explains how to integrate the new `geo` app with the existing supply-chain-management backend.

### 1. Create the Geo App

The app structure has already been set up with:
```
geo/
├── __init__.py
├── models.py              # GeographicZone, SaleRegion, UserLocationSnapshot
├── services.py            # GeoLocationService, GeoProductFilterService, GeoAnalyticsService
├── views.py               # Geographic endpoints
├── serializers.py         # Request/response serializers
├── filters.py             # django_filters integration
├── admin.py               # Django admin configuration
├── apps.py                # App configuration
├── signals.py             # Signal handlers
├── urls.py                # URL routing
├── management/
│   └── commands/
│       └── init_geographic_zones.py  # Initialize zones
└── migrations/            # (Auto-generated)
```

### 2. Update Django Settings

Add `geo` to `INSTALLED_APPS` in [main/settings.py](main/settings.py):

```python
INSTALLED_APPS = [
    # ... existing apps ...
    'django.contrib.gis',  # GIS support (should already exist)
    'geo',  # Geographic location features
    # ... rest of apps ...
]
```

### 3. Update Main URLs

Include geo URLs in [main/urls.py](main/urls.py):

```python
urlpatterns = [
    # ... existing patterns ...
    
    # Geographic endpoints
    path('api/geo/', include('geo.urls', namespace='geo')),
    
    # ... rest of patterns ...
]
```

### 4. Update Producer Models

Add geo-restriction fields to `MarketplaceProduct` in [producer/models.py](producer/models.py):

```python
from django.contrib.gis.db import models as gis_models
from django.db.models import JSONField

class MarketplaceProduct(models.Model):
    # ... existing fields ...
    
    # Geographic restriction fields
    enable_geo_restrictions = models.BooleanField(
        default=False,
        verbose_name=_("Enable Geo Restrictions"),
        help_text=_("Restrict sales to specific geographic zones"),
    )
    
    max_delivery_distance_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max Delivery Distance (km)"),
        help_text=_("Maximum distance from seller location"),
    )
    
    available_delivery_zones = JSONField(
        default=list,
        blank=True,
        verbose_name=_("Available Delivery Zones"),
        help_text=_("List of zone IDs where this product can be delivered"),
    )
    
    seller_geo_point = gis_models.PointField(
        null=True,
        blank=True,
        srid=4326,
        verbose_name=_("Seller Geographic Point"),
        help_text=_("Auto-synced from producer location"),
    )
```

**Note:** For easier migration, you can also use:
```python
seller_location_lat = models.FloatField(null=True, blank=True)
seller_location_lon = models.FloatField(null=True, blank=True)
```

### 5. Update Market Filters

Integrate geo filtering with existing filters in [market/filters.py](market/filters.py):

```python
from geo.filters import GeoProductFilter

class ProductFilter(GeoProductFilter):
    """Product filter with geographic capabilities"""
    
    # Inherit all geo-spatial fields from GeoProductFilter
    # Add additional filters as needed:
    
    category = django_filters.ModelChoiceFilter(
        field_name='category',
        queryset=Category.objects.all(),
    )
    
    min_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='gte'
    )
    
    max_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='lte'
    )
    
    class Meta:
        model = MarketplaceProduct
        fields = [
            'latitude',
            'longitude',
            'max_delivery_distance_km',
            'zone_id',
            'category',
            'min_price',
            'max_price',
        ]
```

### 6. Update Market Views

Integrate geo services in [market/views.py](market/views.py):

```python
from rest_framework.response import Response
from geo.services import GeoProductFilterService

class MarketplaceProductViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceProduct.objects.filter(is_active=True)
    serializer_class = MarketplaceProductSerializer
    filterset_class = ProductFilter  # Now includes geo filters
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    
    def get_queryset(self):
        """Filter products by user location if provided"""
        queryset = super().get_queryset()
        
        # Check if location filters are in request
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        
        if latitude and longitude:
            try:
                lat = float(latitude)
                lon = float(longitude)
                
                # Use geo service to filter deliverable products
                service = GeoProductFilterService()
                queryset = service.get_deliverable_products(
                    user=self.request.user,
                    latitude=lat,
                    longitude=lon,
                    queryset=queryset
                )
            except (ValueError, TypeError):
                pass  # Invalid coordinates, return all products
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def check_deliverability(self, request, pk=None):
        """Check if product can be delivered to location"""
        product = self.get_object()
        
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not latitude or not longitude:
            return Response(
                {'error': 'latitude and longitude required'},
                status=400
            )
        
        service = GeoProductFilterService()
        can_deliver, reason = service.can_deliver_to_location(
            product,
            float(latitude),
            float(longitude),
            seller_latitude=product.producer.location.y if product.producer.location else None,
            seller_longitude=product.producer.location.x if product.producer.location else None,
        )
        
        return Response({
            'product_id': product.id,
            'is_deliverable': can_deliver,
            'reason': reason,
        })
```

### 7. Create and Run Migrations

```bash
# Create migrations for the geo app
python manage.py makemigrations geo

# Create migrations for producer model updates
python manage.py makemigrations producer

# Run migrations
python manage.py migrate
```

### 8. Initialize Geographic Zones

```bash
# Initialize default zones for Nepal
python manage.py init_geographic_zones

# Clear and reinitialize (if needed)
python manage.py init_geographic_zones --clear
```

### 9. Update API Documentation

Add these endpoints to your API documentation:

#### Geographic Zones
- `GET /api/geo/zones/` - List all active zones
- `GET /api/geo/zones/{id}/` - Get zone details
- `POST /api/geo/zones/nearby/` - Get zones near coordinates
- `POST /api/geo/zones/detect-zone/` - Detect user's current zone

#### User Locations
- `POST /api/geo/locations/` - Record user location
- `GET /api/geo/locations/` - Get user's location history
- `POST /api/geo/locations/batch/` - Batch location updates

#### Product Deliverability
- `POST /api/geo/deliverability/check/` - Check if product is deliverable
- `POST /api/geo/deliverability/estimate/` - Get delivery estimate
- `POST /api/geo/deliverability/filter-products/` - Get deliverable products

### 10. Frontend Integration

#### 1. Get User Location (Browser Geolocation API)

```javascript
// Get user's current location
function getUserLocation() {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      position => {
        const { latitude, longitude } = position.coords;
        
        // Send to backend
        fetch('/api/geo/locations/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            latitude,
            longitude,
            accuracy_meters: position.coords.accuracy,
            session_id: getCurrentSessionId()
          })
        });
      },
      error => console.error('Geolocation error:', error)
    );
  }
}
```

#### 2. Filter Products by Location

```javascript
// Fetch products available at user location
async function getDeliverableProducts(latitude, longitude) {
  const response = await fetch(
    `/api/geo/deliverability/filter-products/?latitude=${latitude}&longitude=${longitude}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  return response.json();
}
```

#### 3. Check Product Deliverability

```javascript
// Check if specific product can be delivered
async function checkDeliverability(productId, latitude, longitude) {
  const response = await fetch('/api/geo/deliverability/check/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      product_id: productId,
      latitude,
      longitude
    })
  });
  return response.json();
}
```

### 11. Testing

Create tests in `geo/tests.py`:

```python
from django.test import TestCase
from django.contrib.auth.models import User
from geo.models import GeographicZone
from geo.services import GeoLocationService

class GeoLocationServiceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass')
        self.zone = GeographicZone.objects.create(
            name='Test Zone',
            tier='tier1',
            center_latitude=27.7172,
            center_longitude=85.3240,
            radius_km=15,
        )
    
    def test_zone_detection(self):
        service = GeoLocationService()
        zone = service.get_user_zone(
            self.user,
            27.7172,  # Same as zone center
            85.3240
        )
        self.assertEqual(zone.id, self.zone.id)
```

### 12. Performance Optimization

#### Enable GIS Indexes
Make sure PostGIS indexes are created:
```sql
CREATE INDEX idx_geo_zone_geometry ON geo_geographiczone USING GIST(geometry);
CREATE INDEX idx_user_location_snapshot ON geo_userlocationssnapshot USING GIST(geo_point);
```

#### Caching Strategy
Location snapshots are cached for 1 hour:
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

### 13. Common Use Cases

#### 1. Restrict Product Sales to Specific Zones

```python
from geo.models import GeographicZone

# In admin, set these fields:
product.enable_geo_restrictions = True
product.available_delivery_zones = [
    zone.id for zone in GeographicZone.objects.filter(tier__in=['tier1', 'tier2'])
]
product.save()
```

#### 2. Calculate Delivery Cost Dynamically

```python
service = GeoProductFilterService()
estimate = service.get_delivery_estimate(
    product,
    user_latitude=27.7172,
    user_longitude=85.3240,
    seller_latitude=producer.location.y,
    seller_longitude=producer.location.x
)
# Use estimate['shipping_cost'] in order
```

#### 3. Analyze Geographic Sales Patterns

```python
from geo.services import GeoAnalyticsService

service = GeoAnalyticsService()
popular_zones = service.get_popular_zones(limit=10)
coverage_percent = service.get_coverage_percentage()
```

### 14. Troubleshooting

#### PostGIS Not Enabled
```bash
# Enable PostGIS extension
psql -d your_database -c "CREATE EXTENSION postgis;"
```

#### Invalid Coordinates
Make sure coordinates are in WGS 84 format:
- Latitude: -90 to 90
- Longitude: -180 to 180

#### Zone Detection Not Working
Check that:
1. Zone has either `geometry` (polygon) or `center_latitude/longitude/radius_km`
2. Zone `is_active = True`
3. Coordinates are valid

### 15. Next Steps

1. **Run migrations** for geo and producer models
2. **Initialize zones** using the management command
3. **Update market filters** to include GeoProductFilter
4. **Update market views** to use GeoProductFilterService
5. **Test endpoints** using provided serializers
6. **Integrate frontend** with geolocation API
7. **Monitor performance** using Django admin analytics

For more details, see [GEO_SPATIAL_APP_ARCHITECTURE.md](GEO_SPATIAL_APP_ARCHITECTURE.md) and [GEO_PRACTICAL_EXAMPLES.md](GEO_PRACTICAL_EXAMPLES.md).
