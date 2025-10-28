# Supply Chain Management - API Flow & Data Storage Documentation

## Overview

This document provides comprehensive API specifications and step-by-step flows for the supply chain management system, covering order creation, payment processing, delivery management, and tracking.

## 1. Order Creation Flow

### 1.1 Create Order API
**Endpoint**: `POST /api/v1/marketplace/orders/create/`
**Authentication**: Required (Bearer Token)
**Content-Type**: `application/json`

```
User Cart → Order Creation → Clear Cart → Order Tracking
```

**Request Body**:
```json
{
  "cart_id": 123,
  "delivery_info": {
    "customer_name": "John Doe",
    "phone_number": "+977-9841234567",
    "address": "Thamel, Kathmandu",
    "city": "Kathmandu",
    "state": "Bagmati",
    "zip_code": "44600",
    "latitude": 27.7172,
    "longitude": 85.3240,
    "delivery_instructions": "Call when arrived"
  },
  "payment_method": "KHALTI"
}
```

**Response (201 Created)**:
```json
{
  "id": 456,
  "order_number": "MP-20241027-A1B2C3D4",
  "customer": 789,
  "order_status": "pending",
  "payment_status": "pending",
  "total_amount": "2500.00",
  "currency": "NPR",
  "items": [
    {
      "id": 101,
      "product": {
        "id": 50,
        "name": "Organic Rice",
        "price": "1250.00"
      },
      "quantity": 2,
      "unit_price": "1250.00",
      "total_price": "2500.00"
    }
  ],
  "delivery": {
    "customer_name": "John Doe",
    "phone_number": "+977-9841234567",
    "address": "Thamel, Kathmandu",
    "city": "Kathmandu"
  },
  "created_at": "2024-10-27T10:30:00Z",
  "can_cancel": true,
  "is_paid": false
}
```

**Flow Details**:
1. User calls create order API with cart_id and delivery information
2. System validates cart exists and belongs to user
3. Creates DeliveryInfo record

**Flow Details**:
1. User calls create order API with cart_id and delivery information
2. System validates cart exists and belongs to user
3. Creates DeliveryInfo record
4. **Data Storage in MarketplaceOrder**:
   ```python
   MarketplaceOrder.objects.create(
       customer=cart.user,
       delivery=delivery_info,  # DeliveryInfo instance
       total_amount=calculated_total,
       order_status=OrderStatus.PENDING,
       payment_status=PaymentStatus.PENDING,
       order_number="MP-20241027-A1B2C3D4"  # Auto-generated
   )
   ```

5. **Data Storage in MarketplaceOrderItem**:
   ```python
   # For each cart item
   MarketplaceOrderItem.objects.create(
       order=order,
       product=cart_item.product,  # MarketplaceProduct
       quantity=cart_item.quantity,
       unit_price=product.discounted_price or product.listed_price,
       total_price=unit_price * quantity
   )
   ```

6. **Initial Tracking Event**:
   ```python
   OrderTrackingEvent.objects.create(
       marketplace_order=order,
       status=OrderStatus.PENDING,
       message="Order created successfully"
   )
   ```

7. Cart items are cleared after successful order creation

**Error Responses**:
- `400 Bad Request`: Invalid cart_id or cart is empty
- `404 Not Found`: Cart not found or doesn't belong to user
- `401 Unauthorized`: Authentication required

---

## 2. Payment Processing Flow

### 2.1 Available Payment Gateways

#### 2.1.1 Get Payment Gateways API
**Endpoint**: `GET /api/v1/payments/gateways/`
**Authentication**: None (Public)
**Content-Type**: `application/json`

**Response (200 OK)**:
```json
{
  "status": "success",
  "data": [
    {
      "slug": "KHALTI",
      "name": "Khalti Wallet",
      "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/wallet.svg",
      "items": []
    },
    {
      "slug": "SCT",
      "name": "SCT Card",
      "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/sct.svg",
      "items": []
    },
    {
      "slug": "CONNECT_IPS",
      "name": "Connect IPS",
      "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/connect-ips.svg",
      "items": []
    },
    {
      "slug": "MOBILE_BANKING",
      "name": "Mobile Banking",
      "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/mbanking.svg",
      "items": [
        {
          "idx": "global_ime_bank",
          "name": "Global IME Bank",
          "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/bank_logo/global_ime_bank.jpg"
        },
        {
          "idx": "nabil_bank",
          "name": "Nabil Bank",
          "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/bank_logo/nabil_bank.jpg"
        }
      ]
    },
    {
      "slug": "EBANKING",
      "name": "E-Banking",
      "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/ebanking.svg",
      "items": [
        {
          "idx": "himali_bank",
          "name": "Himali Bank",
          "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/bank_logo/himali_bank.jpg"
        },
        {
          "idx": "nepal_sbi_bank",
          "name": "Nepal SBI Bank",
          "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/bank_logo/nepal_sbi_bank.jpg"
        }
      ]
    }
  ]
}
```

#### 2.1.2 Supported Payment Methods

| Method | Code | Description | Bank Selection Required |
|--------|------|-------------|------------------------|
| Khalti Wallet | `KHALTI` | Digital wallet payment | No |
| SCT Card | `SCT` | Debit/Credit card payment | No |
| Connect IPS | `CONNECT_IPS` | Inter-bank payment system | No |
| Mobile Banking | `MOBILE_BANKING` | Mobile banking apps | Yes |
| E-Banking | `EBANKING` | Online banking | Yes |

### 2.2 Initiate Payment API
**Endpoint**: `POST /api/v1/payments/initiate/`
**Authentication**: Required (Bearer Token)
**Content-Type**: `application/json`

```
Cart → Payment Transaction → Gateway Selection → Payment URL → User Redirect
```

#### 2.2.1 Request Body Examples

**Khalti Wallet Payment**:
```json
{
  "cart_id": 123,
  "gateway": "KHALTI",
  "return_url": "https://yourapp.com/payment/return",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_phone": "+977-9841234567",
  "tax_amount": "325.00",
  "shipping_cost": "100.00"
}
```

**SCT Card Payment**:
```json
{
  "cart_id": 123,
  "gateway": "SCT",
  "return_url": "https://yourapp.com/payment/return",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_phone": "+977-9841234567",
  "tax_amount": "325.00",
  "shipping_cost": "100.00"
}
```

