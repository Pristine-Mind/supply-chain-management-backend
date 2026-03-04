# Business List API Documentation

## Overview
Fast and comprehensive API to list all businesses in Nepal with advanced filtering capabilities. This API specifically targets users with `business_owner` role and `distributor` business type, providing extensive search, filter, and location-based options.

## Endpoint
```
GET /api/v1/businesses/
```

## Authentication
- **Required**: Yes
- **Type**: Token Authentication
- **Header**: `Authorization: Token <your-token>`

## Features
- ✅ **Fast Performance**: Optimized queries with select_related to prevent N+1 issues
- ✅ **Advanced Filtering**: Multiple filter options for business type, location, verification status
- ✅ **Search Functionality**: Search across business names, user details, and phone numbers
- ✅ **Geographic Filtering**: Distance-based filtering using latitude/longitude coordinates
- ✅ **Sorting**: Sort by multiple fields including date, name, location
- ✅ **Pagination**: Built-in pagination for large result sets

## Query Parameters

### Business Filters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `business_type` | string | Filter by business type | `?business_type=distributor` |
| `b2b_verified` | boolean | Filter by B2B verification status | `?b2b_verified=true` |
| `has_marketplace_access` | boolean | Filter by marketplace access | `?has_marketplace_access=true` |

### Location Filters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `city` | integer | Filter by city ID | `?city=1` |
| `city_name` | string | Filter by city name (partial match) | `?city_name=kathmandu` |

### Geographic Distance Filters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `latitude` | float | Latitude for distance filtering | `?latitude=27.7172` |
| `longitude` | float | Longitude for distance filtering | `?longitude=85.3240` |
| `radius_km` | integer | Radius in kilometers | `?radius_km=25` |

**Note**: For geographic filtering, all three parameters (`latitude`, `longitude`, `radius_km`) must be provided together.

### User Status Filters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `is_active` | boolean | Filter by user active status | `?is_active=true` |
| `registered_after` | datetime | Businesses registered after date | `?registered_after=2024-01-01` |
| `registered_before` | datetime | Businesses registered before date | `?registered_before=2024-12-31` |

### Credit Limit Filters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `min_credit_limit` | number | Minimum credit limit | `?min_credit_limit=10000` |
| `max_credit_limit` | number | Maximum credit limit | `?max_credit_limit=100000` |

### Search & Ordering
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `search` | string | Search in business/user names, phone | `?search=grocery` |
| `ordering` | string | Order results by field | `?ordering=-user__date_joined` |

#### Available Ordering Fields
- `user__date_joined` (registration date)
- `user__first_name` / `user__last_name` (user names)
- `business_type` 
- `location__name` (city name)
- `b2b_verified`
- `credit_limit`
- `registered_business_name`

**Note**: Prefix with `-` for descending order (e.g., `-user__date_joined` for newest first).

## Response Format

### Success Response (200 OK)
```json
{
  "count": 150,
  "results": [
    {
      "username": "businessuser123",
      "first_name": "Ram",
      "last_name": "Sharma",
      "email": "ram@business.com",
      "full_name": "Ram Sharma",
      "date_joined": "2024-01-15T10:30:00Z",
      "is_active": true,
      "phone_number": "+977-9841234567",
      "business_type": "distributor",
      "registered_business_name": "Sharma Distributors Pvt Ltd",
      "shop_id": "123e4567-e89b-12d3-a456-426614174000",
      "has_access_to_marketplace": true,
      "role_name": "Business Owner",
      "role_code": "business_owner",
      "location_name": "Kathmandu",
      "latitude": 27.7172,
      "longitude": 85.3240,
      "b2b_verified": true,
      "credit_limit": "50000.00",
      "payment_terms_days": 30,
      "registration_certificate": "/media/certificates/reg_cert_123.pdf",
      "pan_certificate": "/media/certificates/pan_cert_123.pdf",
      "profile_image": "/media/profile/user_123.jpg"
    }
  ],
  "filters_applied": {
    "city_name": "kathmandu",
    "b2b_verified": "true"
  }
}
```

### Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

#### 400 Bad Request (Invalid Parameters)
```json
{
  "error": "Invalid filter parameters"
}
```

## Usage Examples

### 1. Get All Distributors
```bash
curl -H "Authorization: Token <your-token>" \
     "https://api.example.com/api/v1/businesses/"
```

### 2. Search for Businesses
```bash
curl -H "Authorization: Token <your-token>" \
     "https://api.example.com/api/v1/businesses/?search=grocery"
```

### 3. Filter by Location
```bash
curl -H "Authorization: Token <your-token>" \
     "https://api.example.com/api/v1/businesses/?city_name=kathmandu&b2b_verified=true"
```

### 4. Geographic Proximity Search
```bash
curl -H "Authorization: Token <your-token>" \
     "https://api.example.com/api/v1/businesses/?latitude=27.7172&longitude=85.3240&radius_km=15"
```

### 5. Filter by Credit Limit Range
```bash
curl -H "Authorization: Token <your-token>" \
     "https://api.example.com/api/v1/businesses/?min_credit_limit=25000&max_credit_limit=100000"
```

### 6. Complex Filtering with Ordering
```bash
curl -H "Authorization: Token <your-token>" \
     "https://api.example.com/api/v1/businesses/?city_name=kathmandu&b2b_verified=true&ordering=-credit_limit"
```

## Performance Optimizations

### Database Query Optimizations
- **select_related()**: Prevents N+1 queries for user, role, and location data
- **Indexing**: Database indexes on commonly filtered fields
- **Efficient Filtering**: Optimized queryset filtering at database level

### Response Optimizations
- **Pagination**: Automatic pagination for large datasets
- **Field Selection**: Only essential fields included in response
- **Caching Ready**: Response structure optimized for caching layer

## Rate Limiting
- **Default**: 100 requests per minute per authenticated user
- **Burst**: 200 requests per 5 minutes
- **Headers**: Rate limit info in response headers

## Testing

Run the comprehensive test suite:
```bash
python manage.py test user.test_business_api
```

Tests include:
- Authentication requirements
- Filtering functionality
- Search capabilities
- Geographic filtering
- Response format validation
- Performance benchmarks

## Notes for Developers

### Adding New Filters
To add new filters, update the `BusinessFilter` class in `user/filters.py`:

```python
new_field = django_filters.CharFilter(
    field_name='model_field_name',
    lookup_expr='icontains',
    help_text="Description of the filter"
)
```

### Performance Monitoring
Monitor these metrics:
- **Query Count**: Should remain constant regardless of result size
- **Response Time**: Target < 200ms for typical queries
- **Memory Usage**: Monitor for large result sets

### Geographic Filtering Accuracy
Current implementation uses simplified distance calculation suitable for Nepal's geographic area. For high-precision requirements, consider upgrading to PostGIS with proper distance calculations.

## Support
For issues or questions about this API, contact the development team or check the project documentation.