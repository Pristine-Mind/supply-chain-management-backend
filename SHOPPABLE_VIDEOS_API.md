# Shoppable Videos API & Recommendation Engine

## Overview
The Shoppable Videos feature allows users to browse a TikTok-style feed of short videos linked to marketplace products. The feed is personalized using a sophisticated recommendation engine that learns from user interactions (likes, saves, shares, views).

## Data Models

### ShoppableVideoCategory
- **name**: Category name (e.g., "Fashion", "Tech").
- **icon**: Category icon image.
- **order**: Display order.
- **is_active**: Status of the category.

### ShoppableVideo
- **content_type**: Type of content (`VIDEO`, `IMAGE`, `COLLECTION`).
- **product**: Link to `MarketplaceProduct` (Primary product).
- **category**: Link to `ShoppableVideoCategory`.
- **additional_products**: Many-to-Many link to `MarketplaceProduct` (Other featured items).
- **video_file**: The video media file (for `VIDEO` type).
- **image_file**: Single high-res image (for `IMAGE` type).
- **items**: List of images/videos for a carousel (for `COLLECTION` type).
- **title**: Title of the content.
- **tags**: List of tags (e.g., ["tech", "gadgets"]).
- **trend_score**: A float score indicating current popularity.
- **metrics**: `views_count`, `likes_count`, `shares_count`.

### ShoppableVideoItem
- **video**: Parent `ShoppableVideo` content.
- **file**: Media file (image or video).
- **order**: Display order in carousel.
- **thumbnail**: Thumbnail for item (if needed).

### Social & Moderation Models
- **VideoComment**: User comments on videos, supports threaded replies.
- **VideoReport**: User reports for inappropriate content (spam, harassment, etc.).
- **UserFollow**: Follow relationship between users (buyers following creators/sellers).

### User Interactions
- **VideoLike**: Records when a user likes a video.
- **VideoSave**: Records when a user saves a video for later.
- **UserInteraction**: Logs generic events like `product_view` and `add_to_cart_from_video` which feed into the recommendation engine.

## Recommendation Algorithm

The personalized feed is generated via a 4-stage process:

### 1. User Profiling
We derive a user's interest profile based on:
- **Explicit Signals**: Liked videos, Saved videos, Followed creators.
- **Implicit Signals**: Product views, Add to cart actions, and **Dwell Time** (passive watch time).
- **Time Decay**: Recent interactions are weighted higher than old ones ($W = 1 / (days\_since + 1)$).
- **Session Reactivity**: Real-time intent is captured within the browsing session and applies a **5.0x boost** to active categories.

### 2. Candidate Generation
We select a pool of potential videos (~50-100) from:
- **Interest-based**: Videos matching the user's preferred categories.
- **Following**: Videos from creators the user follows.
- **Similarity**: Content-based filtering via tag overlap.
- **Trending**: High `trend_score` videos (for discovery).
- **Recency**: New uploads (to solve the cold-start problem).

### 3. Scoring
Each candidate video is assigned a relevance score:
$$ Score = S_{category} + S_{tags} + S_{engagement} + S_{trend} + S_{random} + S_{freshness} $$

- **Category Match**: +2.0 points (multiplied by session boost).
- **Tag Match**: +1.5 points per matching tag.
- **Engagement**: Weighted sum of interactions ($0.01 \times views + 1.0 \times likes + 1.2 \times shares$).
- **Freshness**: +1.0 point if content is < 24 hours old.
- **Trend**: $4.0 \times trend\_score$.
- **Randomness**: Small random factor (0-0.5) for variety.

### 4. Diversity & Discovery
The feed uses a **60/20/20** ratio:
- 60% Interest Matches (Personalized).
- 20% Global Trending.
- 20% Pure Discovery (New content/Exploration).

## API Endpoints

Base URL: `/api/v1/`

### 1. Shoppable Videos (`/shoppable-videos/`)

#### Get Video Feed
**GET** `/?category={id}`
Returns a personalized list of videos. Optional `category` ID parameter to filter by a specific video category.

**Response:**
```json
[
  {
    "id": 1,
    "category": 2,
    "category_details": {
      "id": 2,
      "name": "Fashion",
      "icon": "http://.../icon.png"
    },
    "title": "Summer Outfit Haul",
    "video_file": "http://.../video.mp4",
    "product": { "id": 101, "name": "Summer Dress", "price": 199.99 },
    "additional_products": [
        { "id": 102, "name": "Sun Hat", "price": 49.99 }
    ],
    "likes_count": 150,
    "is_liked": true,
    "is_saved": false,
    "trend_score": 0.85
  },
  ...
]
```

#### Upload Content (Video or Image)
**POST** `/`
- **content_type**: `VIDEO`, `IMAGE`, or `COLLECTION`.
- **video_file**: File (if type is `VIDEO`).
- **image_file**: File (if type is `IMAGE`).
- **product_id**: ID of the primary product.
- **...other metadata fields...**

#### Add Item to Collection
**POST** `/{id}/add-item/`
Add a media file to a carousel/collection content.
- **file**: Image or video file.
- **order**: Display order.