**Mobile Banking Payment**:
```json
{
  "cart_id": 123,
  "gateway": "MOBILE_BANKING",
  "bank": "global_ime_bank",
  "return_url": "https://yourapp.com/payment/return",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_phone": "+977-9841234567",
  "tax_amount": "325.00",
  "shipping_cost": "100.00"
}
```

**E-Banking Payment**:
```json
{
  "cart_id": 123,
  "gateway": "EBANKING",
  "bank": "himali_bank",
  "return_url": "https://yourapp.com/payment/return",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_phone": "+977-9841234567",
  "tax_amount": "325.00",
  "shipping_cost": "100.00"
}
```

**Connect IPS Payment**:
```json
{
  "cart_id": 123,
  "gateway": "CONNECT_IPS",
  "return_url": "https://yourapp.com/payment/return",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_phone": "+977-9841234567",
  "tax_amount": "325.00",
  "shipping_cost": "100.00"
}
```

#### 2.2.2 Response Format

**Success Response (200 OK)**:
```json
{
  "status": "success",
  "payment_url": "https://pay.khalti.com/epayment/initiate/?token=xyz123",
  "transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
  "order_number": "PMT-20241027-X1Y2Z3",
  "data": {
    "pidx": "khalti_payment_idx_123456",
    "payment_url": "https://pay.khalti.com/epayment/initiate/?token=xyz123",
    "expires_at": "2024-10-27T11:30:00Z",
    "gateway": "KHALTI",
    "amount": 2925.00
  }
}
```

**Flow Details**:
1. System validates payment gateway and bank (if required)
2. Calculates cart total including taxes and shipping
3. Creates PaymentTransaction record:
   ```python
   PaymentTransaction.objects.create(
       user=request.user,
       cart=cart,
       gateway=gateway,  # "KHALTI", "SCT", "MOBILE_BANKING", etc.
       bank=bank,  # Required for MOBILE_BANKING and EBANKING
       subtotal=subtotal,
       tax_amount=tax_amount,
       shipping_cost=shipping_cost,
       total_amount=total_amount,
       status=PaymentTransactionStatus.PROCESSING,
       customer_name=customer_name,
       customer_email=customer_email,
       customer_phone=customer_phone
   )
   ```
4. Calls Khalti API with appropriate gateway configuration
5. Returns payment URL for user redirection

**Error Responses**:
- `400 Bad Request`: Invalid cart, gateway, or missing bank for banking methods
- `404 Not Found`: Cart not found
- `500 Internal Server Error`: Payment gateway API failure

### 2.3 Payment Status Check API
**Endpoint**: `GET /api/v1/payments/status/{transaction_id}/`
**Authentication**: Required (Transaction Owner)

**Response (200 OK)**:
```json
{
  "status": "success",
  "data": {
    "transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
    "gateway_transaction_id": "khalti_txn_789",
    "order_number": "PMT-20241027-X1Y2Z3",
    "payment_status": "completed",
    "gateway": "KHALTI",
    "total_amount": 2925.00,
    "is_successful": true,
    "khalti_amount": 2925.00,
    "created_at": "2024-10-27T10:30:00Z",
    "completed_at": "2024-10-27T10:45:00Z",
    "inquiry_data": {
      "status": "Completed",
      "total_amount": 292500,
      "fee": 2925,
      "refunded": false
    }
  }
}
```

### 2.4 Payment Callback API
**Endpoint**: `POST /api/v1/payments/callback/`
**Authentication**: None (Called by Payment Gateway)
**Content-Type**: `application/json`

```
Gateway Callback → Verify Transaction → Create MarketplaceSales → Update Stock → Notify
```

#### 2.4.1 Callback Processing Flow

**Request Body (from Khalti)**:
```json
{
  "pidx": "khalti_payment_idx_123456",
  "status": "Completed",
  "total_amount": 292500,
  "transaction_id": "khalti_txn_789",
  "fee": 2925,
  "refunded": false,
  "purchase_order_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
  "purchase_order_name": "PMT-20241027-X1Y2Z3"
}
```

**Success Response (200 OK)**:
```json
{
  "status": "success",
  "message": "Payment completed successfully",
  "data": {
    "transaction_id": "khalti_txn_789",
    "payment_transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
    "order_number": "PMT-20241027-X1Y2Z3",
    "amount": 2925.00,
    "gateway": "KHALTI",
    "marketplace_sales": [
      {
        "order_number": "MS-20241027-A1B2C3",
        "product_name": "Organic Rice",
        "quantity": 2,
        "total_amount": 2500.00,
        "seller": "farmer_john"
      }
    ],
    "total_items": 1,
    "processing_time": "2024-10-27T10:45:15Z"
  }
}
```

#### 2.4.2 Critical Processing Steps

1. **Transaction Verification**:
   ```python
   # Khalti inquiry to verify payment status
   khalti = Khalti()
   inquiry_result = khalti.inquiry(khalti_transaction_id)
   is_successful = khalti.is_success(inquiry_result)
   ```

2. **Payment Completion**:
   ```python
   if is_successful:
       payment_transaction.mark_as_completed(khalti_transaction_id)
   ```

3. **MarketplaceSale Creation** (Automatic):
   ```python
   # This happens in PaymentTransaction._create_marketplace_sales()
   for each cart_item:
       MarketplaceSale.objects.create(
           buyer=payment_transaction.user,
           seller=cart_item.product.product.user,
           product=cart_item.product,
           quantity=cart_item.quantity,
           unit_price=cart_item.product.price,
           total_amount=calculated_item_total,
           payment_method=payment_transaction.gateway,
           transaction_id=payment_transaction.transaction_id,
           payment_status=PaymentStatus.PAID,
           status=SaleStatus.PROCESSING,
           order_number=auto_generated_order_number
       )
   ```

4. **Inventory Management**:
   ```python
   # Update product stock
   cart_item.product.stock -= cart_item.quantity
   cart_item.product.save()
   ```

5. **Transaction Item Linking**:
   ```python
   PaymentTransactionItem.objects.create(
       payment_transaction=self,
       marketplace_sale=marketplace_sale,
       product=cart_item.product,
       quantity=cart_item.quantity,
       unit_price=cart_item.product.price,
       total_amount=item_total
   )
   ```

### 2.5 Payment Method Specific Flows

