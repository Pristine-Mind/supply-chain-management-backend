**Creators & Shoppable Videos — Frontend Integration Guide**

Overview
- Purpose: document backend changes, endpoints, payloads, and frontend integration notes for Creator profiles and Shoppable Video features implemented in the backend.
- Relevant changed files: [producer/views.py](producer/views.py), [market/serializers.py](market/serializers.py), [market/models.py](market/models.py), [producer/signals.py](producer/signals.py), [main/urls.py](main/urls.py)

Key model changes (backend)
- `ShoppableVideo`: `uploader` is now nullable (SET_NULL). A new FK `creator_profile` links a `CreatorProfile` to a video for creator-owned content. Validation enforces at least one of `uploader` or `creator_profile` be present.
- `CreatorProfile`: OneToOne to `User` (already present); new API endpoints expose profile data and follow lists.
- `AffiliateClick`: logging created for affiliate redirect clicks (indexed for performance).

Primary endpoints (summary)
- GET /api/v1/creators/
  - Purpose: list creators; supports `?q=` search over `handle`, `display_name`, `username`.
  - Auth: allow any
  - Pagination: standard DRF pagination

- GET /api/v1/creators/{id}/
  - Purpose: retrieve creator profile
  - Auth: allow any

- GET /api/v1/creators/{id}/followers/
  - Purpose: list followers for creator (optimized server-side to avoid N+1 queries)
  - Auth: allow any

- GET /api/v1/creators/{id}/following/
  - Purpose: list creators the given creator follows (optimized)
  - Auth: allow any

- GET /api/v1/creators/{id}/videos/
  - Purpose: list paginated `ShoppableVideo` entries for this creator (videos where `creator_profile` == creator OR `uploader` == creator.user)
  - Auth: allow any
  - Notes: server prefetches `creator_profile` and `uploader` to avoid extra DB hits; use pagination.

- GET /api/v1/creators/me_following/
  - Purpose: list creators the authenticated user follows
  - Auth: authenticated

- POST /api/v1/creators/{id}/follow/
  - Purpose: toggle follow/unfollow for authenticated user (returns updated follower_count)
  - Auth: authenticated

- GET /api/v1/affiliate/redirect/?click_id=... OR ?post_id=...&product_id=...
  - Purpose: logs affiliate click (`AffiliateClick`) and issues 302 redirect to affiliate URL
  - Auth: allow any
  - Note: frontend should simply follow the Location header; do not attempt to fetch the target URL from frontend due to CORS/behavior differences.

Shoppable video endpoints / actions (on existing viewset)
- GET /api/v1/shoppable-videos/{id}/product-tags/ (list tags)
- POST /api/v1/shoppable-videos/{id}/product-tags/ (add tag)
- POST /api/v1/shoppable-videos/{id}/view/ (increment views)
  - Side effect: increments `ShoppableVideo.views_count` and `CreatorProfile.views_count` if linked.

Important response fields (Shoppable Video serializer)
- `uploader_profile` / `uploader_profile_url` — read-only nested profile info + link used in UI to open uploader profile
- `creator_profile` — nested creator profile data when attached
- `product_tags` — array of product tag objects for overlay hotspots

Frontend integration recommendations
- Pagination: always respect the DRF pagination metadata (next/previous/count); do not attempt to fetch all items in one request.
- Profile pages
  - Fetch `/api/v1/creators/{id}/` for profile header (bio, handle, stats).
  - Use `/api/v1/creators/{id}/videos/` for the creator's media grid; use server paging.
- Follow button
  - Use optimistic UI update: toggle follower_count locally on success; show spinner while awaiting POST to `/creators/{id}/follow/`.
  - Handle 401s by redirecting to login.
- Video views
  - When a video is shown or its playback starts, call `/shoppable-videos/{id}/view/` (POST) once per view session to increment server counters.
  - To avoid double-counting, track in localStorage or session whether the current user has already counted this view in the session.
- Affiliate links
  - For product affiliate clicks, navigate the browser to the affiliate redirect URL returned by the API call (or simply link directly to the API redirect URL). Expect a 302 redirect response.
  - Do not attempt to fetch the redirect target with XHR (CORS and safe redirect behavior). Use window.location or an anchor with `rel="noopener noreferrer"`.
- N+1 concerns
  - Creator follow lists are optimized server-side; if the frontend requires additional nested fields (e.g., avatar, stats), notify backend owners to prefetch those fields in `ProducerProfileViewSet`.
- Caching & invalidation
  - Many list endpoints are cached briefly server-side; after performing an action that mutates lists (follow/unfollow, create video), consider invalidating client caches or refetching key endpoints.

Example requests
- List a creator's videos (page 1):
  curl 'http://localhost:8000/api/v1/creators/42/videos/?page=1'

