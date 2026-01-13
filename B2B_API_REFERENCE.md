# B2B Pricing System - API Reference

## Base URL
All API endpoints are prefixed with: `/api/v1/`

## Authentication
All B2B endpoints require authentication. Include the following header:
```
Authorization: Bearer <your-token>
```

## Content Type
All requests should include:
```
Content-Type: application/json
```

---

## Product B2B Pricing APIs

### 1. Get B2B Pricing for Product

**Endpoint:** `GET /producer/products/{product_id}/b2b-pricing/`

**Description:** Retrieves B2B pricing information for a specific product based on the authenticated user's business type and requested quantity.

**Parameters:**
- `product_id` (path): Integer - Product ID
- `quantity` (query, optional): Integer - Quantity for price calculation (default: 1)

**Request Example:**
```bash
GET /api/v1/producer/products/123/b2b-pricing/?quantity=50
Authorization: Bearer your-token-here
```

**Response Format:**
```json
{
    "has_b2b_pricing": true,
    "b2b_price": "85.00",
    "regular_price": "100.00", 
    "discount_percentage": "15.00",
    "min_quantity": 10,
    "your_customer_type": "distributor",
    "applicable_tiers": [
        {
            "customer_type": "distributor",
            "min_quantity": 10,
            "max_quantity": 99,
            "price_per_unit": "85.00",
            "discount_percentage": "15.00"
        },
        {
            "customer_type": "distributor", 
            "min_quantity": 100,
            "max_quantity": null,
            "price_per_unit": "75.00",
            "discount_percentage": "25.00"
        }
    ]
}
```

**Response Fields:**
- `has_b2b_pricing`: Boolean indicating if B2B pricing is available
- `b2b_price`: Effective B2B price for requested quantity
- `regular_price`: Standard consumer price
- `discount_percentage`: Percentage discount from regular price
- `min_quantity`: Minimum quantity required for B2B pricing
- `your_customer_type`: User's business classification
- `applicable_tiers`: Array of available price tiers

**Error Responses:**
- `401 Unauthorized`: Not authenticated
- `403 Forbidden`: Not a verified business
- `404 Not Found`: Product not found
- `400 Bad Request`: Invalid quantity parameter

---

### 2. Calculate Order Pricing

**Endpoint:** `POST /producer/calculate-order-pricing/`

**Description:** Calculates total pricing for multiple products with B2B discounts applied.

**Request Body:**
```json
{
    "items": [
        {
            "product_id": 123,
            "quantity": 50
        },
        {
            "product_id": 124,
            "quantity": 25
        }
    ],
    "apply_credit": false
}
```

**Request Fields:**
- `items`: Array of order items
  - `product_id`: Integer - Product identifier
  - `quantity`: Integer - Quantity to order
- `apply_credit`: Boolean - Whether to apply available credit (default: false)

**Response Format:**
```json
{
    "success": true,
    "total_amount": "6750.00",
    "total_discount": "1250.00",
    "credit_applied": "0.00",
    "final_amount": "6750.00",
    "items": [
        {
            "product_id": 123,
            "product_name": "Sample Product A",
            "quantity": 50,
            "unit_price": "85.00",
            "regular_unit_price": "100.00",
            "total_price": "4250.00",
            "discount_applied": "15.00",
            "tier_used": {
                "customer_type": "distributor",
                "min_quantity": 10,
                "price_per_unit": "85.00"
            }
        },
        {
            "product_id": 124,
            "product_name": "Sample Product B",
            "quantity": 25,
            "unit_price": "100.00",
            "regular_unit_price": "100.00",
            "total_price": "2500.00",
            "discount_applied": "0.00",
            "tier_used": null
        }
    ],
    "is_b2b_pricing": true,
    "payment_terms": {
        "days": 30,
        "due_date": "2025-01-01"
    }
}
```

**Error Responses:**
- `401 Unauthorized`: Not authenticated
- `400 Bad Request`: Invalid product IDs or quantities
- `403 Forbidden`: Not eligible for B2B pricing