#### 2.5.1 Khalti Wallet Flow
```
1. User selects Khalti Wallet
2. System calls /api/v1/payments/initiate/ with gateway="KHALTI"
3. Khalti API returns payment URL
4. User redirected to Khalti payment page
5. User authenticates with PIN/Password
6. Payment processed
7. Khalti calls callback with success/failure
8. System verifies with Khalti inquiry API
9. Create sales and update inventory
```

#### 2.5.2 Mobile Banking Flow
```
1. User selects Mobile Banking + Bank
2. System calls /api/v1/payments/initiate/ with gateway="MOBILE_BANKING" & bank
3. Khalti API returns bank-specific payment URL
4. User redirected to bank's mobile banking interface
5. User authenticates with bank credentials
6. Payment processed through bank
7. Bank notifies Khalti → Khalti calls callback
8. System verifies and processes payment
```

#### 2.5.3 E-Banking Flow
```
1. User selects E-Banking + Bank
2. System calls /api/v1/payments/initiate/ with gateway="EBANKING" & bank
3. Khalti API returns bank-specific payment URL
4. User redirected to bank's internet banking portal
5. User logs in with online banking credentials
6. Payment processed through bank's system
7. Bank confirms to Khalti → Khalti calls callback
8. System verifies and completes transaction
```

#### 2.5.4 SCT Card Flow
```
1. User selects SCT Card
2. System calls /api/v1/payments/initiate/ with gateway="SCT"
3. Khalti API returns card payment URL
4. User redirected to SCT payment gateway
5. User enters card details (number, CVV, expiry)
6. Card payment processed
7. Khalti receives confirmation → calls callback
8. System verifies and processes payment
```

#### 2.5.5 Connect IPS Flow
```
1. User selects Connect IPS
2. System calls /api/v1/payments/initiate/ with gateway="CONNECT_IPS"
3. Khalti API returns Connect IPS payment URL
4. User redirected to Connect IPS interface
5. User selects their bank and authenticates
6. Payment processed through IPS network
7. IPS confirms to Khalti → Khalti calls callback
8. System verifies and completes transaction
```

### 2.6 Payment Verification APIs

#### 2.6.1 Manual Payment Verification
**Endpoint**: `POST /api/v1/payments/verify/`
**Authentication**: Required (Admin/User)
**Content-Type**: `application/json`

**Request Body**:
```json
{
  "transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
  "force_verify": false
}
```

**Response (200 OK)**:
```json
{
  "status": "success",
  "message": "Payment verification completed",
  "data": {
    "transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
    "payment_status": "completed",
    "verification_result": {
      "gateway_status": "Completed",
      "amount_matches": true,
      "transaction_valid": true
    },
    "sales_created": 2,
    "inventory_updated": true
  }
}
```

#### 2.6.2 Webhook Handling
**Endpoint**: `POST /api/v1/payments/webhook/`
**Authentication**: None (Webhook signature verification)

For additional payment confirmations and real-time updates from payment gateways.

**Request Body (Webhook)**:
```json
{
  "event": "payment.completed",
  "data": {
    "transaction_id": "khalti_txn_789",
    "pidx": "khalti_payment_idx_123456",
    "status": "Completed",
    "amount": 292500,
    "timestamp": "2024-10-27T10:45:00Z"
  },
  "signature": "webhook_signature_hash"
}
```

### 2.7 Payment Error Handling

#### 2.7.1 Common Error Scenarios

**Insufficient Balance (Khalti Wallet)**:
```json
{
  "status": "failed",
  "message": "Insufficient wallet balance",
  "error_code": "INSUFFICIENT_BALANCE",
  "data": {
    "required_amount": 2925.00,
    "available_balance": 1500.00
  }
}
```

**Bank Service Unavailable**:
```json
{
  "status": "failed",
  "message": "Bank service temporarily unavailable",
  "error_code": "BANK_SERVICE_DOWN",
  "data": {
    "bank": "global_ime_bank",
    "retry_after": 300
  }
}
```

**Card Declined**:
```json
{
  "status": "failed",
  "message": "Card payment declined",
  "error_code": "CARD_DECLINED",
  "data": {
    "decline_reason": "Invalid card details",
    "can_retry": true
  }
}
```

**Payment Timeout**:
```json
{
  "status": "failed",
  "message": "Payment session expired",
  "error_code": "PAYMENT_TIMEOUT",
  "data": {
    "session_duration": 900,
    "expired_at": "2024-10-27T11:30:00Z"
  }
}
```

### 2.8 Payment Security & Compliance

#### 2.8.1 Security Measures
- **PCI DSS Compliance**: All card payments processed through PCI-compliant gateways
- **SSL/TLS Encryption**: All payment communications encrypted
- **Transaction Signatures**: Webhook verification using HMAC signatures
- **Rate Limiting**: Payment initiation rate limits per user
- **Fraud Detection**: Unusual payment pattern detection

### 2.9 Post-Payment Success APIs

After successful payment completion, the following APIs are automatically called or available:

#### 2.9.1 Order Status Update (Automatic)
When payment is completed, the system automatically:

1. **Updates MarketplaceOrder Status**:
   ```python
   # If order exists, mark as paid
   order.payment_status = PaymentStatus.PAID
   order.save()
   
   # Create tracking event
   OrderTrackingEvent.objects.create(
       marketplace_order=order,
       status=OrderStatus.CONFIRMED,
       message="Payment confirmed"
   )
   ```

#### 2.9.2 Notification APIs (Automatic)
**Email Notifications**:
- Order confirmation email to customer
- Sale notification email to sellers
- Payment receipt email

**SMS Notifications** (if configured):
- Payment confirmation SMS
- Order status SMS

#### 2.9.3 Invoice Generation API
**Endpoint**: `GET /api/v1/payments/{transaction_id}/invoice/`
**Authentication**: Required (Transaction Owner)

**Response (200 OK)**:
```json
{
  "invoice_number": "INV-20241027-001",
  "transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
  "order_number": "PMT-20241027-X1Y2Z3",
  "customer": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+977-9841234567"
  },
  "items": [
    {
      "product_name": "Organic Rice",
      "quantity": 2,
      "unit_price": 1250.00,
      "total": 2500.00,
      "seller": "farmer_john"
    }
  ],
  "subtotal": 2500.00,
  "tax_amount": 325.00,
  "shipping_cost": 100.00,
  "total_amount": 2925.00,
  "payment_method": "KHALTI",
  "payment_date": "2024-10-27T10:45:00Z",
  "status": "paid"
}
```

