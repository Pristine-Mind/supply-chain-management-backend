# Shoppable Videos API & Recommendation Engine

## Overview
The Shoppable Videos feature allows users to browse a TikTok-style feed of short videos linked to marketplace products. The feed is personalized using a sophisticated recommendation engine that learns from user interactions (likes, saves, shares, views).

## Data Models

### ShoppableVideo
- **product**: Link to `MarketplaceProduct` (Primary product).
- **additional_products**: Many-to-Many link to `MarketplaceProduct` (Other featured items).
- **video_file**: The video media file.
- **title**: Title of the video.
- **tags**: List of tags (e.g., ["tech", "gadgets"]).
- **trend_score**: A float score indicating current popularity.
- **metrics**: `views_count`, `likes_count`, `shares_count`.

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
- **Implicit Signals**: Product views, Add to cart actions.
- **Output**: A set of preferred `categories` and `tags`.

### 2. Candidate Generation
We select a pool of potential videos (~50-100) from:
- **Interest-based**: Videos matching the user's preferred categories.
- **Following**: Videos from creators the user follows.
- **Trending**: High `trend_score` videos (for discovery).
- **Recency**: New uploads (to solve the cold-start problem).

### 3. Scoring
Each candidate video is assigned a relevance score:
$$ Score = S_{category} + S_{tags} + S_{engagement} + S_{trend} + S_{random} $$

- **Category Match**: +2.0 points.
- **Tag Match**: +1.5 points per matching tag.
- **Engagement**: Weighted sum of interactions ($0.01 \times views + 1.0 \times likes + 1.2 \times shares$).
- **Trend**: $4.0 \times trend\_score$.
- **Randomness**: Small random factor (0-0.5) to ensure feed variety.

### 4. Ranking
Candidates are sorted by score in descending order, and the top N results are returned.

## API Endpoints

Base URL: `/api/v1/`

### 1. Shoppable Videos (`/shoppable-videos/`)

#### Get Video Feed
**GET** `/`
Returns a personalized list of videos.

**Response:**
```json
[
  {
    "id": 1,
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

#### Upload Video
**POST** `/`
- **file**: Video file (max 50MB, .mp4).
- **product_id**: ID of the primary product.
- **additional_product_ids**: List of IDs for other featured products (e.g., `[102, 103]`).
- **title**: Video title.
- **tags**: JSON list of tags.

#### Like / Unlike
**POST** `/{id}/like/`
Toggles the like status.

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

#### List / Search Creators
**GET** `/api/v1/creators/?q={query}`
- Supports searching by `handle`, `display_name`, or `username` via the `q` query param.
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

#### Followers
**GET** `/api/v1/creators/{id}/followers/`
Returns a list of users (or creator profiles) who follow this creator.

#### Following
**GET** `/api/v1/creators/{id}/following/`
Returns a list of creators this creator (user) follows.

#### My Following
**GET** `/api/v1/creators/me_following/`
Authenticated endpoint returning creators the current user follows.
