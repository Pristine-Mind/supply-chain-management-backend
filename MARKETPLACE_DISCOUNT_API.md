# Marketplace Product Discount API Documentation

## Overview

Businesses can now set discount percentages on their marketplace products. The system automatically calculates the discounted price based on the discount percentage provided, allowing for easy management of product pricing through the business dashboard.

## Features

- **Discount Percentage Field**: Add discount percentage (0-100%) directly when creating or updating marketplace products
- **Auto-Calculated Discounted Price**: System automatically calculates the final discounted price
- **Savings Amount**: Automatic calculation of savings amount for customer visibility
- **API Endpoints**: Complete REST API endpoints for managing discounts
- **Serializer Support**: Full integration with existing marketplace product serializer

## Model Changes

### MarketplaceProduct Model

**New Field Added:**
```python
discount_percentage = models.FloatField(
    default=0,
    verbose_name=_("Discount Percentage"),
    help_text="Discount percentage to apply (0-100). Auto-calculates discounted_price.",
    validators=[MinValueValidator(0), MaxValueValidator(100)],
)
```

**Updated `save()` Method:**
- When `discount_percentage` is set (>0), the system automatically calculates `discounted_price`
- Formula: `discounted_price = listed_price * (1 - discount_percentage/100)`
- When `discount_percentage` is 0, `discounted_price` is cleared

## API Endpoints

### 1. Set Discount (Create/Update)

**Endpoint:** 
```
PATCH /api/marketplace-products/{id}/set-discount/
POST /api/marketplace-products/{id}/set-discount/
```

**Authentication:** Required (JWT Token)

**Request Body:**
```json
{
    "discount_percentage": 15.0
}
```

**Response (200 OK):**
```json
{
    "message": "Discount percentage updated successfully to 15.0%",
    "discount_applied": {
        "listed_price": 1000.0,
        "discount_percentage": 15.0,
        "discounted_price": 850.0,
        "savings_amount": 150.0
    },
    "product": {
        "id": 123,
        "product": 456,
        "listed_price": 1000.0,
        "discount_percentage": 15.0,
        "discounted_price": 850.0,
        "percent_off": 15.0,
        "savings_amount": 150.0,
        "is_available": true,
        ...
    }
}
```

**Error Responses:**

- **400 Bad Request** - Invalid discount_percentage:
```json
{
    "error": "discount_percentage must be between 0 and 100"
}
```

- **403 Forbidden** - User doesn't own the product:
```json
{
    "detail": "You don't have permission to update discount for this product"
}
```

### 2. Get Discount Info

**Endpoint:**
```
GET /api/marketplace-products/{id}/discount-info/
```

**Authentication:** Required (JWT Token)

**Response (200 OK):**
```json
{
    "listed_price": 1000.0,
    "discount_percentage": 15.0,
    "discounted_price": 850.0,
    "savings_amount": 150.0,
    "percent_off": 15.0,
    "effective_price": 850.0
}
```

### 3. Create/Update Marketplace Product

**Endpoint:**
```
POST /api/marketplace-products/
PATCH /api/marketplace-products/{id}/
PUT /api/marketplace-products/{id}/
```

**Authentication:** Required (JWT Token)

**Request Body (with discount):**
```json
{
    "product": 456,
    "listed_price": 1000.0,
    "discount_percentage": 15.0,
    "estimated_delivery_days": 3,
    "shipping_cost": "50.00",
    "is_available": true
}
```

**Response:**
```json
{
    "id": 123,
    "product": 456,
    "listed_price": 1000.0,
    "discount_percentage": 15.0,
    "discounted_price": 850.0,
    "percent_off": 15.0,
    "savings_amount": 150.0,
    "is_available": true,
    "effective_price": 850.0,
    ...
}
```

## Serializer Integration

The `MarketplaceProductSerializer` now includes:

```python
discount_percentage = serializers.FloatField(required=False, allow_null=True)
```

And validates:
- Must be between 0 and 100
- Supports both creation and update operations
- Properly serialized in list and detail endpoints

## Usage Examples

### JavaScript/TypeScript (Frontend Dashboard)

