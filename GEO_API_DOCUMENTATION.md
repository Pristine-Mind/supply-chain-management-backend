# Geographic API Documentation

## Overview
This document covers two core geographic APIs for location tracking and product deliverability checking.

---

## 1. Create User Location

**Endpoint:** `POST /api/v1/geo/locations/`

**Description:** Record user's current geographic location with optional accuracy metadata.

**Authentication:** Required (Bearer Token)

### Request

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <token>
```

**Body:**
```json
{
    "latitude": 27.7172,
    "longitude": 85.3240,
    "accuracy_meters": 10,
    "session_id": "session_abc123"
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| latitude | float | Yes | User's latitude (-90 to 90) |
| longitude | float | Yes | User's longitude (-180 to 180) |
| accuracy_meters | integer | No | GPS accuracy in meters |
| session_id | string | No | Optional session identifier for tracking |

### Response

**Status:** `201 Created`

```json
{
    "id": 42,
    "user": 5,
    "latitude": 27.7172,
    "longitude": 85.3240,
    "accuracy_meters": 10,
    "session_id": "session_abc123",
    "created_at": "2026-01-21T10:30:45.123456Z"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| id | integer | Location snapshot ID |
| user | integer | User ID who created the snapshot |
| latitude | float | Stored latitude |
| longitude | float | Stored longitude |
| accuracy_meters | integer | GPS accuracy in meters |
| session_id | string | Session identifier if provided |
| created_at | datetime | Timestamp when created |

### Error Responses

**400 Bad Request** - Invalid coordinates or missing required fields
```json
{
    "latitude": ["Ensure this field is greater than or equal to -90."],
    "longitude": ["Ensure this field is less than or equal to 180."]
}
```

**401 Unauthorized** - Missing or invalid authentication token
```json
{
    "detail": "Authentication credentials were not provided."
}
```

### Examples

**cURL:**
```bash
curl -X POST http://localhost:8000/api/v1/geo/locations/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -d '{
    "latitude": 27.7172,
    "longitude": 85.3240,
    "accuracy_meters": 15,
    "session_id": "mobile_session_123"
  }'
```

**Python Requests:**
```python
import requests

headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json"
}

data = {
    "latitude": 27.7172,
    "longitude": 85.3240,
    "accuracy_meters": 10,
    "session_id": "session_abc123"
}

response = requests.post(
    "http://localhost:8000/api/v1/geo/locations/",
    json=data,
    headers=headers
)

print(response.json())
```

**JavaScript/Fetch:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/geo/locations/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_TOKEN'
    },
    body: JSON.stringify({
        latitude: 27.7172,
        longitude: 85.3240,
        accuracy_meters: 10,
        session_id: 'session_abc123'
    })
});

const data = await response.json();
console.log(data);
```

---

## 2. Check Product Deliverability

**Endpoint:** `POST /api/v1/geo/deliverability/check/`

**Description:** Check if a specific product can be delivered to a given location.

**Authentication:** Not required (AllowAny)

### Request

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
    "product_id": 123,
    "latitude": 27.7172,
    "longitude": 85.3240
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| product_id | integer | Yes | ID of MarketplaceProduct to check |
| latitude | float | Yes | Delivery location latitude (-90 to 90) |
| longitude | float | Yes | Delivery location longitude (-180 to 180) |

### Response

**Status:** `200 OK`

```json
{
    "is_deliverable": true,
    "reason": null,
    "estimated_days": 1,
    "shipping_cost": "0.00",
    "zone": "Kathmandu City"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| is_deliverable | boolean | Whether product can be delivered to location |
| reason | string or null | Reason if not deliverable (null if deliverable) |
| estimated_days | integer | Expected delivery time in days |
| shipping_cost | string | Shipping cost in currency (as string for precision) |
| zone | string | Geographic zone name for the location |

### Possible Reason Values

When `is_deliverable` is `false`, the `reason` field contains one of:

| Reason | Description |
|--------|-------------|
| "Beyond maximum delivery distance" | Product's max delivery distance exceeded |
| "Not available in your delivery zone" | Product restricted to specific zones |
| "Cannot determine your delivery zone" | Zone detection failed for location |

### Error Responses

**400 Bad Request** - Invalid coordinates or missing required fields
```json
{
    "detail": "Invalid coordinates"
}
```

**404 Not Found** - Product does not exist
```json
{
    "detail": "Not found."
}
```

### Examples

**cURL - Deliverable Product:**
```bash
curl -X POST http://localhost:8000/api/v1/geo/deliverability/check/ \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 123,
    "latitude": 27.7172,
    "longitude": 85.3240
  }'
```

**Response:**
```json
{
    "is_deliverable": true,
    "reason": null,
    "estimated_days": 1,
    "shipping_cost": "0.00",
    "zone": "Kathmandu City"
}
```

**cURL - Non-Deliverable Product:**
```bash
curl -X POST http://localhost:8000/api/v1/geo/deliverability/check/ \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 456,
    "latitude": 28.5355,
    "longitude": 84.1240
  }'