---

## Credit Management APIs

### 3. Get Credit Information

**Endpoint:** `GET /user/b2b-credit/`

**Description:** Retrieves current credit information for the authenticated business user.

**Response Format:**
```json
{
    "credit_limit": "10000.00",
    "available_credit": "7500.00", 
    "used_credit": "2500.00",
    "payment_terms_days": 30,
    "is_business_verified": true,
    "business_type": "distributor",
    "outstanding_orders": [
        {
            "order_id": 456,
            "amount": "1500.00",
            "due_date": "2025-01-15",
            "days_overdue": 0
        }
    ],
    "credit_utilization_percentage": "25.00"
}
```

**Response Fields:**
- `credit_limit`: Maximum credit available
- `available_credit`: Current available credit
- `used_credit`: Currently used credit amount
- `payment_terms_days`: Default payment terms
- `outstanding_orders`: Array of orders with outstanding balances
- `credit_utilization_percentage`: Percentage of credit limit used

---

### 4. Apply Credit to Order

**Endpoint:** `POST /user/b2b-credit/apply/`

**Description:** Applies available credit to a specific order.

**Request Body:**
```json
{
    "order_id": 789,
    "credit_amount": "1000.00"
}
```

**Response Format:**
```json
{
    "success": true,
    "message": "Credit applied successfully",
    "order_id": 789,
    "credit_applied": "1000.00",
    "remaining_credit": "6500.00",
    "order_balance": "3250.00",
    "order_status": "partially_paid"
}
```

**Error Responses:**
- `400 Bad Request`: Insufficient credit or invalid amount
- `404 Not Found`: Order not found
- `403 Forbidden`: Not authorized to modify this order

---

### 5. Update Credit Limit (Admin Only)

**Endpoint:** `POST /user/b2b-credit/update-limit/`

**Description:** Updates credit limit for a business user (admin access required).

**Request Body:**
```json
{
    "user_id": 456,
    "new_limit": "15000.00",
    "reason": "Increased based on payment history"
}
```

**Response Format:**
```json
{
    "success": true,
    "message": "Credit limit updated successfully",
    "user_id": 456,
    "old_limit": "10000.00",
    "new_limit": "15000.00",
    "updated_by": "admin@company.com",
    "updated_at": "2025-12-02T10:30:00Z"
}
```

---

## Enhanced Product APIs

### 6. Product List with B2B Information

**Endpoint:** `GET /producer/products/`

**Description:** Enhanced product listing that includes B2B pricing information for verified businesses.

**Query Parameters:**
- `page`: Integer - Page number for pagination
- `limit`: Integer - Items per page
- `category`: String - Filter by category
- `has_b2b_pricing`: Boolean - Filter products with B2B pricing
- `min_quantity`: Integer - Filter by minimum B2B quantity

**Response Format:**
```json
{
    "count": 150,
    "next": "/api/v1/producer/products/?page=2",
    "previous": null,
    "results": [
        {
            "id": 123,
            "name": "Sample Product",
            "description": "Product description",
            "price": "100.00",
            "category": "Electronics",
            "stock_quantity": 500,
            "b2b_enabled": true,
            "b2b_price": "85.00",
            "b2b_min_quantity": 10,
            "b2b_discount_percentage": "15.00",
            "available_tiers": [
                {
                    "customer_type": "distributor",
                    "min_quantity": 10,
                    "price": "85.00"
                }
            ]
        }
    ]
}
```

---

### 7. Product Detail with B2B Pricing

**Endpoint:** `GET /producer/products/{product_id}/`

**Description:** Detailed product information including complete B2B pricing structure.

