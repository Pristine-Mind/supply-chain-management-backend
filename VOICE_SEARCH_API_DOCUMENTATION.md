# Voice & Agentic Search API Documentation

This document describes the APIs for voice-enabled and natural language (agentic) search within the marketplace. These APIs use LLM-style intent parsing to move beyond keyword matching, offering a bespoke experience for both B2B and B2C users.

---

## 1. Agentic Voice Search API

An intelligent endpoint that processes either raw audio or text queries to understand intent and return personalized product recommendations.

- **Endpoint**: `POST /api/market/voice-search/`
- **Authentication**: Optional (Authenticated users receive hyper-personalized results based on their history).
- **Content-Type**: `multipart/form-data` (for audio) or `application/json` (for text).

### Request Parameters

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `query` | String | No* | The text query to process (e.g., "bulk office chairs under $500"). |
| `audio_file` | File | No* | Audio file containing the voice command. Supports standard formats (WAV, MP3). |
| `page` | Integer | No | Page number for pagination (Default: 1). |
| `page_size` | Integer | No | Number of results per page (Default: 20). |

*\*At least one of `query` or `audio_file` must be provided.*

### Intent Features (Agentic Rules)

The search engine automatically extracts the following intents from natural language:
- **Price Brackets**: Detects "under," "above," and "between" constraints.
- **B2B Logic**: Keywords like "wholesale," "bulk," or "business" trigger B2B price prioritization.
- **Geographic Boost**: Keywords like "local" or "swadeshi" filter for products made in Nepal.
- **Urgency**: "Fast," "today," or "urgent" sorts results by delivery speed.
- **Attributes**: Detects colors (e.g., "red," "blue") and sizes.

### Sample Response

```json
{
  "query": "wholesale red bricks under 500",
  "intent": {
    "query": "bricks",
    "max_price": 500.0,
    "is_b2b": true,
    "made_in_nepal": false,
    "color": "RED",
    "urgency": "normal",
    "sort_by": "price_asc"
  },
  "metadata": {
    "total_results": 142,
    "page": 1,
    "total_pages": 8,
    "has_next": true,
    "has_previous": false
  },
  "results": [
    {
      "id": 1024,
      "name": "Standard Red Brick - Grade A",
      "b2b_price": 450.0,
      "listed_price": 600.0,
      "is_made_in_nepal": true,
      "estimated_delivery_days": 2
    }
  ]
}
```

---

## 2. Recommendation Engine Integration

The results returned by the search API are ranked using a two-stage pipeline:

1.  **Retrieval Phase**: Filters products based on extracted intent (B2B context, price, geography).
2.  **Hyper-Personalization Phase**: For authenticated users, products are boosted if they match the user's previously interacted categories or brands (captured via the `UserInteraction` model).

---

## 3. Error Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Search processed successfully. |
| `400 Bad Request` | Missing required fields or invalid audio format. |
| `503 Service Unavailable` | Speech recognition service is down. |

---

## Technical Appendix: Search Intent logic

The underlying `AgenticSearchService` in [market/services.py](market/services.py) uses a non-deterministic parsing approach to handle variations in user queries, making the interface feel conversational and human-centric.
