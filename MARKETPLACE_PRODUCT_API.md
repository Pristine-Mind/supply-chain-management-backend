# Marketplace Product Creation API

## Overview
This document describes the new API endpoints for creating marketplace products from existing products.

## Endpoints

### 1. Create Marketplace Product from Product ID
**Endpoint:** `POST /api/marketplace-products/create-from-product/`
**Description:** Creates a marketplace product from an existing product using the product ID.
**Authentication:** Required

#### Request Body
```json
{
    "product_id": 123,
    "listed_price": 99.99,           // optional, defaults to product price
    "discounted_price": 79.99,       // optional
    "size": "M",                     // optional, inherits from product if not provided
    "color": "RED",                  // optional, inherits from product if not provided
    "additional_information": "Special marketplace information", // optional
    "min_order": 1,                  // optional
    "offer_start": "2025-01-01T00:00:00Z",  // optional
    "offer_end": "2025-01-31T23:59:59Z",    // optional
    "estimated_delivery_days": 3,    // optional
    "shipping_cost": "5.00",         // optional, defaults to 0
    "is_featured": false,            // optional, defaults to false
    "is_made_in_nepal": true         // optional, defaults to false
}
```

#### Response Success (201)
```json
{
    "message": "Marketplace product created successfully for 'Product Name'",
    "data": {
        "id": 456,
        "product": 123,
        "product_details": {
            "id": 123,
            "name": "Product Name",
            "description": "Product description",
            "price": 99.99,
            "size": "M",
            "color": "RED",
            // ... other product fields
        },
        "listed_price": 99.99,
        "discounted_price": 79.99,
        "size": "M",
        "color": "RED",
        "size_display": "Medium",
        "color_display": "Red",
        "effective_size": "M",
        "effective_color": "RED",
        "additional_information": "Special marketplace information",
        "is_available": true,
        "is_featured": false,
        "is_made_in_nepal": true,
        "listed_date": "2025-11-26T12:00:00Z",
        // ... other marketplace fields
    }
}
```

#### Response Error Examples
```json
// Product not found
{
    "error": "Product not found"
}

// Marketplace product already exists
{
    "product_id": ["A marketplace product already exists for this product."]
}

// Permission denied
{
    "error": "You don't have permission to create marketplace product for this product"
}

// Invalid product (inactive)
{
    "product_id": ["Cannot create marketplace product from inactive product."]
}
```

### 2. Push Product to Marketplace (Alternative Endpoint)
**Endpoint:** `POST /api/products/{product_id}/push-to-marketplace/`
**Description:** Directly pushes a specific product to the marketplace.
**Authentication:** Required

#### Request Body (all fields optional)
```json
{
    "listed_price": 99.99,
    "discounted_price": 79.99,
    "size": "M",
    "color": "RED",
    "additional_information": "Special marketplace information",
    "min_order": 1,
    "offer_start": "2025-01-01T00:00:00Z",
    "offer_end": "2025-01-31T23:59:59Z",
    "estimated_delivery_days": 3,
    "shipping_cost": "5.00",
    "is_featured": false,
    "is_made_in_nepal": true
}
```

#### Response
Same format as the create-from-product endpoint.

## Field Inheritance
When creating a marketplace product, the following fields are automatically inherited from the base product if not explicitly provided:

- `size` - inherits from `product.size`
- `color` - inherits from `product.color`
- `additional_information` - inherits from `product.additional_information`
- `listed_price` - defaults to `product.price`

## Choice Fields
### Size Choices
- `XS` - Extra Small
- `S` - Small
- `M` - Medium
- `L` - Large
- `XL` - Extra Large
- `XXL` - Double Extra Large
- `XXXL` - Triple Extra Large
- `ONE_SIZE` - One Size
- `CUSTOM` - Custom Size

### Color Choices
- `RED` - Red
- `BLUE` - Blue
- `GREEN` - Green
- `YELLOW` - Yellow
- `BLACK` - Black
- `WHITE` - White
- `GRAY` - Gray
- `BROWN` - Brown
- `ORANGE` - Orange
- `PURPLE` - Purple
- `PINK` - Pink
- `NAVY` - Navy
- `BEIGE` - Beige
- `GOLD` - Gold
- `SILVER` - Silver
- `MULTICOLOR` - Multicolor
- `TRANSPARENT` - Transparent
- `CUSTOM` - Custom Color

## Getting Choice Options
### Get Size Choices
**Endpoint:** `GET /api/marketplace-products/size-choices/`
**Authentication:** Not required

### Get Color Choices
**Endpoint:** `GET /api/marketplace-products/color-choices/`
**Authentication:** Not required

### Get All Filter Options
**Endpoint:** `GET /api/marketplace-products/filter-options/`
**Authentication:** Not required

Response format:
```json
{
    "sizes": [
        {"key": "S", "value": "Small"},
        {"key": "M", "value": "Medium"},
        // ...
    ],
    "colors": [
        {"key": "RED", "value": "Red"},
        {"key": "BLUE", "value": "Blue"},
        // ...
    ]
}
```

## Permissions
- Users can only create marketplace products for products they own or products in their shop
- Staff and superusers can create marketplace products for any product
- Shop-based permissions apply based on `user_profile.shop_id`

## Validation Rules
1. Product must exist and be active
2. Only one marketplace product can exist per product
3. If `discounted_price` is provided, it must be less than `listed_price`
4. If offer dates are provided, `offer_end` must be after `offer_start`
5. `size` and `color` must be valid choices if provided
6. For distributors, `min_order` is required and must be greater than 0

## Example Usage

### JavaScript/Frontend
```javascript
// Create marketplace product
const createMarketplaceProduct = async (productId, marketplaceData = {}) => {
    const response = await fetch('/api/marketplace-products/create-from-product/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + authToken
        },
        body: JSON.stringify({
            product_id: productId,
            ...marketplaceData
        })
    });
    
    return response.json();
};

// Usage
const result = await createMarketplaceProduct(123, {
    listed_price: 99.99,
    size: 'M',
    color: 'RED',
    is_featured: true
});
```

### cURL
```bash
# Create marketplace product
curl -X POST "http://localhost:8000/api/marketplace-products/create-from-product/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 123,
    "listed_price": 99.99,
    "size": "M",
    "color": "RED",
    "is_featured": true
  }'

# Push product to marketplace (alternative)
curl -X POST "http://localhost:8000/api/products/123/push-to-marketplace/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "listed_price": 99.99,
    "size": "M",
    "color": "RED"
  }'
```