# Distributor API

This document describes the distributor-facing API endpoints added to the marketplace app. It includes request/response examples, authorization, and notes about invoice generation.

**Base auth**: endpoints require authentication (session cookie or token). The requesting user must be a distributor (checked via `user.user_profile.is_distributor()`).

---

## Endpoints

### 1) GET /api/v1/distributor/profile/
- Description: Returns the distributor's products insights and the number of marketplace orders containing their items.
- Auth: Required (distributor)

Sample response (200):

```json
{
  "products": [
    {
      "id": 123,
      "name": "Turmeric 1kg",
      "views": 45,
      "bids": 3,
      "total_sold": 120,
      "avg_rating": 4.5
    },
    {
      "id": 456,
      "name": "Cumin 500g",
      "views": 12,
      "bids": 0,
      "total_sold": 5,
      "avg_rating": 0.0
    }
  ],
  "orders_count": 7
}
```

Errors:
- 403: {"error": "User is not a distributor"}

---

### 2) GET /api/v1/distributor/orders/
- Description: Lists marketplace orders that include this distributor's products. Each order contains only the items that belong to the requesting distributor.
- Auth: Required (distributor)

Query params: none implemented (returns recent 50 by default).

Sample response (200):

```json
[
  {
    "id": 10,
    "order_number": "MP-20250101-AB12CD34",
    "customer": "buyer_username",
    "created_at": "2025-01-01T12:34:56Z",
    "order_status": "confirmed",
    "payment_status": "paid",
    "seller_items": [
      {
        "id": 201,
        "product_id": 123,
        "product_name": "Turmeric 1kg",
        "quantity": 10,
        "unit_price": 250.0,
        "total_price": 2500.0
      }
    ],
    "total_amount": 3500.0
  }
]
```

Errors:
- 403: {"error": "User is not a distributor"}

---

### 3) GET /api/v1/distributor/orders/<pk>/invoice/
- Description: Generate or return the invoice PDF for the specified `MarketplaceOrder` if the requesting distributor has at least one item in that order.
- Auth: Required (distributor)
- Response: `application/pdf` file download (File response) or JSON with an error/message.

Behavior notes:
- If the order already has an associated `Invoice` with a PDF file, that file is returned.
- If no invoice exists, the server attempts to create one using `InvoiceGenerationService.create_invoice_from_marketplace_order(order)`.
- Invoice generation requires the order to be paid (`order.is_paid`) OR the order must have `requires_invoice=True`. Otherwise invoice creation raises an error.
- PDF generation requires ReportLab (the code checks `PDF_AVAILABLE`). If ReportLab is not installed, invoice JSON will still be created but PDF may not be available.

Success responses:
- 200 (application/pdf): raw PDF stream (downloadable)
- 200 (application/json): {"message": "Invoice generated but PDF not available."} (if PDF generation not available)

Error responses:
- 404: {"error": "Order not found"}
- 403: {"error": "You don't have permission to view invoice for this order."}
- 400: {"error": "<reason>"} (e.g., invoice creation failure)

Example: request header to prefer PDF

```bash
curl -i -H "Authorization: Token <TOKEN>" \
     -H "Accept: application/pdf" \
     https://your-host/api/v1/distributor/orders/10/invoice/ -o invoice-10.pdf
```

If the API returns JSON with a message, download is not available.

---

## cURL Examples

1) Get distributor profile

```bash
curl -H "Authorization: Token <TOKEN>" \
     https://your-host/api/v1/distributor/profile/
```

2) List distributor orders

```bash
curl -H "Authorization: Token <TOKEN>" \
     https://your-host/api/v1/distributor/orders/
```

3) Fetch invoice PDF for order `10` (save to file)

```bash
curl -H "Authorization: Token <TOKEN>" \
     -H "Accept: application/pdf" \
     https://your-host/api/v1/distributor/orders/10/invoice/ -o invoice-10.pdf
```

---

## Implementation notes for engineers

- Views are implemented in `market/views.py` as `DistributorProfileView`, `DistributorOrdersView`, and `DistributorOrderInvoiceView`.
- Invoice generation is in `market/services.py` via `InvoiceGenerationService.create_invoice_from_marketplace_order(...)`.
- PDF generation uses ReportLab. To enable PDF generation, add `reportlab` to your environment:

```bash
pip install reportlab
```

- Permission check: views use `user.user_profile.is_distributor()`; ensure `user_profile` exists and the method is available.
- The invoice service will attach a PDF to `Invoice.pdf_file` when `PDF_AVAILABLE` is True.

---

## Troubleshooting

- If you get `403` but the user should be a distributor, check `user.user_profile.business_type` and the `is_distributor()` implementation.
- If invoice creation raises errors, check order payment state and `requires_invoice` flag.
- If PDF is not generated, confirm `reportlab` is installed and `PDF_AVAILABLE` is True in `market/services.py`.

---

If you want, I can:
- add example responses into the project OpenAPI schema,
- add automated tests for these endpoints, or
- create a Postman collection / OpenAPI snippet for easy import.