```

**Response:**
```json
{
    "is_deliverable": false,
    "reason": "Beyond maximum delivery distance",
    "estimated_days": 7,
    "shipping_cost": "300.00",
    "zone": "Extended Delivery (Nepal-wide)"
}
```

**Python Requests:**
```python
import requests

# Check product deliverability
product_id = 123
latitude = 27.7172
longitude = 85.3240

response = requests.post(
    "http://localhost:8000/api/v1/geo/deliverability/check/",
    json={
        "product_id": product_id,
        "latitude": latitude,
        "longitude": longitude
    }
)

if response.status_code == 200:
    data = response.json()
    if data['is_deliverable']:
        print(f"✓ Deliverable in {data['estimated_days']} days")
        print(f"  Shipping: Rs {data['shipping_cost']}")
        print(f"  Zone: {data['zone']}")
    else:
        print(f"✗ Not deliverable: {data['reason']}")
else:
    print(f"Error: {response.status_code}")
```

**JavaScript/Fetch:**
```javascript
async function checkDeliverability(productId, latitude, longitude) {
    const response = await fetch('http://localhost:8000/api/v1/geo/deliverability/check/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            product_id: productId,
            latitude: latitude,
            longitude: longitude
        })
    });

    const data = await response.json();
    
    if (data.is_deliverable) {
        console.log(`✓ Deliverable in ${data.estimated_days} days`);
        console.log(`Shipping: Rs ${data.shipping_cost}`);
    } else {
        console.log(`✗ Not deliverable: ${data.reason}`);
    }
    
    return data;
}

// Usage
checkDeliverability(123, 27.7172, 85.3240);
```

**React Component:**
```javascript
import { useState, useEffect } from 'react';

const DeliverabilityCheck = ({ productId, latitude, longitude }) => {
    const [deliverability, setDeliverability] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const checkDelivery = async () => {
            try {
                const response = await fetch(
                    'http://localhost:8000/api/v1/geo/deliverability/check/',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            product_id: productId,
                            latitude: latitude,
                            longitude: longitude
                        })
                    }
                );
                
                if (!response.ok) throw new Error('Failed to check deliverability');
                
                const data = await response.json();
                setDeliverability(data);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        checkDelivery();
    }, [productId, latitude, longitude]);

    if (loading) return <div>Checking deliverability...</div>;
    if (error) return <div>Error: {error}</div>;

    return (
        <div className="deliverability-info">
            {deliverability.is_deliverable ? (
                <div className="available">
                    <h3>✓ Available for delivery</h3>
                    <p>Zone: {deliverability.zone}</p>
                    <p>Estimated delivery: {deliverability.estimated_days} days</p>
                    <p>Shipping: Rs {deliverability.shipping_cost}</p>
                </div>
            ) : (
                <div className="unavailable">
                    <h3>✗ Not available</h3>
                    <p>Reason: {deliverability.reason}</p>
                </div>
            )}
        </div>
    );
};

export default DeliverabilityCheck;
```

---

## Rate Limiting & Quotas

| Endpoint | Rate Limit | Notes |
|----------|-----------|-------|
| POST /api/v1/geo/locations/ | 100 requests/hour | Per authenticated user |
| POST /api/v1/geo/deliverability/check/ | Unlimited | Public endpoint |

---

## Status Codes Reference

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Deliverability check successful |
| 201 | Created | Location snapshot created |
| 400 | Bad Request | Invalid coordinates or parameters |
| 401 | Unauthorized | Missing/invalid auth token (locations only) |
| 404 | Not Found | Product ID doesn't exist |
| 500 | Server Error | Unexpected server error |

---

## Best Practices

### Location Recording
- Track location changes at **30-60 second intervals** for optimal accuracy
- Use the `session_id` to group related location updates
- Include `accuracy_meters` from device GPS for quality metrics

### Deliverability Checking
- Cache results for **5-10 minutes** if location is static
- Call before showing checkout to verify current deliverability
- Use for filtering product search results
- Show shipping cost prominently to users

### Error Handling
```python
# Example error handling
try:
    response = requests.post(url, json=data, timeout=5)
    response.raise_for_status()
    result = response.json()
    
    if result['is_deliverable']:
        # Show product as available
        show_product(result)
    else:
        # Show reason and suggest alternatives
        show_error(result['reason'])
        
except requests.exceptions.RequestException as e:
    # Network/server error - retry or fallback
    logger.error(f"API error: {e}")
```

---

## Coordinate Format

All coordinates use **WGS84 (SRID 4326)** standard:

- **Latitude:** Range -90 to 90 (negative = South)
- **Longitude:** Range -180 to 180 (negative = West)

**Example - Kathmandu, Nepal:**
- Latitude: 27.7172
- Longitude: 85.3240

---

## Questions & Support

For API issues, check:
1. Coordinate validation (-90 to 90 for lat, -180 to 180 for lon)
2. Product ID exists in database
3. Authentication token is valid (locations endpoint)
4. Network connectivity and timeout settings
