**B2B API Reference**

Summary
- Provides endpoints to list B2B-verified users and fetch products belonging to B2B-verified users.
- Endpoints are optimized with `select_related` / `prefetch_related` to avoid N+1 queries and are paginated.

Base path
- All endpoints are mounted under `/api/v1/`.

Endpoints

- **List B2B users**
  - URL: `/api/v1/b2b-verified-users-products/` (router-registered ReadOnlyModelViewSet)
  - Method: `GET`
  - Purpose: Return users whose `user_profile.b2b_verified == True`.
  - Query params:
    - `q` (optional): search by username, first_name, last_name, registered_business_name, or business_type.
    - `page` / `page_size` (pagination)
  - Response: paginated list of users. Each user includes fields from `B2BUserProductsSerializer`:
    - `id`, `username`, `first_name`, `last_name`, `email`, `registered_business_name`, `business_type`.

- **Get single B2B user**
  - URL: `/api/v1/b2b-verified-users-products/{pk}/`
  - Method: `GET`
  - Purpose: Return single B2B user detail (same serializer as list).

- **List products for a B2B user (detail action)**
  - URL: `/api/v1/b2b-verified-users-products/{pk}/products/`
  - Method: `GET`
  - Purpose: Return paginated products for the requested B2B-verified user.
  - Query params:
    - `q` (optional): search product `name` or `sku`.
    - `page` / `page_size` (pagination)
  - Response: paginated list of products using `MiniProductSerializer` (lightweight):
    - `id`, `name`, `brand_name`, `price`, `thumbnail`, `category_info`.

Notes on performance
- The viewset prefetches related `Product` objects into a `prefetched_products` attribute, and the `products` action uses that when available to avoid per-user queries (eliminates N+1).
- Product lists use `select_related("brand", "user")` and `prefetch_related("images")` to fetch related data in a small number of queries.

Examples

- List B2B users (first page):

```bash
curl -s "https://<your-host>/api/v1/b2b-verified-users-products/?page=1&page_size=20"
```

- Get products for user with id 123 (search for "soap"):

```bash
curl -s "https://<your-host>/api/v1/b2b-verified-users-products/123/products/?q=soap&page=1&page_size=24"
```

Sample product item (MiniProductSerializer):

```json
{
  "id": 987,
  "name": "Handmade Soap",
  "brand_name": "Nepal Naturals",
  "price": 4.5,
  "thumbnail": "https://<host>/media/product_images/abc.jpg",
  "category_info": { "id": 12, "name": "Personal Care" }
}
```

Authentication & ACL
- Current views are configured with `AllowAny`. If you require authentication or role-based access, change `permission_classes` to `IsAuthenticated` or custom permissions.

Recommendations
- Consider adding caching (per-page) for high-traffic endpoints.
- If clients only need product data, use the `/.../{pk}/products/` action directly instead of listing users then fetching products.

References
- Implementation: `user/b2b_api.py`
- Lightweight product serializer: `producer/serializers.py` (`MiniProductSerializer`)

Recent additions (Dec 2025)
- **Seller-level chat (seller-chats)**: A new model `SellerChatMessage` was added to support seller/user-level conversations across a seller's products. Key files:
  - Model: `market/models.py` (`SellerChatMessage`)
  - Serializer: `market/serializers.py` (`SellerChatMessageSerializer`)
  - ViewSet & route: `market/views.py` (`SellerChatMessageViewSet`) registered as `/api/v1/seller-chats/`
  - Access: Messages are scoped so users only see messages where they are the sender or the `target_user`. Use `?direction=inbox` for incoming messages or `?direction=sent` for sent messages.

- **Per-product chat under B2B user route**: Added a detail action on the B2B users viewset to list/create product-specific chats for a product belonging to a B2B user:
  - URL (list): `/api/v1/b2b-verified-users-products/{user_pk}/products/{product_id}/chat/` (GET)
  - URL (create): same path (POST) — authenticated users only
  - Serializer: reuses `market/serializers.ChatMessageSerializer` for product-level chats (notifications to product owner are preserved).

Usage examples
- List seller inbox messages (authenticated):

```bash
curl -H "Authorization: Token <token>" \
  "https://<host>/api/v1/seller-chats/?direction=inbox"
```

- Send a product chat message to a B2B user's product:

```bash
curl -X POST -H "Authorization: Token <token>" -H "Content-Type: application/json" \
  -d '{"message":"Hi, is this available in bulk?"}' \
  "https://<host>/api/v1/b2b-verified-users-products/123/products/987/chat/"
```

Notes
- The `SellerChatMessage` model requires a migration; run `python manage.py makemigrations market` and `python manage.py migrate` to apply.
- Permissions: endpoints default to `IsAuthenticated` for chat creation and access. Review and adjust as needed for your app's policies.

Product-level chats
- **ProductChatMessage**: new model to attach chats directly to the `Product` model (not `MarketplaceProduct`). Useful when conversations belong to the underlying product regardless of marketplace listings.
  - Model: `market/models.py` (`ProductChatMessage`)
  - Serializer: `market/serializers.py` (`ProductChatMessageSerializer`)
  - ViewSet & route: `market/views.py` (`ProductChatMessageViewSet`) registered as `/api/v1/product-chats/`
  - Querying: use `?product_id=<id>` to list messages for a specific `Product`.

Migration reminder: After pulling these changes, run:

```bash
python manage.py makemigrations market
python manage.py migrate
```
