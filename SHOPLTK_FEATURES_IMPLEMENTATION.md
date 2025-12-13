# Shopltk (LTK) Feature Extraction & Implementation Plan for Shopable

Purpose
-------
This document extracts high-impact features from Shopltk (shopltk.com) and translates them into concrete, prioritized implementation steps you can apply to our `Shopable` section. It includes feature descriptions, data model proposals, API contracts, UI behavior, infra considerations, metrics to track, and an initial sprint roadmap.

Feature Summary
---------------
- Creator-Centric Feed: Creator profiles, follow system, and personalized feed of creator posts.
- Shoppable Posts: Posts (images/videos) tagged with multiple products; clicking a tag opens product details or redirects to merchant with affiliate tracking.
- Video & Watch Experience: Short-form video feed with timecoded product overlays.
- Discovery & Curations: Category pages, seasonal/trend collections, and curated landing pages.
- Saved Lists / Collections: Save items and create public/private collections.
- Affiliate Link Handling: Centralized affiliate parameter appending and redirect tracking for monetization.
- Search & Filters: Product/brand search, category filters, hashtags.
- Brand & Creator Pages: Aggregated content and product lists per brand/creator.
- Analytics & Reporting: Creator performance, CTR, conversion, revenue attribution.

Mapping to Our Codebase
-----------------------
- Primary areas to extend:
  - `producer/` — creator content, posts, media tasks
  - `market/` — product models, product-collection mapping, shoppable view logic
  - `notification/` — impressions, click events, creator alerts
- Tests to reference: `market/test_shoppable_videos.py`, `producer/test_shoppable_videos.py`

High-Priority Features (what to build first)
-------------------------------------------
1) Shoppable Posts (MVP)
   - Allow images & videos to include multiple `ProductTag`s.
   - Rapid wins: image pins + product modal -> external merchant link with affiliate params.

2) Creator Profiles & Follow Feed
   - Follow/unfollow creators, follow-feed endpoint, creator profile aggregation.

3) Collections / Saved Items
   - Allow users to save items to personal collections and share collections.

4) Shoppable Video (phase 1)
   - Timecode-tagged products, player overlay, pause-to-open modal UX.

5) Affiliate Link Builder & Redirect
   - Abstraction for building affiliate links, redirect endpoint to record clicks.

Data Model Proposals (concise)
------------------------------
- ProductTag (new)
  - id: PK
  - post: FK -> Post
  - product: FK -> Product
  - x: Float (0–1) — relative horizontal position
  - y: Float (0–1) — relative vertical position
  - width: Float (0–1) nullable
  - height: Float (0–1) nullable
  - timecode: Float nullable (seconds into video)
  - label: Char
  - merchant_url: URL
  - affiliate_meta: JSON (partner id, params)
  - created_at

- Follow
  - follower: FK -> User
  - creator: FK -> User (or CreatorProfile)
  - created_at

- Collection
  - owner: FK -> User
  - title: Char
  - visibility: Enum (private/public)
  - items: M2M -> Product

- AffiliateClick
  - user (nullable), product, post (nullable), redirect_url, affiliate_meta, ip, user_agent, created_at

API Contracts (examples)
------------------------
- POST /api/posts/
  - payload: { media_url, caption, product_tags: [{product_id, x, y, width, height, timecode, label}] }
  - response: post with nested `product_tags`

- GET /api/posts/{id}/
  - response: { id, media_url, caption, product_tags: [...] }

- GET /api/feed/following/?page=
  - returns feed of posts from followed creators (paginated)

- POST /api/creators/{id}/follow
  - body: {}
  - response: success, follower count

- GET /api/affiliate/redirect/?click_id={}
  - Server resolves affiliate url, logs AffiliateClick, redirects (302)

Frontend / UX Patterns
----------------------
- Image pins: small tappable hotspots that expand to a product card/modal (title, price, merchant, buy button).
- Video overlays: transient overlay when timecode reached; allow pin to persist on tap.
- Creator profile: header info + grid/vertical feed of posts; follow button in prominent position.
- Feed ordering: recency + engagement; support local / interest filters.

Infra & Operational Notes
-------------------------
- Use CDN for media and pre-generate thumbnails (image sizes + video poster frames).
- Video processing: use a transcoding pipeline (e.g., AWS Elastic Transcoder / MediaConvert) to produce mobile-optimized variants.
- For search and trending pages, consider Algolia/Elasticsearch once scale demands.
- Background tasks: reuse Celery tasks in `producer/tasks.py` for thumbnailing, link validation, indexing.

Analytics & Metrics
-------------------
- Track: impressions (post + tag), clicks (tag -> affiliate redirect), saved-item events, purchases (if available via partner callbacks).
- KPIs: CTR of product pins, conversion rate, revenue per creator, retention by saved-list usage.

Implementation Roadmap (6 sprints)
---------------------------------
- Sprint 0 — Discovery & schema design
  - Audit `market/models.py` and `producer/models.py` for existing Post/Product relations.
  - Create migrations for `ProductTag` and `Follow` models.
- Sprint 1 — Shoppable Posts MVP
  - Implement `ProductTag` model, API to add tags to posts, image pin UI, product modal.
- Sprint 2 — Creator Follow & Feed
  - Implement `Follow` model, feed endpoint, follow/unfollow UI, basic notifications.
- Sprint 3 — Collections / Saved
  - Implement `Collection` model and endpoints, add save UI for product cards, exportable lists.
- Sprint 4 — Shoppable Video
  - Add `timecode` support, player overlays, video tag UI, CDN optimizations.
- Sprint 5 — Affiliate & Analytics
  - Implement affiliate redirect service and `AffiliateClick` logging, creator dashboards, automated reports.

Detailed Spec (Top 3 items)
---------------------------
1) Shoppable Posts
  - Model: `ProductTag` (see model proposal)
  - API: Accepts `product_tags` on post create/update; returns enriched post data.
  - Behavior: Clicking a pin opens product modal with `Buy` -> `/api/affiliate/redirect/?post={}&product={}`.
  - Tests: Create post with tags; assert pins returned; clicking increments impression; redirect logs click.

2) Creator Follow & Feed
  - Model: `Follow` (see above)
  - API: Follow/unfollow endpoints and `GET /api/feed/following/` paginated.
  - Behavior: Feed merges posts from followed creators sorted by recency + engagement.
  - Tests: Follow/unfollow flow; feed shows correct posts.

3) Shoppable Video (phase 1)
  - Model: reuse `ProductTag.timecode` for video tags.
  - Player behavior: At timecode, show overlay; allow tap-to-open modal (pause on open).
  - Tests: Verify overlay appears at timecode; clicking opens modal and logs impression.

Risk & Dependencies
-------------------
- Video transcoding and CDN costs/ops are a dependency.
- Affiliate integrations require partner configs and QA.
- Search/trending scalability may require an external index.

Next Immediate Steps (pick one)
------------------------------
1. Implement `ProductTag` model + migrations and a minimal API (fast path to shoppable content).
2. Implement `Follow` model + feed endpoint (fast engagement uplift).
3. Implement affiliate redirect endpoint + click logging (monetization plumbing).

If you want, I can open a PR that adds the `ProductTag` model and corresponding tests.

---
Generated on: 2025-12-13
