# Supply Chain Management Platform — Complete Feature Inventory

This document catalogs the features implemented across the repository. It's intended as a technical inventory for product managers, engineers, and technical reviewers.

## Table of Contents
- Marketplace & Product
- Producer / Seller Tools
- Orders, Sales & Checkout
- Payments
- Delivery & Transport
- External Integrations & Webhooks
- B2B / Enterprise Features
- Inventory, Stock & Procurement
- Notifications & Messaging
- Search, Recommendations & Trending
- Media & Shoppable Videos
- Analytics, Reporting & Exports
- Admin & Security
- Background Jobs & Scalability

---

## Marketplace & Product
- Marketplace product creation endpoints (create-from-product, push-to-marketplace). See marketplace API for fields: listed price, discounted price, size, color, min_order, offer windows.
- Marketplace product model supports: bulk_price_tiers, variants, reviews, product images, size/color choices, featured flags, made-in-country flag.
- Marketplace product listing: filtering, category/subcategory/sub_subcategory, brand, SKU, min/max price, size, color.
- Marketplace product paginated list with randomized-first-N ordering to improve variety.
- Marketplace product search using Haystack SearchQuerySet with additional field filters.

## Producer / Seller Tools
- Producer CRUD endpoints (`ProducerViewSet`) and shop-scoped permissions via `user_profile.shop_id`.
- Product CRUD with image prefetching, push-to-marketplace action, update-stock action, category/size/color choices endpoints.
- StockList management and push-to-marketplace actions for bulk items.
- CreatorProfile and social follow features: follow/unfollow, followers/following lists, videos by creator.

## Orders, Sales & Checkout
- Order and Sale ViewSets with shop-scoped querysets and status updates.
- Create/retrieve/update order operations, update status with transactional stock decrement on delivery.
- Marketplace orders: create, cancel, reorder, seller order listing, order detail endpoints.

## Payments
- Payment models and verification flows for multiple gateways: eSewa and Khalti integrations included (init + verify endpoints).
- Payment confirmation and payment flow handling (redirects, verification, SMS hooks).
- Payment endpoints under `payment` app (see `main/urls.py` inclusion).

## Delivery & Transport
- Delivery creation API supports deliveries created from cart, sale, marketplace_sale, marketplace_order.
- `DeliveryViewSet` supports update-status action, tracking numbers, delivery person assignment, estimated/actual delivery dates.
- Transport app provides delivery history, accept/acceptance endpoints, update-status, tracking endpoints, ratings and reviews for deliveries.
- Delivery platform exposes analytics endpoints: delivery trends, efficiency metrics, auto-assignment, bulk operations, suggestions.

## External Integrations & Webhooks
- Dedicated external delivery integration app with multi-tenant `ExternalBusiness` model, API key & secret, webhook URL/secret.
- Middleware for external API authentication, HMAC signature validation, rate limiting, quota enforcement, request size limits.
- Webhook sending with retry, WebhookLog model, configurable timeout/max-retries and backoff delays.

## B2B / Enterprise Features
- Comprehensive B2B pricing system: per-product B2B enablement, B2B price tiers, tiered quantity discounts, min-quantity requirements.
- Business verification (tax ID, business type), business profiles with `credit_limit`, `available_credit`, `payment_terms_days`.
- B2B pricing and credit APIs:
  - GET product B2B pricing: `/api/v1/producer/products/{id}/b2b-pricing/`
  - POST calculate order pricing (bulk): `/api/v1/producer/calculate-order-pricing/`
  - GET/POST credit management endpoints: `/api/v1/user/b2b-credit/` and `/api/v1/user/b2b-credit/apply/`
- Administrative credit limit update endpoints for staff.

## Inventory, Stock & Procurement
- `StockHistory` model: immutable records (soft-delete by superuser), stock_in/stock_out tracking.
- `StockList` for bulk stock items and marketplace push operations.
- Purchase Orders, Procurement Request/Response serializers and endpoints (procurement flows present in `producer` app).
- Ledger entries, reconciliation endpoints and audit logs for accounting and traceability.

## Notifications & Messaging
- Notification model and API for listing and marking as read.
- Notification tasks via Celery: scheduled notifications, retry failed notifications, cleanup tasks, analytics generation.
- Signals create notifications on marketplace events (orders, sales, stocklist pushes, PO events).
- SMS integration hooks used after payment verification.

## Search, Recommendations & Trending
- Haystack-powered search with advanced field filtering and caching of search results.
- Trending products and recommendation endpoints (TrendingProductsViewSet, MarketplaceUserRecommendedProductViewSet).
- Recommendation/recommender utilities present (`recommendation.py`) and test coverage for recommendation behavior.

## Media & Shoppable Videos
- Shoppable videos model and API endpoints. Creators can upload videos tied to products.
- CreatorProfile, follow relationships and APIs to list creator videos.

## Analytics, Reporting & Exports
- Dashboard endpoints aggregate product, order, sale counts and monthly trends.
- Daily product stats with Excel export via `openpyxl` (`export_queryset_to_excel` utility used across views).
- Delivery analytics endpoints in transport app (delivery trends, efficiency metrics).

## Admin & Security
- Admin UI enhancements for B2B fields, B2B price tiers, user verification and credit management.
- Middleware for security: request size limiting, API quota enforcement, external API auth, and security headers.
- Role-based access: endpoints restrict to `IsAuthenticated`, staff, or superuser where necessary.

## Background Jobs & Scalability
- Celery tasks for notifications, webhooks, delivery reminders, and background analytics.
- Caching (Django cache) for list & search endpoints with TTL configuration options (`PRODUCER_LIST_CACHE_TTL`, `PRODUCER_SEARCH_CACHE_TTL`).
- Pagination (DRF PageNumberPagination) used widely with `page_size` controls.

## Other Notable Features
- Voice search utilities and guides (`VOICE_SEARCH_GUIDE.md`) — voice query support and mapping.
- Mobile authentication documentation and endpoints (`MOBILE_AUTH_DOCUMENTATION.md`).
- Export utilities (Excel) and data dumps for offline reporting.
- Tests: Many unit and integration tests across apps (`market`, `producer`, `notification`, `transport`), including test factories.

---

## Where to find implementation
- Core marketplace and producer features: [producer/views.py](producer/views.py)
- Marketplace endpoints, deliveries, payments: [market/views.py](market/views.py)
- Delivery platform and external integration: [external_delivery/README.md](external_delivery/README.md) and [DELIVERY_API_PLATFORM_GUIDE.md](DELIVERY_API_PLATFORM_GUIDE.md)
- B2B pricing: [B2B_PRICING_SYSTEM_DOCUMENTATION.md](B2B_PRICING_SYSTEM_DOCUMENTATION.md) and services in `producer/services.py`
- Notifications: [notification/](notification/)
- Transport/delivery analytics: [transport/](transport/)

---

This file is a living inventory. If you want, I can expand any section with endpoint samples, model fields, or sequence diagrams for specific flows (order -> payment -> delivery, or external delivery integration).