**Response Format:**
```json
{
    "id": 123,
    "name": "Sample Product",
    "description": "Detailed product description",
    "price": "100.00",
    "category": "Electronics",
    "stock_quantity": 500,
    "images": [...],
    "specifications": {...},
    "b2b_pricing": {
        "enabled": true,
        "base_price": "85.00",
        "min_quantity": 10,
        "tiers": [
            {
                "customer_type": "distributor",
                "min_quantity": 10,
                "max_quantity": 99,
                "price_per_unit": "85.00",
                "discount_percentage": "15.00"
            },
            {
                "customer_type": "distributor",
                "min_quantity": 100,
                "max_quantity": null,
                "price_per_unit": "75.00",
                "discount_percentage": "25.00"
            },
            {
                "customer_type": "retailer",
                "min_quantity": 20,
                "max_quantity": null,
                "price_per_unit": "90.00",
                "discount_percentage": "10.00"
            }
        ]
    }
}
```

---

## Error Handling

### Standard Error Response Format
```json
{
    "error": true,
    "message": "Error description",
    "code": "ERROR_CODE",
    "details": {
        "field": "Specific field error details"
    }
}
```

### Common Error Codes
- `INSUFFICIENT_CREDIT`: Not enough credit for operation
- `BUSINESS_NOT_VERIFIED`: Business verification required
- `INVALID_QUANTITY`: Quantity below minimum B2B threshold
- `PRODUCT_NOT_B2B_ENABLED`: Product doesn't support B2B pricing
- `CREDIT_LIMIT_EXCEEDED`: Requested credit exceeds available limit

---

## Rate Limiting

All API endpoints are subject to rate limiting:
- **Standard Users**: 100 requests per minute
- **Business Users**: 500 requests per minute
- **Admin Users**: 1000 requests per minute

Rate limit headers included in responses:
```
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 487
X-RateLimit-Reset: 1672531200
```

---

## Negotiation System APIs

### 1. List/Initiate Negotiations
**Endpoint:** `GET/POST /negotiations/`
- **GET**: Returns ongoing negotiations. Includes `masked_price` and `is_locked` status.
- **POST**: Initiates a new deal. Buyer must be B2B verified.

### 2. Negotiation Actions (PATCH)
**Endpoint:** `PATCH /negotiations/{id}/`
Perform `ACCEPT`, `REJECT`, or `COUNTER_OFFER`. 
Integrated with **Distributed Locking** and **Price Masking** to ensure high-concurrency safety.

### 3. Concurrency Management
- **Force Release Lock**: `POST /negotiations/{id}/force_release_lock/` (Admin/Seller only)
- **Extend Lock**: `POST /negotiations/{id}/extend_lock/` (Current lock owner only)

---

## Analytics & Reporting APIs

### 1. Customer RFM Segments
**Endpoint:** `GET /report/rfm-segments/`
Returns RFM (Recency, Frequency, Monetary) analysis for buyer-seller relationships. 
Categories include: `Champions`, `Loyal Customers`, `At Risk`, `Hibernating`, `Lost`.

### 2. Weekly Business Digests
**Endpoint:** `GET /report/weekly-digests/`
Access to generated `WeeklyBusinessHealthDigest` reports containing total revenue, growth rate, and inventory health scores.

### 3. Predictive Lost Sales
**Endpoint:** `GET /report/lost-sales/`
Provides detailed analysis of potential revenue lost due to out-of-stock items, based on `avg_daily_demand` and `lead_time`.

---

## Pagination

List endpoints support pagination with the following parameters:
- `page`: Page number (default: 1)
- `limit`: Items per page (default: 20, max: 100)

Response includes pagination metadata:
```json
{
    "count": 1500,
    "next": "/api/v1/endpoint/?page=3",
    "previous": "/api/v1/endpoint/?page=1",
    "results": [...]
}
```

---

## Webhooks (Future Enhancement)

B2B system supports webhook notifications for:
- Credit limit changes
- Payment due date reminders
- Order status updates
- Price tier modifications

Webhook configuration available through admin interface.

---

## SDK and Client Libraries

Official client libraries available for:
- JavaScript/Node.js
- Python
- PHP
- Java

Example Python usage:
```python
from supply_chain_sdk import B2BClient

client = B2BClient(api_key="your-api-key")
pricing = client.get_b2b_pricing(product_id=123, quantity=50)
```

---

*For additional support or custom integrations, contact the API support team.*