- Follow a creator (authenticated):
  curl -X POST -u user:pass 'http://localhost:8000/api/v1/creators/42/follow/'

- Open an affiliate redirect (browser link):
  <a href="/api/v1/affiliate/redirect/?post_id=123&product_id=456">Buy</a>

Developer notes & next steps
- Run migrations locally before starting the server to pick up model changes (new FK, nullable fields).
  ```bash
  python manage.py makemigrations market producer
  python manage.py migrate
  ```
- Tests: run the test suite to catch integration issues:
  ```bash
  python manage.py test -q
  ```
- If the frontend needs additional fields on `ShoppableVideoSerializer`, list them so backend can prefetch/annotate and avoid N+1 queries (e.g., `product` details referenced by tags).

Contact
- For backend questions, see the implementation in [producer/views.py](producer/views.py) and [market/serializers.py](market/serializers.py).
 
Example request / response payloads
---------------------------------

1) List creators

Request:
```bash
GET /api/v1/creators/?q=alice&page=1
Accept: application/json
```

Response (200):
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 42,
      "user": 101,
      "handle": "alice_shop",
      "display_name": "Alice",
      "bio": "Curated fashion and accessories",
      "follower_count": 1200,
      "views_count": 53400,
      "profile_url": "/creators/42/"
    },
    {
      "id": 43,
      "user": 102,
      "handle": "alice_home",
      "display_name": "Alice Home",
      "bio": "Handmade homewares",
      "follower_count": 300,
      "views_count": 12000,
      "profile_url": "/creators/43/"
    }
  ]
}
```

2) Retrieve creator profile

Request:
```bash
GET /api/v1/creators/42/
Accept: application/json
```

Response (200):
```json
{
  "id": 42,
  "user": 101,
  "handle": "alice_shop",
  "display_name": "Alice",
  "bio": "Curated fashion and accessories",
  "follower_count": 1200,
  "views_count": 53400,
  "social_links": {
    "instagram": "https://instagram.com/alice_shop"
  },
  "profile_image": "/media/avatars/alice.jpg"
}
```

3) Creator videos (paginated)

Request:
```bash
GET /api/v1/creators/42/videos/?page=1
Accept: application/json
```

Response (200):
```json
{
  "count": 125,
  "next": "/api/v1/creators/42/videos/?page=2",
  "previous": null,
  "results": [
    {
      "id": 9001,
      "title": "Spring lookbook",
      "video_url": "/media/videos/9001.mp4",
      "thumbnail": "/media/videos/thumbs/9001.jpg",
      "uploader_profile": {
        "id": 42,
        "handle": "alice_shop",
        "profile_url": "/creators/42/"
      },
      "creator_profile": {
        "id": 42,
        "handle": "alice_shop"
      },
      "product_tags": [
        {"id": 1, "product_id": 200, "x": 0.42, "y": 0.63, "label": "Jacket"}
      ],
      "views_count": 1200,
      "created_at": "2025-12-01T10:23:00Z"
    }
  ]
}
```

4) Follow / unfollow a creator

Request (authenticated):
```bash
POST /api/v1/creators/42/follow/
Authorization: Token <user-token>
Accept: application/json
```

Response (200) - success toggle:
```json
{
  "following": true,
  "follower_count": 1201
}
```

5) Increment video view

Request (client-side when playback starts):
```bash
POST /api/v1/shoppable-videos/9001/view/
Content-Type: application/json
```

Response (200):
```json
{
  "id": 9001,
  "views_count": 1201
}
```

6) Affiliate redirect (browser navigation)

Request (user clicks link):
```text
GET /api/v1/affiliate/redirect/?post_id=123&product_id=456
```

Server behavior / Response:
- Logs an `AffiliateClick` record and issues a 302 redirect to the affiliate `target_url`.
- The browser receives a 302 with `Location` header pointing to the affiliate partner URL and follows it.

Example raw response headers:
```
HTTP/1.1 302 Found
Location: https://affiliate.partner/track?ref=abc123
Content-Type: text/html; charset=utf-8

```

7) Product tags (list / create)

List tags (GET):
```bash
GET /api/v1/shoppable-videos/9001/product-tags/
```

Response (200):
```json
[
  {"id": 1, "product_id": 200, "x": 0.42, "y": 0.63, "label": "Jacket"}
]
```

Create tag (POST):
```bash
POST /api/v1/shoppable-videos/9001/product-tags/
Content-Type: application/json

{
  "product_id": 200,
  "x": 0.42,
  "y": 0.63,
  "label": "Jacket"
}
```

Response (201):
```json
{
  "id": 2,
  "product_id": 200,
  "x": 0.42,
  "y": 0.63,
  "label": "Jacket"
}
```