#### 2.9.4 Sales Analytics Update (Automatic)
The system automatically updates:
- Product sales count
- Seller revenue
- Customer purchase history
- Inventory levels
- Sales reports

### 2.10 Complete Payment Flow Summary

#### 2.10.1 Step-by-Step Payment Process

```bash
# Step 1: Get Available Payment Methods
curl -X GET "http://localhost:8000/api/v1/payments/gateways/"

# Step 2: Initiate Payment (Khalti Wallet Example)
curl -X POST "http://localhost:8000/api/v1/payments/initiate/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cart_id": 123,
    "gateway": "KHALTI",
    "return_url": "https://yourapp.com/payment/return",
    "customer_name": "John Doe",
    "customer_email": "john@example.com",
    "customer_phone": "+977-9841234567"
  }'

# Step 3: User is redirected to payment URL (handled by frontend)
# Payment URL: https://pay.khalti.com/epayment/initiate/?token=xyz123

# Step 4: Payment Callback (Automatic from Khalti)
curl -X POST "http://localhost:8000/api/v1/payments/callback/" \
  -H "Content-Type: application/json" \
  -d '{
    "pidx": "khalti_payment_idx_123456",
    "status": "Completed",
    "total_amount": 292500,
    "transaction_id": "khalti_txn_789"
  }'

# Step 5: Check Payment Status
curl -X GET "http://localhost:8000/api/v1/payments/status/d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Step 6: Get Invoice
curl -X GET "http://localhost:8000/api/v1/payments/d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9/invoice/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

#### 2.10.2 Frontend Integration Example

**JavaScript Payment Flow**:
```javascript
// 1. Get payment gateways
const gateways = await fetch('/api/v1/payments/gateways/')
  .then(res => res.json());

// 2. User selects payment method
const selectedGateway = 'KHALTI';
const selectedBank = null; // Only required for MOBILE_BANKING/EBANKING

// 3. Initiate payment
const paymentResponse = await fetch('/api/v1/payments/initiate/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${authToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    cart_id: cartId,
    gateway: selectedGateway,
    bank: selectedBank,
    return_url: window.location.origin + '/payment/return',
    customer_name: 'John Doe',
    customer_email: 'john@example.com',
    customer_phone: '+977-9841234567'
  })
});

const paymentData = await paymentResponse.json();

// 4. Redirect to payment URL
if (paymentData.status === 'success') {
  window.location.href = paymentData.payment_url;
}

// 5. Handle return from payment gateway (on return URL)
const urlParams = new URLSearchParams(window.location.search);
const pidx = urlParams.get('pidx');
const status = urlParams.get('status');

if (status === 'completed') {
  // Payment successful - check status and redirect to success page
  const statusResponse = await fetch(`/api/v1/payments/status/${paymentData.transaction_id}/`);
  const statusData = await statusResponse.json();
  
  if (statusData.data.is_successful) {
    // Redirect to order confirmation page
    window.location.href = `/orders/confirmation/${statusData.data.order_number}`;
  }
}
```

#### 2.10.3 Testing Payment Methods

**Test Credentials for Development**:

**Khalti Wallet (Test)**:
- Mobile: `9800000001`
- MPIN: `1111`

**Test Bank Details**:
- Any valid mobile number for mobile banking
- Use test credentials provided by respective banks

**Test Card Details**:
- Card Number: `4242424242424242`
- CVV: `123`
- Expiry: Any future date

#### 2.10.4 Production Configuration

**Environment Variables Required**:
```bash
# Khalti Configuration
KHALTI_SECRET_KEY=your_khalti_secret_key
KHALTI_PUBLIC_KEY=your_khalti_public_key
KHALTI_RETURN_URL=https://yourapp.com/payment/return
KHALTI_WEBHOOK_URL=https://yourapp.com/api/v1/payments/webhook/

