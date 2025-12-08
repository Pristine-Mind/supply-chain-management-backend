# Shoppable Videos API & Recommendation Engine

## Overview
The Shoppable Videos feature allows users to browse a TikTok-style feed of short videos linked to marketplace products. The feed is personalized using a sophisticated recommendation engine that learns from user interactions (likes, saves, shares, views).

## Data Models

### ShoppableVideo
- **product**: Link to `MarketplaceProduct`.
- **video_file**: The video media file.
- **title**: Title of the video.
- **tags**: List of tags (e.g., ["tech", "gadgets"]).
- **trend_score**: A float score indicating current popularity.
- **metrics**: `views_count`, `likes_count`, `shares_count`.

### User Interactions
- **VideoLike**: Records when a user likes a video.
- **VideoSave**: Records when a user saves a video for later.
- **UserInteraction**: Logs generic events like `product_view` which feed into the recommendation engine.

## Recommendation Algorithm

The personalized feed is generated via a 4-stage process:

### 1. User Profiling
We derive a user's interest profile based on:
- **Explicit Signals**: Liked videos, Saved videos.
- **Implicit Signals**: Product views (from `UserInteraction`).
- **Output**: A set of preferred `categories` and `tags`.

### 2. Candidate Generation
We select a pool of potential videos (~50-100) from:
- **Interest-based**: Videos matching the user's preferred categories.
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

Base URL: `/api/v1/shoppable-videos/`

### 1. Get Video Feed
**GET** `/`

Returns a personalized list of videos.

**Response:**
```json
[
  {
    "id": 1,
    "title": "Amazing Gadget Review",
    "video_file": "http://.../video.mp4",
    "product": {
      "id": 101,
      "name": "Smart Watch",
      "price": 199.99
    },
    "likes_count": 150,
    "is_liked": true,
    "is_saved": false,
    "trend_score": 0.85
  },
  ...
]
```

### 2. Upload Video
**POST** `/`
- **file**: Video file (max 50MB, .mp4).
- **product_id**: ID of the product.
- **title**: Video title.
- **tags**: JSON list of tags.

### 3. Like / Unlike
**POST** `/{id}/like/`

Toggles the like status.

**Response:**
```json
{
  "status": "success",
  "liked": true,
  "likes_count": 151
}
```

### 4. Save / Unsave
**POST** `/{id}/save_video/`

Toggles the save status.

**Response:**
```json
{
  "status": "success",
  "saved": true
}
```

### 5. Share
**POST** `/{id}/share/`

Increments the share counter.

**Response:**
```json
{
  "status": "success",
  "shares_count": 45
}
```

### 6. View
**POST** `/{id}/view/`

Increments the view counter. Call this when a video loops or is watched for a significant duration.

**Response:**
```json
{
  "status": "success",
  "views_count": 1205
}
```
