# Marketplace Trending Products API

This document describes the trending products API endpoints for the marketplace.

## Overview

The trending products API provides comprehensive endpoints to retrieve and analyze trending marketplace products based on various metrics including:

- Recent purchases (24 hours and 7 days)
- View counts
- Average ratings
- Sales velocity
- Engagement rates

## Base URL

All trending product endpoints are under:
```
/api/v1/marketplace-trending/
```

## Endpoints

### 1. List Trending Products

**GET** `/api/v1/marketplace-trending/`

Returns a list of trending products ordered by trending score.

**Query Parameters:**
- `category` (optional): Filter by product category name
- `min_price` (optional): Minimum price filter
- `max_price` (optional): Maximum price filter
- `location` (optional): Filter by seller location
- `limit` (optional): Number of results to return (default: 20)

**Response:**
```json
{
    "results": [
        {
            "id": 1,
            "product_details": {...},
            "listed_price": 1000.0,
            "discounted_price": 800.0,
            "trending_score": 85.5,
            "total_sales": 45,
            "recent_sales_count": 8,
            "weekly_sales_count": 12,
            "weekly_view_count": 156,
            "sales_velocity": 1.71,
            "engagement_rate": 7.69,
            "trending_rank": 1,
            "price_trend": "decreasing",
            "average_rating": 4.5,
            "view_count": 1200,
            "is_available": true
        }
    ],
    "count": 20,
    "timestamp": "2025-11-01T10:30:00Z"
}
```

### 2. Top Weekly Products

**GET** `/api/v1/marketplace-trending/top_weekly/`

Returns top products based on weekly sales performance.

**Response:**
```json
{
    "results": [...],
    "period": "weekly",
    "count": 10
}
```

### 3. Most Viewed Products

**GET** `/api/v1/marketplace-trending/most_viewed/`

Returns products with highest view counts.

**Response:**
```json
{
    "results": [...],
    "period": "most_viewed",
    "count": 10
}
```

### 4. Fastest Selling Products

**GET** `/api/v1/marketplace-trending/fastest_selling/`

Returns products with highest sales velocity (sales per day).

**Response:**
```json
{
    "results": [...],
    "period": "fastest_selling",
    "count": 10
}
```

### 5. New Trending Products

**GET** `/api/v1/marketplace-trending/new_trending/`

Returns newly listed products (within 7 days) that are trending.

**Response:**
```json
{
    "results": [...],
    "period": "new_trending",
    "count": 10
}
```

### 6. Trending Categories

**GET** `/api/v1/marketplace-trending/categories/`

Returns trending product categories with metrics.

**Response:**
```json
{
    "results": [
        {
            "category_name": "Electronics",
            "product_count": 45,
            "total_sales": 123,
            "avg_rating": 4.2,
            "trending_score": 89.5
        }
    ],
    "count": 10
}
```

### 7. Trending Statistics

**GET** `/api/v1/marketplace-trending/stats/`

Returns overall trending products statistics.

**Response:**
```json
{
    "total_trending_products": 156,
    "trending_categories": [...],
    "top_performing_timeframe": "weekly",
    "average_trending_score": 45.8,
    "price_range": {
        "min": 50.0,
        "max": 5000.0,
        "average": 850.75
    }
}
```

## Data Fields Explanation

### Core Fields
- `trending_score`: Calculated score based on weighted metrics (0-100+)
- `trending_rank`: Ranking position based on trending score
- `sales_velocity`: Average sales per day over the last week
- `engagement_rate`: Percentage of views that convert to sales

### Metrics Weights
The trending score is calculated using:
- Recent purchases (50% weight): Recent sales activity
- View count (30% weight): Product visibility and interest
- Average rating (20% weight): Product quality indicator

### Price Trend Indicators
- `stable`: No significant price changes
- `decreasing`: Product has active discount
- `promotional`: Product has time-limited offers

## Usage Examples

### Get top 10 trending electronics under $1000
```
GET /api/v1/marketplace-trending/?category=electronics&max_price=1000&limit=10
```

### Get fastest selling products in Kathmandu
```
GET /api/v1/marketplace-trending/fastest_selling/?location=kathmandu
```

### Get trending categories statistics
```
GET /api/v1/marketplace-trending/categories/
```

## Rate Limiting

The trending products API is rate-limited to prevent abuse:
- 100 requests per minute per user
- 1000 requests per hour per user

## Error Responses

Standard HTTP status codes are used:
- `400`: Bad Request (invalid parameters)
- `404`: Not Found
- `429`: Too Many Requests (rate limited)
- `500`: Internal Server Error

## Notes

- Trending scores are updated hourly via background tasks
- View counts are updated in real-time when products are viewed
- Recent purchase counts reflect the last 24 hours
- All responses include timestamps for cache management