# Site Configuration
SITE_URL=https://yourapp.com
DEBUG=False  # Set to False for production amounts
```

**Production Checklist**:
- [ ] Update Khalti credentials to production keys
- [ ] Configure proper return URLs
- [ ] Set up webhook endpoints
- [ ] Enable SSL/TLS for all payment endpoints
- [ ] Configure rate limiting
- [ ] Set up monitoring and alerting
- [ ] Test all payment methods
- [ ] Verify PCI compliance
- [ ] Set up proper logging
- [ ] Configure backup payment processing
**Endpoint**: `POST /api/v1/payments/callback/`
**Authentication**: None (Called by Khalti)
**Content-Type**: `application/json`

```
Khalti Callback → Verify Transaction → Create MarketplaceSales → Update Stock
```

**Request Body (from Khalti)**:
```json
{
  "pidx": "khalti_payment_idx_123456",
  "status": "Completed",
  "total_amount": 292500,
  "transaction_id": "khalti_txn_789",
  "fee": 2925,
  "refunded": false
}
```

**Response (200 OK)**:
```json
{
  "status": "success",
  "message": "Payment completed successfully",
  "data": {
    "transaction_id": "khalti_txn_789",
    "payment_transaction_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
    "order_number": "PMT-20241027-X1Y2Z3",
    "amount": 2925.00,
    "gateway": "KHALTI",
    "marketplace_sales": [
      {
        "order_number": "MS-20241027-A1B2C3",
        "product_name": "Organic Rice",
        "quantity": 2,
        "total_amount": 2500.00,
        "seller": "farmer_john"
      }
    ],
    "total_items": 1
  }
}
```

**Critical Flow**:
1. Khalti sends callback with `pidx` (transaction ID)
2. System calls Khalti inquiry API to verify payment status
3. If successful, calls `payment_transaction.mark_as_completed(khalti_transaction_id)`
4. **Data Storage in MarketplaceSale** (Automatic):
   ```python
   # This happens automatically in PaymentTransaction._create_marketplace_sales()
   for each cart_item:
       MarketplaceSale.objects.create(
           buyer=payment_transaction.user,
           seller=cart_item.product.product.user,  # Product owner
           product=cart_item.product,
           quantity=cart_item.quantity,
           unit_price=cart_item.product.price,
           total_amount=calculated_item_total,
           payment_method=payment_transaction.gateway,
           transaction_id=payment_transaction.transaction_id,
           payment_status=PaymentStatus.PAID,
           status=SaleStatus.PROCESSING,
           order_number=auto_generated_order_number
       )
   ```

5. **Stock Update**:
   ```python
   cart_item.product.stock -= cart_item.quantity
   cart_item.product.save()
   ```

6. **PaymentTransactionItem Creation**:
   ```python
   PaymentTransactionItem.objects.create(
       payment_transaction=self,
       marketplace_sale=marketplace_sale,
       product=cart_item.product,
       quantity=cart_item.quantity,
       unit_price=cart_item.product.price,
       total_amount=item_total
   )
   ```

**Error Responses**:
- `400 Bad Request`: Payment verification failed
- `404 Not Found`: Payment transaction not found
- `500 Internal Server Error`: Processing error

---

## 3. Post-Payment Delivery Management

### 3.1 Delivery Creation API
**Endpoint**: `POST /api/deliveries/create/`
**Authentication**: Required (Admin/Seller)
**Content-Type**: `application/json`

After payment success, delivery entries are created:

**Request Body**:
```json
{
  "marketplace_sale_id": 789,
  "pickup_address": "Farm Location, Bhaktapur",
  "pickup_latitude": 27.6710,
  "pickup_longitude": 85.4298,
  "pickup_contact_name": "Farmer John",
  "pickup_contact_phone": "+977-9841111111",
  "pickup_instructions": "Call 30 minutes before pickup",
  "delivery_address": "Thamel, Kathmandu",
  "delivery_latitude": 27.7172,
  "delivery_longitude": 85.3240,
  "delivery_contact_name": "John Doe",
  "delivery_contact_phone": "+977-9841234567",
  "delivery_instructions": "Call when arrived",
  "package_weight": 2.5,
  "package_dimensions": "30x20x15 cm",
  "package_value": 2500.00,
  "fragile": false,
  "requires_signature": true,
  "special_instructions": "Handle with care",
  "priority": "normal",
  "delivery_fee": 150.00,
  "requested_pickup_date": "2024-10-28T09:00:00Z",
  "requested_delivery_date": "2024-10-28T18:00:00Z"
}
```

**Response (201 Created)**:
```json
{
  "id": 101,
  "delivery_id": "f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6",
  "marketplace_sale": 789,
  "tracking_number": "TRK1234567890",
  "pickup_address": "Farm Location, Bhaktapur",
  "delivery_address": "Thamel, Kathmandu",
  "package_weight": 2.5,
  "status": "available",
  "status_display": "Available for Assignment",
  "priority": "normal",
  "priority_display": "Normal",
  "delivery_fee": 150.00,
  "distance_km": 25.3,
  "estimated_delivery_time": null,
  "created_at": "2024-10-27T10:45:00Z"
}
```

**Alternative: Management Command**:
```bash
python manage.py create_delivery \
  --marketplace-sale-id 789 \
  --pickup-address "Farm Location, Bhaktapur" \
  --delivery-address "Thamel, Kathmandu" \
  --pickup-contact-name "Farmer John" \
  --pickup-contact-phone "+977-9841111111" \
  --delivery-contact-name "John Doe" \
  --delivery-contact-phone "+977-9841234567" \
  --package-weight 2.5 \
  --delivery-fee 150.00
