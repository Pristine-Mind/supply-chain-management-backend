# Coupon and Redemption System Documentation

This document outlines the Coupon system implemented in the Marketplace. It provides details on the data model, available APIs, and how to integrate them into the frontend checkout process.

## Table of Contents
1. [Data Model](#data-model)
2. [API Endpoints](#api-endpoints)
3. [Frontend Integration Guide](#frontend-integration-guide)
4. [Admin Management](#admin-management)

---

## Data Model

The `Coupon` model is located in `market/models.py`.

### Key Fields:
- **`code`**: Unique uppercase string (e.g., `SUMMER20`).
- **`discount_type`**: `percentage` or `fixed`.
- **`discount_value`**: The value of the discount (e.g., `10.00` for 10% or $10).
- **`min_purchase_amount`**: Minimum cart total required to apply the coupon.
- **`max_discount_amount`**: (Optional) Cap for percentage-based discounts.
- **`start_date` / `end_date`**: Validity period.
- **`usage_limit`**: Total times the coupon can be used across the system.
- **`user_limit`**: Times a single user can use the same coupon (default: 1).
- **`is_active`**: Master toggle for the coupon.

---

## API Endpoints

All Coupon-related APIs are prefixed with `/api/v1/coupons/`.

### 1. Validate Coupon
Checks if a coupon is valid for the current user and their current cart.

- **Endpoint**: `POST /api/v1/coupons/validate/`
- **Auth Required**: Yes (Bearer Token)
- **Request Body**:
  ```json
  {
    "code": "SUMMER20",
    "cart_id": 123
  }
  ```
- **Success Response (200 OK)**:
  ```json
  {
    "valid": true,
    "message": "Coupon applied successfully",
    "data": {
      "original_amount": "1000.00",
      "discount_amount": "200.00",
      "final_amount": "800.00",
      "coupon_code": "SUMMER20",
      "discount_type": "percentage"
    }
  }
  ```
- **Error Response (200 OK or 400/404)**:
  ```json
  {
    "valid": false,
    "message": "This coupon has expired."
  }
  ```

### 2. Redeem Coupon (During Checkout)
Coupons are redeemed as part of the order creation process.

- **Endpoint**: `POST /api/v1/marketplace/create-order/` (or similar endpoint using `CreateOrderSerializer`)
- **Request Body Snippet**:
  ```json
  {
    "cart_id": 123,
    "delivery_info": { ... },
    "payment_method": "esewa",
    "coupon_code": "SUMMER20"
  }
  ```

### 3. Manage Coupons (Admin Only)
Standard CRUD operations are available for staff users:
- `GET /api/v1/coupons/`: List all coupons.
- `POST /api/v1/coupons/`: Create a new coupon.
- `GET /api/v1/coupons/{code}/`: Retrieve details.
- `PATCH /api/v1/coupons/{code}/`: Update.
- `DELETE /api/v1/coupons/{code}/`: Remove.

---

## Frontend Integration Guide

### Step 1: Add Coupon Input Field
In the checkout page, add a text input for the coupon code and an "Apply" button.

### Step 2: Validation
When the user clicks "Apply", call the `/api/v1/coupons/validate/` endpoint.
- If `valid: true`, update the UI to show the `discount_amount` and the new `final_amount`. Save the `coupon_code` in your state.
- If `valid: false`, show the `message` to the user in red.

### Step 3: Persistence
When the user proceeds to final checkout/payment, include the `coupon_code` in the order creation request.

### Step 4: Edge Cases to Handle
- **Empty Cart**: Validation will fail if the cart is empty.
- **Unauthorized**: User must be logged in to validate/use coupons.
- **Code Change**: If the user modifies their cart after applying a coupon, you should re-validate the coupon, as the `min_purchase_amount` check might now fail.

---

## Admin Management

Admins can manage coupons via the Django Admin panel under the **Market** section.
- Coupons are automatically converted to **UPPERCASE** on save.
- The `used_count` is read-only and increments automatically whenever an order is successfully placed using the coupon.
