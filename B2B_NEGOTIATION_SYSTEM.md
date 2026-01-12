# B2B Price & Quantity Negotiation System

## Overview
The B2B Price & Quantity Negotiation system allows verified business buyers and sellers to negotiate custom deals for marketplace products. This feature is integrated with the B2B pricing system and the marketplace checkout process.

## 1. Database Schema

### Negotiation Model
Tracks the lifecycle and current state of a negotiation.
- `buyer`: The business user proposing the deal.
- `seller`: The owner of the product (derived from `MarketplaceProduct.product.producer.user`).
- `product`: The specific `MarketplaceProduct` being negotiated.
- `proposed_price`: The latest price offer.
- `proposed_quantity`: The latest quantity offer.
- `status`: `PENDING`, `ACCEPTED`, `REJECTED`, `COUNTER_OFFER`, `ORDERED`.
- `last_offer_by`: Reference to the user who made the last move (used for turn-based enforcement).

### NegotiationHistory Model
Audit trail of every step in the negotiation.
- `negotiation`: FK to parent object.
- `offer_by`: The user who made this specific offer.
- `price`, `quantity`, `message`: Details of the specific offer step.

---

## 2. API Reference

### `GET /api/v1/negotiations/`
List negotiations for the authenticated user.
- **Filters**: `status`, `product_id`.
- **Returns**: List of negotiations where the user is either the buyer or seller.

### `POST /api/v1/negotiations/`
Start a new negotiation.
- **Request Body**:
  ```json
  {
    "product": 1,
    "proposed_price": 450.00,
    "proposed_quantity": 100,
    "message": "Bulk purchase for winter season"
  }
  ```
- **Constraints**:
  - Buyer must be B2B verified.
  - Product must have `enable_b2b_sales=True`.
  - Price cannot exceed listed price.
  - Price must be above the floor limit (default 50% of listed price).
  - Quantity must meet product's `min_order` and be available in stock.

### `GET /api/v1/negotiations/active/?product=<id>`
Helper to find the currently ongoing negotiation between the requester and the seller for a specific product.

### `PATCH /api/v1/negotiations/:id/`
Perform actions (Accept, Reject, Counter).
- **Accept**: Sets status to `ACCEPTED`. Only valid if it's the receiver's turn. Checks stock availability one last time.
- **Reject**: Sets status to `REJECTED`. Ends the negotiation.
- **Counter Offer**: Updates price/quantity and sets status to `COUNTER_OFFER`. Validates turn and price/quantity constraints.

---

## 3. Business Logic & Guardrails

### Turn-Based Enforcement
Users cannot respond to their own offers. If User A (Buyer) sends an offer, only User B (Seller) can Accept or Counter.

### Order Integration
When checking out via the shopping cart, the system checks for `ACCEPTED` negotiations:
1. Validates that the cart quantity is **greater than or equal to** the negotiated quantity.
2. Applies the negotiated price if valid.
3. Upon successful order placement, the negotiation status moves to `ORDERED` to prevent reuse of the same deal for multiple orders.

### Automated Invalidation (Signals)
- **Stock Depletion**: If product stock falls below the negotiated quantity due to other sales, the negotiation is automatically `REJECTED`.
- **Product Policy Changes**: If a seller disables B2B sales or marks a product as unavailable, all associated active negotiations are automatically `REJECTED`.

### Expiration Policy
Negotiations expire after 7 days of inactivity (configurable via `NEGOTIATION_EXPIRY_DAYS`). A periodic task cleans up stale negotiations, and the API checks for expiration on-the-fly.

---

## 4. Notifications
The system triggers in-app notifications via `notify_event` for:
- New Offer (Seller notified)
- Counter Offer (Other party notified)
- Acceptance (Other party notified)
- Rejection (Other party notified)

---

## 5. Security
- **Object-Level Permissions**: Users can only access negotiations they are party to.
- **B2B Walls**: Non-verified users or products not enabled for B2B are strictly blocked from initiating negotiations.