```

**Data Storage in Transport.Delivery**:
```python
Delivery.objects.create(
    marketplace_sale=marketplace_sale,  # Links to MarketplaceSale
    pickup_address=pickup_address,
    delivery_address=delivery_address,
    pickup_contact_name=pickup_contact_name,
    delivery_contact_name=delivery_contact_name,
    package_weight=package_weight,
    status=TransportStatus.AVAILABLE,  # Ready for assignment
    tracking_number=auto_generated_tracking_number,
    delivery_fee=delivery_fee,
    priority=priority
)
```

### 3.2 Delivery Assignment APIs

#### 3.2.1 Auto Assignment API
**Endpoint**: `POST /api/auto-assign/`
**Authentication**: Required (Admin)
**Content-Type**: `application/json`

```
Available Delivery → Score Transporters → Assign Best Match → Notify Parties
```

**Request Body (Single Delivery)**:
```json
{
  "delivery_id": 101
}
```

**Request Body (Bulk Assignment)**:
```json
{
  "priority_filter": "high",
  "vehicle_type_filter": "motorcycle",
  "max_assignments": 20,
  "time_range_hours": 24
}
```

**Response (200 OK) - Single Assignment**:
```json
{
  "success": true,
  "message": "Delivery assigned successfully",
  "delivery_id": 101,
  "delivery_uuid": "f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6",
  "assigned_transporter": {
    "id": 25,
    "name": "Ram Bahadur",
    "business_name": "Quick Transport",
    "vehicle_type": "motorcycle",
    "vehicle_number": "BA-1-PA-1234",
    "rating": 4.8,
    "phone": "+977-9841555555"
  },
  "score_details": {
    "distance_score": 85,
    "rating_score": 96,
    "capacity_score": 100,
    "workload_score": 75,
    "total_score": 89
  },
  "alternatives": [
    {
      "transporter_id": 30,
      "name": "Hari Singh",
      "score": 82
    }
  ],
  "distance_km": 25.3,
  "estimated_delivery_time": "2024-10-28T16:30:00Z"
}
```

**Response (200 OK) - Bulk Assignment**:
```json
{
  "success": true,
  "assignments": [
    {
      "delivery_id": 101,
      "delivery_uuid": "f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6",
      "tracking_number": "TRK1234567890",
      "assigned_transporter": "Ram Bahadur",
      "score": 89
    }
  ],
  "summary": {
    "total_processed": 5,
    "successful_assignments": 4,
    "failed_assignments": 1,
    "avg_score": 85.2
  },
  "failures": [
    {
      "delivery_id": "102",
      "error": "No available transporters found"
    }
  ]
}
```

**Assignment Logic**:
1. Find available transporters within delivery area
2. Score based on:
   - Distance from pickup location (0-100 points)
   - Transporter rating (0-100 points)
   - Vehicle capacity vs package weight (0-100 points)
   - Current workload (0-100 points)
3. Assign to highest-scoring transporter

**Data Updates**:
```python
delivery.assign_to_transporter(best_transporter)
# Updates:
# - delivery.transporter = transporter
# - delivery.status = TransportStatus.ASSIGNED
# - delivery.assigned_at = timezone.now()
```

#### 3.2.2 Manual Transporter Assignment
**Endpoint**: `POST /api/deliveries/{delivery_id}/accept/`
**Authentication**: Required (Transporter)
**Content-Type**: `application/json`

Used by transporters to accept delivery assignments.

**Request Body**:
```json
{
  "estimated_pickup_time": "2024-10-28T10:00:00Z",
  "notes": "Will pickup in the morning"
}
```

**Response (200 OK)**:
```json
{
  "id": 101,
  "delivery_id": "f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6",
  "status": "assigned",
  "status_display": "Assigned",
  "transporter": {
    "id": 25,
    "name": "Ram Bahadur",
    "business_name": "Quick Transport",
    "phone": "+977-9841555555"
  },
  "assigned_at": "2024-10-27T11:00:00Z",
  "estimated_delivery_time": "2024-10-28T16:30:00Z"
}
```

**Error Responses**:
- `400 Bad Request`: Package weight exceeds vehicle capacity
- `403 Forbidden`: Documents expired or not verified
- `404 Not Found`: Delivery not found
- `409 Conflict`: Delivery already assigned

---

## 4. Tracking and Status Updates

### 4.1 Order Tracking APIs

#### 4.1.1 Get Order Details
**Endpoint**: `GET /api/v1/marketplace/orders/{order_id}/`
**Authentication**: Required (Order Owner)

**Response (200 OK)**:
```json
{
  "id": 456,
  "order_number": "MP-20241027-A1B2C3D4",
  "customer": 789,
  "order_status": "shipped",
  "order_status_display": "Shipped",
  "payment_status": "paid",
  "payment_status_display": "Paid",
  "total_amount": "2500.00",
  "formatted_total": "NPR 2,500.00",
  "currency": "NPR",
  "items": [
    {
      "id": 101,
      "product": {
        "id": 50,
        "name": "Organic Rice",
        "price": "1250.00",
        "images": [
          {
            "image": "/media/product_images/rice.jpg"
          }
        ]
      },
      "quantity": 2,
      "unit_price": "1250.00",
      "total_price": "2500.00"
    }
  ],
  "delivery": {
    "customer_name": "John Doe",
    "phone_number": "+977-9841234567",
    "address": "Thamel, Kathmandu",
    "city": "Kathmandu",
    "full_address": "Thamel, Kathmandu, Bagmati, 44600"
  },
  "tracking_events": [
    {
      "id": 201,
      "status": "pending",
      "message": "Order created successfully",
      "created_at": "2024-10-27T10:30:00Z"
    },
    {
      "id": 202,
      "status": "confirmed",
      "message": "Payment confirmed",
      "created_at": "2024-10-27T10:45:00Z"
    },
    {
      "id": 203,
      "status": "shipped",
      "message": "Order shipped for delivery",
      "created_at": "2024-10-27T14:00:00Z"
    }
  ],
  "created_at": "2024-10-27T10:30:00Z",
  "estimated_delivery_date": "2024-10-28T18:00:00Z",
  "tracking_number": "TRK1234567890",
  "can_cancel": false,
  "can_refund": false,
  "is_paid": true,
  "is_delivered": false
}
```

#### 4.1.2 List Customer Orders
**Endpoint**: `GET /api/v1/marketplace/orders/my-orders/`
**Authentication**: Required (Customer)

**Query Parameters**:
- `status`: Filter by order status (pending, confirmed, shipped, delivered)
- `payment_status`: Filter by payment status (pending, paid, failed)
- `page`: Page number for pagination
- `page_size`: Number of items per page

**Response (200 OK)**:
```json
{
  "count": 25,
  "next": "http://api.example.com/api/v1/marketplace/orders/my-orders/?page=2",
  "previous": null,
  "results": [
    {
      "id": 456,
      "order_number": "MP-20241027-A1B2C3D4",
      "order_status": "shipped",
      "order_status_display": "Shipped",
      "payment_status": "paid",
      "total_amount": "2500.00",
      "formatted_total": "NPR 2,500.00",
      "items_count": 1,
      "created_at": "2024-10-27T10:30:00Z",
      "estimated_delivery_date": "2024-10-28T18:00:00Z"
    }
  ]
}
```

### 4.2 Delivery Tracking APIs

#### 4.2.1 Track Delivery by Tracking Number
**Endpoint**: `GET /api/deliveries/{tracking_number}/track/`
**Authentication**: None (Public)

**Response (200 OK)**:
```json
{
  "tracking_number": "TRK1234567890",
  "status": "in_transit",
  "status_display": "In Transit",
  "pickup_address": "Farm Location, Bhaktapur",
  "delivery_address": "Thamel, Kathmandu",
  "estimated_delivery_time": "2024-10-28T16:30:00Z",
  "transporter": {
    "name": "Ram Bahadur",
    "business_name": "Quick Transport",
    "phone": "+977-9841555555",
    "vehicle_type": "motorcycle",
    "vehicle_number": "BA-1-PA-1234"
  },
  "tracking_history": [
    {
      "status": "assigned",
      "status_display": "Assigned",
      "message": "Package assigned to transporter",
      "timestamp": "2024-10-27T11:00:00Z",
      "location": null
    },
    {
      "status": "picked_up",
      "status_display": "Picked Up",
      "message": "Package picked up from sender",
      "timestamp": "2024-10-28T09:30:00Z",
      "location": {
        "latitude": 27.6710,
        "longitude": 85.4298,
        "address": "Farm Location, Bhaktapur"
      }
    },
    {
      "status": "in_transit",
      "status_display": "In Transit",
      "message": "Package is on the way",
      "timestamp": "2024-10-28T10:15:00Z",
      "location": {
        "latitude": 27.6950,
        "longitude": 85.3800,
        "address": "Ring Road, Kathmandu"
      }
    }
  ],
  "distance_km": 25.3,
  "package_details": {
    "weight": 2.5,
    "dimensions": "30x20x15 cm",
    "value": 2500.00,
    "fragile": false,
    "requires_signature": true
  }
}
```

### 4.3 Transporter APIs

#### 4.3.1 Get Assigned Deliveries
**Endpoint**: `GET /api/transporters/{transporter_id}/deliveries/`
**Authentication**: Required (Transporter)

**Query Parameters**:
- `status`: Filter by delivery status
- `date_from`: Filter deliveries from date
- `date_to`: Filter deliveries to date

**Response (200 OK)**:
```json
{
  "count": 5,
  "results": [
    {
      "id": 101,
      "delivery_id": "f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6",
      "tracking_number": "TRK1234567890",
      "status": "assigned",
      "priority": "normal",
      "pickup_address": "Farm Location, Bhaktapur",
      "delivery_address": "Thamel, Kathmandu",
      "package_weight": 2.5,
      "delivery_fee": 150.00,
      "distance_km": 25.3,
      "assigned_at": "2024-10-27T11:00:00Z",
      "requested_pickup_date": "2024-10-28T09:00:00Z",
      "estimated_delivery_time": "2024-10-28T16:30:00Z"
    }
  ]
}
```

#### 4.3.2 Update Delivery Status
**Endpoint**: `POST /api/deliveries/{delivery_id}/pickup/`
**Authentication**: Required (Assigned Transporter)

**Request Body**:
```json
{
  "latitude": 27.6710,
  "longitude": 85.4298,
  "notes": "Package collected from farm",
  "pickup_photo": "base64_encoded_image_data"
}
```

**Response (200 OK)**:
```json
{
  "status": "picked_up",
  "message": "Delivery marked as picked up",
  "timestamp": "2024-10-28T09:30:00Z",
  "location": {
    "latitude": 27.6710,
    "longitude": 85.4298
  }
}
```

#### 4.3.3 Mark as Delivered
**Endpoint**: `POST /api/deliveries/{delivery_id}/deliver/`
**Authentication**: Required (Assigned Transporter)

**Request Body**:
```json
{
  "latitude": 27.7172,
  "longitude": 85.3240,
  "notes": "Delivered to customer",
  "delivery_photo": "base64_encoded_image_data",
  "signature": "base64_encoded_signature_data",
  "customer_rating": 5
}
```

**Response (200 OK)**:
```json
{
  "status": "delivered",
  "message": "Delivery completed successfully",
  "delivered_at": "2024-10-28T16:25:00Z",
  "location": {
    "latitude": 27.7172,
    "longitude": 85.3240
  },
  "earnings": 135.00
}
```

### 4.4 Order Tracking Events
**Model**: `OrderTrackingEvent`
- Supports both MarketplaceOrder and MarketplaceSale
- Dual foreign keys: `marketplace_order` and `marketplace_sale`

**Status Progression**:
```
PENDING → CONFIRMED → PROCESSING → SHIPPED → DELIVERED → COMPLETED
```

### 4.5 Delivery Tracking
**Model**: `DeliveryTracking`
- Real-time GPS tracking
- Status updates with timestamps
- Photo and signature capture

**Status Progression**:
```
AVAILABLE → ASSIGNED → PICKED_UP → IN_TRANSIT → DELIVERED
```

---

## 5. Data Relationships & Storage Patterns

### 5.1 MarketplaceOrder vs MarketplaceSale

**MarketplaceOrder** (New Consolidated System):
- **Purpose**: Multi-item orders with single delivery address
- **Relationship**: One order → Many order items → One delivery info
- **Use Case**: Shopping cart checkout with multiple products
- **When Created**: During order creation API call
- **Payment Link**: Links to PaymentTransaction

**MarketplaceSale** (Legacy Individual Sales):
- **Purpose**: Individual product sales
- **Relationship**: One sale → One product → One delivery
- **Use Case**: Direct product purchases
- **When Created**: After successful payment callback
- **Payment Link**: Created from PaymentTransactionItem

### 5.2 Data Flow Diagram

```
User Cart Items
       ↓