#### Like / Unlike
**POST** `/{id}/like/`
Toggles the like status.

#### View (Optimized)
**POST** `/{id}/view/`
Increments the view counter. Optimized using atomic database updates to handle high concurrency.

#### Track Interaction (Advanced)
**POST** `/{id}/track-interaction/`
Log detailed behavioral signals for the recommendation engine.
- **event_type**: `watch_time`, `cta_click`, `scroll_pause`.
- **dwell_time**: Duration in seconds (for `watch_time`).
- **extra_data**: JSON object for additional context.

#### More Like This (Similarity)
**GET** `/{id}/more-like-this/`
Returns content with similar tags and categories.

#### People Also Watched (Collaborative)
**GET** `/{id}/also-watched/`
Returns content based on the behavior of other users with similar interests.

#### Save / Unsave
**POST** `/{id}/save_video/`
Toggles the save status.

#### Share
**POST** `/{id}/share/`
Increments the share counter.

#### Add to Cart (Directly from Video)
**POST** `/{id}/add_to_cart/`
Adds the video's product to the user's cart.

**Payload:**
```json
{
  "product_id": 102, // Optional. If omitted, adds the primary product.
  "quantity": 1
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Added Sun Hat to cart",
  "cart_item_count": 5
}
```

### 2. Comments (`/video-comments/`)

#### List Comments
**GET** `/?video_id={id}`
Get comments for a specific video.

#### Add Comment
**POST** `/`
```json
{
  "video": 1,
  "text": "Where can I get this?",
  "parent": null // Optional parent comment ID for replies
}
```

### 3. User Follows (`/user-follows/`)

#### Toggle Follow
**POST** `/toggle_follow/`
Follow or unfollow a user (creator/seller).

**Payload:**
```json
{
  "following_id": 42
}
```

#### List Followers
**GET** `/?user_id={id}`
List users following the specified user.

### 4. Moderation (`/video-reports/`)

#### Report Video
**POST** `/`
Report a video for inappropriate content.

**Payload:**
```json
{
  "video": 1,
  "reason": "spam", // Options: spam, inappropriate, harassment, misleading, other
  "description": "Bot account posting spam links"
}
```

### 5. Creators (`/creators/`)

Endpoints related to creator profiles and discovery. Base path: `/api/v1/creators/`.

#### Trending Creators
**GET** `/trending/`
Returns a ranked list of creators based on social proof, verification status, and follower growth.

### 6. Video Categories (`/shoppable-video-categories/`)

#### List Categories
**GET** `/`
Returns list of active video categories.

#### Category Creators
**GET** `/{id}/creators/`
Returns creators associated with this video category.

#### Category Videos
**GET** `/{id}/videos/`
Returns shoppable videos in this category.

## Management Commands

### Load Video Categories
Populate default video categories.
```bash
python manage.py load_video_categories
```

## Performance & Optimization

The system is designed for high performance and low latency:
- **Database Indexing**: Critical fields like `trend_score`, `created_at`, `content_type`, `follower_count`, and engagement statuses (`is_liked`, `is_saved`) are indexed.
- **N+1 Avoidance**: Feed results pre-fetch all engagement data (likes/saves) for the current user in a single request batch.
- **Atomic Updates**: Counters for views, likes, and shares use database-level `F()` expressions to ensure consistency and speed.
- **Media Optimization**: Separate fields for `video_file` and `image_file` allow the frontend to request and render only the necessary media type.


#### List / Search Creators
**GET** `/api/v1/creators/?q={query}&video_category={id}&category={id}`
- Supports searching by `handle`, `display_name`, or `username` via the `q` query param.
- Supports filtering by `video_category` or product `category`.
- Sorted by `follower_count` by default.

**Response:**
```json
{
  "count": 123,
  "results": [
    {
      "id": 12,
      "user": 45,
      "username": "creator123",
      "handle": "@creator",
      "display_name": "Creator Name",
      "avatar": "http://.../avatar.jpg",
      "follower_count": 1024,
      "posts_count": 34,
      "views_count": 120345,
      "uploader_profile_url": "http://localhost:8005/api/v1/creators/12/"
    }
  ]
}
```

#### Retrieve Creator
**GET** `/api/v1/creators/{id}/`
Returns the full `CreatorProfile` for the given id.

#### Update Creator (owner only)
**PATCH/PUT** `/api/v1/creators/{id}/`
- Only the profile owner may update their profile fields (avatar, bio, social_links, etc.).

#### Creator Products
**GET** `/api/v1/creators/{id}/products/`
Returns marketplace products owned by or featured in videos of the creator.

#### Creator Videos
**GET** `/api/v1/creators/{id}/videos/`
Returns shoppable videos from this creator.

#### Followers
**GET** `/api/v1/creators/{id}/followers/`
Returns a list of users (or creator profiles) who follow this creator.

#### Following
**GET** `/api/v1/creators/{id}/following/`
Returns a list of creators this creator (user) follows.

#### My Following
**GET** `/api/v1/creators/me_following/`
Authenticated endpoint returning creators the current user follows.