```javascript
// Set discount percentage
async function setProductDiscount(productId, discountPercentage) {
    const token = localStorage.getItem('authToken');
    
    const response = await fetch(
        `/api/marketplace-products/${productId}/set-discount/`,
        {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                discount_percentage: discountPercentage
            })
        }
    );
    
    const data = await response.json();
    
    if (response.ok) {
        console.log('Discount applied:', data.discount_applied);
        // Update UI with new prices
        return data;
    } else {
        console.error('Error:', data.error || data.detail);
        throw new Error(data.error || data.detail);
    }
}

// Get current discount info
async function getDiscountInfo(productId) {
    const token = localStorage.getItem('authToken');
    
    const response = await fetch(
        `/api/marketplace-products/${productId}/discount-info/`,
        {
            headers: {
                'Authorization': `Bearer ${token}`,
            }
        }
    );
    
    return await response.json();
}

// Usage
setProductDiscount(123, 20)
    .then(result => console.log('New prices:', result.discount_applied))
    .catch(error => console.error('Failed to set discount:', error));
```

### Python (Backend Usage)

```python
from producer.models import MarketplaceProduct

# Get a marketplace product
product = MarketplaceProduct.objects.get(id=123)

# Set discount percentage
product.discount_percentage = 15.0
product.save()

# Access calculated values
print(f"Listed Price: {product.listed_price}")
print(f"Discount Percentage: {product.discount_percentage}%")
print(f"Discounted Price: {product.discounted_price}")
print(f"Savings Amount: {product.savings_amount}")
print(f"Percent Off: {product.percent_off}%")

# Clear discount
product.discount_percentage = 0
product.save()  # discounted_price is cleared
```

### cURL Examples

```bash
# Set a 15% discount
curl -X PATCH \
  http://localhost:8000/api/marketplace-products/123/set-discount/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"discount_percentage": 15.0}'

# Get discount info
curl -X GET \
  http://localhost:8000/api/marketplace-products/123/discount-info/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Create product with discount
curl -X POST \
  http://localhost:8000/api/marketplace-products/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 456,
    "listed_price": 1000.0,
    "discount_percentage": 20.0,
    "estimated_delivery_days": 3,
    "shipping_cost": "50.00",
    "is_available": true
  }'
```

## Validation Rules

1. **Discount Percentage Range:**
   - Minimum: 0
   - Maximum: 100
   - Must be a valid number

2. **Automatic Calculation:**
   - Discounted Price = Listed Price × (1 - Discount% / 100)
   - Savings Amount = Listed Price - Discounted Price
   - Percent Off = Discount Percentage

3. **Edge Cases:**
   - Setting discount_percentage to 0 clears the discounted_price
   - Listed price must be set before applying discount
   - Discounted price must be less than listed price (validated in save method)

## Business Dashboard Integration

The business dashboard can use these endpoints to:

1. **Product Creation Form:**
   - Add "Discount Percentage" input field
   - Show real-time preview of discounted price

2. **Product Management:**
   - Display current discount percentage
   - Show savings amount and final price
   - Bulk discount management

3. **Product Listing:**
   - Display "X% OFF" badge
   - Show original vs. discounted price
   - Calculate and display savings

## Migration Required

Run the following command to apply the database changes:

```bash
python manage.py migrate producer
```

## Backward Compatibility

- Existing marketplace products (without discount_percentage) will have default value of 0
- No discount is applied until explicitly set
- Existing discounted_price field remains unchanged for backward compatibility

## Performance Considerations

- Discount calculation is done at save time, not query time
- No additional database queries for discount info
- Properties (`percent_off`, `savings_amount`) are computed on-the-fly for read operations
- Serializer includes all discount-related fields efficiently

## Security

- Only authenticated users can set discounts
- Only product owner or staff can modify discount
- Input validation prevents invalid discount percentages
- Proper permission checks on all endpoints

## Testing

Example test cases:

```python
from django.test import TestCase
from producer.models import MarketplaceProduct
from decimal import Decimal

class DiscountTestCase(TestCase):
    def test_discount_percentage_calculation(self):
        product = MarketplaceProduct.objects.create(
            listed_price=1000.0,
            discount_percentage=15.0,
            ...
        )
        self.assertEqual(product.discounted_price, 850.0)
        self.assertEqual(product.savings_amount, 150.0)
        self.assertEqual(product.percent_off, 15.0)
    
    def test_zero_discount_clears_discounted_price(self):
        product = MarketplaceProduct.objects.create(
            listed_price=1000.0,
            discount_percentage=10.0,
            ...
        )
        product.discount_percentage = 0
        product.save()
        self.assertIsNone(product.discounted_price)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Discount not applied | Ensure `discount_percentage` is between 0-100 |
| 403 Forbidden when setting discount | Verify you own the product or are staff |
| discounted_price not updating | Save the object after setting discount_percentage |
| Migration fails | Run `python manage.py makemigrations` first |

## Future Enhancements

- Time-based discount scheduling
- Bulk discount rules
- Customer-specific discounts
- Discount coupon integration
- Analytics on discount effectiveness