[POST /api/v1/marketplace/orders/create/]
       ↓
MarketplaceOrder ← → DeliveryInfo
       ↓
MarketplaceOrderItem (for each cart item)
       ↓
[POST /api/v1/payments/initiate/]
       ↓
PaymentTransaction → Khalti Gateway
       ↓
[POST /api/v1/payments/callback/] (from Khalti)
       ↓
MarketplaceSale (for each item) ← → PaymentTransactionItem
       ↓
[POST /api/deliveries/create/] OR Management Command
       ↓
Transport.Delivery ← → DeliveryTracking
       ↓
[POST /api/auto-assign/] OR Manual Assignment
       ↓
OrderTrackingEvent & DeliveryTracking Updates
```

### 5.3 Key Tracking Points

1. **Order Level Tracking** (`OrderTrackingEvent`):
   - Order creation, payment confirmation, status changes
   - Links to `marketplace_order` field
   - **API**: `GET /api/v1/marketplace/orders/{id}/`

2. **Sale Level Tracking** (`OrderTrackingEvent`):
   - Individual item processing, seller actions
   - Links to `marketplace_sale` field
   - **API**: `GET /api/marketplace/sales/{id}/`

3. **Delivery Tracking** (`DeliveryTracking`):
   - Physical delivery progress, GPS locations
   - Pickup, transit, and delivery confirmations
   - **API**: `GET /api/deliveries/{tracking_number}/track/`

---

## 6. Complete API Sequence Flow

### 6.1 Step-by-Step Customer Journey

#### Step 1: Create Order
```bash
curl -X POST "http://localhost:8000/api/v1/marketplace/orders/create/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cart_id": 123,
    "delivery_info": {
      "customer_name": "John Doe",
      "phone_number": "+977-9841234567",
      "address": "Thamel, Kathmandu",
      "city": "Kathmandu",
      "state": "Bagmati",
      "zip_code": "44600",
      "latitude": 27.7172,
      "longitude": 85.3240
    }
  }'
```

#### Step 2: Initiate Payment
```bash
curl -X POST "http://localhost:8000/api/v1/payments/initiate/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cart_id": 123,
    "gateway": "KHALTI",
    "return_url": "https://yourapp.com/payment/return",
    "customer_name": "John Doe",
    "customer_email": "john@example.com",
    "customer_phone": "+977-9841234567"
  }'
```

#### Step 3: Payment Callback (Automatic from Khalti)
```bash
# This is called automatically by Khalti
curl -X POST "http://localhost:8000/api/v1/payments/callback/" \
  -H "Content-Type: application/json" \
  -d '{
    "pidx": "khalti_payment_idx_123456",
    "status": "Completed",
    "total_amount": 292500,
    "transaction_id": "khalti_txn_789"
  }'
```

#### Step 4: Create Delivery (Admin/Seller)
```bash
curl -X POST "http://localhost:8000/api/deliveries/create/" \
  -H "Authorization: Bearer ADMIN_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "marketplace_sale_id": 789,
    "pickup_address": "Farm Location, Bhaktapur",
    "pickup_contact_name": "Farmer John",
    "pickup_contact_phone": "+977-9841111111",
    "delivery_address": "Thamel, Kathmandu",
    "delivery_contact_name": "John Doe",
    "delivery_contact_phone": "+977-9841234567",
    "package_weight": 2.5,
    "delivery_fee": 150.00
  }'
```

#### Step 5: Auto-Assign Delivery (Admin)
```bash
curl -X POST "http://localhost:8000/api/auto-assign/" \
  -H "Authorization: Bearer ADMIN_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_id": 101
  }'
```

#### Step 6: Transporter Pickup (Transporter)
```bash
curl -X POST "http://localhost:8000/api/deliveries/f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6/pickup/" \
  -H "Authorization: Bearer TRANSPORTER_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 27.6710,
    "longitude": 85.4298,
    "notes": "Package collected from farm"
  }'
```

#### Step 7: Mark as Delivered (Transporter)
```bash
curl -X POST "http://localhost:8000/api/deliveries/f1g2h3i4-j5k6-l7m8-n9o0-p1q2r3s4t5u6/deliver/" \
  -H "Authorization: Bearer TRANSPORTER_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 27.7172,
    "longitude": 85.3240,
    "notes": "Delivered to customer",
    "customer_rating": 5
  }'
```

#### Step 8: Track Order (Customer)
```bash
curl -X GET "http://localhost:8000/api/v1/marketplace/orders/456/" \
  -H "Authorization: Bearer CUSTOMER_JWT_TOKEN"
```

### 6.2 Seller Management APIs

#### Get Sales List
**Endpoint**: `GET /api/marketplace/sales/`
**Authentication**: Required (Seller)

**Response (200 OK)**:
```json
{
  "count": 10,
  "results": [
    {
      "id": 789,
      "order_number": "MS-20241027-A1B2C3",
      "buyer_name": "John Doe",
      "product": {
        "name": "Organic Rice",
        "price": "1250.00"
      },
      "quantity": 2,
      "total_amount": "2500.00",
      "status": "processing",
      "payment_status": "paid",
      "delivery_status": "assigned",
      "created_at": "2024-10-27T10:45:00Z"
    }
  ]
}
```

#### Mark Sale as Delivered
**Endpoint**: `POST /api/marketplace/sales/{sale_id}/mark-as-delivered/`
**Authentication**: Required (Seller)

**Response (200 OK)**:
```json
{
  "status": "sale marked as delivered",
  "delivered_at": "2024-10-28T16:30:00Z"
}
```

### 6.3 Admin Management APIs

#### Bulk Delivery Operations
**Endpoint**: `POST /api/deliveries/bulk-operations/`
**Authentication**: Required (Admin)

**Request Body**:
```json
{
  "operation": "auto_assign",
  "delivery_ids": [101, 102, 103],
  "parameters": {
    "max_assignments": 10,
    "priority_filter": "high"
  }
}
```

**Response (200 OK)**:
```json
{
  "operation": "auto_assign",
  "results": {
    "successful": 2,
    "failed": 1,
    "assignments": [
      {
        "delivery_id": 101,
        "transporter": "Ram Bahadur",
        "score": 89
      }
    ],
    "failures": [
      {
        "delivery_id": 103,
        "error": "No available transporters"
      }
    ]
  }
}
```

---

## 7. Error Handling & Status Codes

### 7.1 Common HTTP Status Codes

- **200 OK**: Successful request
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request data
- **401 Unauthorized**: Authentication required
- **403 Forbidden**: Permission denied
- **404 Not Found**: Resource not found
- **409 Conflict**: Resource conflict (e.g., already assigned)
- **500 Internal Server Error**: Server error

### 7.2 Payment Error Scenarios

**Payment Initiation Failures**:
```json
{
  "status": "error",
  "message": "Cart is empty",
  "error_code": "EMPTY_CART"
}
```

**Payment Callback Failures**:
```json
{
  "status": "failed",
  "message": "Payment was not successful",
  "data": {
    "khalti_status": "Expired",
    "reason": "Payment timeout"
  }
}
```

### 7.3 Delivery Assignment Errors

**No Available Transporters**:
```json
{
  "success": false,
  "error": "No available transporters found for this delivery",
  "suggestions": [
    "Increase delivery fee",
    "Change priority to urgent",
    "Extend pickup time window"
  ]
}
```

**Transporter Capacity Exceeded**:
```json
{
  "detail": "Package weight exceeds your vehicle capacity",
  "package_weight": 5.5,
  "vehicle_capacity": 3.0
}
```

---

## 8. Database Schema Summary

```sql
-- Core Order Structure
MarketplaceOrder (1) → (N) MarketplaceOrderItem
MarketplaceOrder (1) → (1) DeliveryInfo

-- Payment Processing
PaymentTransaction (1) → (N) PaymentTransactionItem
PaymentTransactionItem (1) → (1) MarketplaceSale

-- Delivery Management
MarketplaceSale (1) → (1) Delivery
Delivery (1) → (N) DeliveryTracking
Delivery (1) → (1) Transporter

-- Tracking Events
OrderTrackingEvent → MarketplaceOrder OR MarketplaceSale
```

### 8.1 Key Model Relationships

```python
# Order System
class MarketplaceOrder:
    customer = ForeignKey(User)
    delivery = ForeignKey(DeliveryInfo)
    items = Reverse ForeignKey(MarketplaceOrderItem)

# Payment System  
class PaymentTransaction:
    user = ForeignKey(User)
    cart = ForeignKey(Cart)
    transaction_items = Reverse ForeignKey(PaymentTransactionItem)

# Sale System
class MarketplaceSale:
    buyer = ForeignKey(User)
    seller = ForeignKey(User)
    product = ForeignKey(MarketplaceProduct)
    delivery_details = OneToOne(Delivery)

# Transport System
class Delivery:
    marketplace_sale = OneToOneField(MarketplaceSale)
    transporter = ForeignKey(Transporter)
    tracking_updates = Reverse ForeignKey(DeliveryTracking)
```

This comprehensive architecture supports the complete e-commerce and delivery workflow with proper API specifications, error handling, and data tracking at every step.