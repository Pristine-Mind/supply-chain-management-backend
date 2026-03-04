# New Features Implementation Documentation

This document describes the four major features implemented:
1. Advanced Product Filtering with Faceted Search
2. Predictive Inventory Analytics
3. Enhanced Product Search with Query Understanding
4. Bulk Import/Export with Background Processing

---

## 1. Advanced Product Filtering with Faceted Search

### Overview
A comprehensive filtering system for marketplace products with faceted search capabilities, enabling users to filter by multiple criteria simultaneously with real-time facet counts.

### Key Features
- **Multi-dimensional Filtering**: Price ranges, ratings, availability, offers, attributes (size, color), location
- **Faceted Search**: Dynamic counts for each filter option based on current results
- **Price Range Presets**: Budget, Economy, Mid-range, Premium, Luxury
- **Stock Status Filtering**: In stock, Low stock, Out of stock
- **Delivery Time Filtering**: Same day, 1-2 days, 3-5 days, 1 week+
- **Sorting Options**: Price, popularity, rating, newest, discount
- **Geographic Filtering**: Near me (lat,lng,radius)

### API Endpoints

#### GET /api/v1/marketplace/advanced-search/
Main search endpoint with query parameter filtering.

**Query Parameters:**
- `search`: Text search across product details
- `category_id`, `subcategory_id`, `sub_subcategory_id`: Category filters
- `brand_id`: Filter by brand (can be multiple)
- `min_price`, `max_price`: Price range
- `price_range`: Preset values (budget, economy, mid, premium, luxury)
- `min_rating`: Minimum average rating (1-5)
- `min_reviews`: Minimum number of reviews
- `in_stock`: true/false
- `stock_status`: in_stock, low_stock, out_of_stock
- `has_discount`: true/false
- `discount_min`: Minimum discount percentage
- `on_sale`: true/false
- `size`, `color`: Product attributes (can be multiple)
- `b2b_available`: true/false
- `sort_by`: price_asc, price_desc, newest, popular, rating, discount
- `near_me`: Format "lat,lng,radius_km" (e.g., "27.7172,85.3240,10")

**Response:**
```json
{
  "results": [...],
  "facets": {
    "price_ranges": {"budget": 15, "economy": 42, ...},
    "categories": [{"id": 1, "name": "Electronics", "count": 25}],
    "brands": [{"id": 1, "name": "Samsung", "count": 12}],
    "ratings": {"4_and_up": 45, "3_and_up": 78},
    "stock_status": {"in_stock": 120, "low_stock": 15, "out_of_stock": 5},
    "discounts": {"has_discount": 35, "no_discount": 105},
    "delivery_time": {"same_day": 10, "1_2_days": 45, ...}
  },
  "total_count": 140,
  "total_pages": 7,
  "current_page": 1
}
```

#### GET /api/v1/marketplace/facets/
Get facet counts without full product results (useful for initial page load).

#### GET /api/v1/marketplace/filter-options/
Get all available filter options for building UI.

#### POST /api/v1/marketplace/advanced-search/post/
POST endpoint for complex search queries with JSON body.

### Files
- `market/advanced_filters.py`: Core filtering logic
- `market/views_advanced_filters.py`: API views

---

## 2. Predictive Inventory Analytics

### Overview
Machine learning-based inventory forecasting system that predicts demand, stockout dates, and optimal reorder points using historical sales data.

### Key Features
- **Demand Forecasting**: Multiple methods (Moving Average, Exponential Smoothing, Seasonal Decomposition, Ensemble)
- **Stockout Prediction**: Predicts when products will run out of stock
- **Stockout Probability**: Monte Carlo simulation for risk assessment
- **Economic Order Quantity (EOQ)**: Optimal order quantity calculation
- **Reorder Point Optimization**: Dynamic reorder point based on lead time and demand variability
- **Seasonality Analysis**: Weekly pattern detection
- **Trend Analysis**: Demand trend detection (increasing, decreasing, stable)
- **Portfolio Analytics**: Overview of all products' health

### Forecasting Methods

#### 1. Moving Average
Simple average of recent sales data. Good for stable demand.

#### 2. Exponential Smoothing
Weights recent data more heavily. Good for trending data.

#### 3. Seasonal Decomposition
Detects weekly patterns (weekday vs weekend sales).

#### 4. Ensemble
Combines all methods for best accuracy.

### API Endpoints

#### GET /api/v1/producer/products/{id}/forecast/
Get demand forecast for a product.

**Query Parameters:**
- `days`: Forecast period (default: 30, max: 90)
- `method`: moving_average, exponential_smoothing, seasonal, ensemble

**Response:**
```json
{
  "product_id": 1,
  "product_name": "Product Name",
  "forecast": {
    "daily_forecast": 12.5,
    "forecast_period_days": 30,
    "total_forecast": 375,
    "confidence_interval": [10.2, 14.8],
    "method": "ensemble",
    "methods_used": ["moving_average", "exponential_smoothing", "seasonal_decomposition"]
  }
}
```

#### GET /api/v1/producer/products/{id}/stockout-prediction/
Get stockout prediction and risk assessment.

**Response:**
```json
{
  "product_id": 1,
  "current_stock": 50,
  "stockout_prediction": {
    "will_stockout": true,
    "stockout_date": "2024-03-15",
    "days_until_stockout": 4,
    "risk_level": "critical",
    "recommended_reorder_date": "2024-03-08"
  },
  "stockout_probability": {
    "30_days": {"probability": 85.5, "confidence": "high"},
    "60_days": {"probability": 95.2, "confidence": "medium"}
  }
}
```

#### GET /api/v1/producer/products/{id}/optimization/
Get inventory optimization recommendations.

**Response:**
```json
{
  "product_id": 1,
  "optimization": {
    "reorder_point": 87,
    "economic_order_quantity": 150,
    "safety_stock": 35,
    "action_required": "reorder_now",
    "urgency": "high"
  },
  "eoq_analysis": {
    "eoq": 150,
    "annual_demand": 4562.5,
    "order_frequency_per_year": 30.4,
    "days_between_orders": 12.0
  }
}
```

#### POST /api/v1/producer/products/{id}/optimization/
Apply optimization recommendations to product.

#### GET /api/v1/producer/products/{id}/analytics/
Get complete analytics (forecast + stockout + optimization + seasonality + trends).

#### GET /api/v1/producer/portfolio-analytics/
Get dashboard overview of all products.

#### GET /api/v1/producer/reorder-recommendations/
Get list of products needing reorder with recommendations.

#### POST /api/v1/producer/batch-forecast/
Get forecasts for multiple products at once.

### Files
- `producer/inventory_analytics.py`: Core analytics engine
- `producer/views_inventory_analytics.py`: API views

---

## 3. Enhanced Product Search with Query Understanding

### Overview
An enhanced search system that understands natural language queries through rule-based parsing. Extracts intent, entities, and performs intelligent keyword matching without requiring external ML libraries.

### Key Features
- **Query Understanding**: Parses natural language to extract intent and entities
- **Intent Classification**: Detects product_search, comparison, question, price_search intents
- **Entity Extraction**: Extracts colors, sizes, materials, price constraints, use cases
- **Query Expansion**: Generates query variations for better recall
- **Relevance Scoring**: Multi-factor scoring based on name, description, attributes
- **Similar Products**: Finds similar products based on category and attributes
- **Search Suggestions**: Real-time suggestions as user types

### How It Works

1. **Query Parsing**: Analyzes the query to understand:
   - Intent (what the user wants)
   - Entities (colors, sizes, brands, price ranges)
   - Keywords (important search terms)
   - Use cases (gift, office, outdoor, etc.)

2. **Enhanced Search**: 
   - Searches across multiple fields (name, description, tags, brand)
   - Applies entity-based boosts (color match = +0.15, size match = +0.15)
   - Scores results based on match quality

3. **Similar Products**: 
   - Uses category, brand, size, color, and price proximity
   - No pre-built index required

### API Endpoints

#### GET /api/v1/marketplace/semantic-search/?q={query}
Main enhanced search endpoint.

**Query Parameters:**
- `q`: Search query (required)
- `category_id`, `brand_id`: Filters
- `min_price`, `max_price`: Price filters
- `in_stock`: true/false

**Response:**
```json
{
  "query": "comfortable running shoes under 5000",
  "parsed_query": {
    "intent": "product_search",
    "entities": {
      "use_cases": ["sports"],
      "price_constraints": {"descriptor": "budget"},
      "colors": [],
      "sizes": []
    },
    "keywords": ["comfortable", "running", "shoes", "5000"],
    "expanded_queries": [
      "comfortable running shoes under 5000",
      "comfortable running shoes under 5000 for sports"
    ]
  },
  "results": [
    {
      "product": {...},
      "relevance_score": 0.92,
      "keyword_score": 0.92,
      "match_type": "excellent"
    }
  ],
  "search_method": "enhanced_keyword",
  "total_found": 25
}
```

#### GET /api/v1/marketplace/products/{id}/similar/
Find products similar to a given product.

#### GET /api/v1/marketplace/query-understanding/?q={query}
Analyze a query to understand intent and entities.

#### POST /api/v1/marketplace/semantic-search/
POST endpoint with JSON body for complex queries.

#### GET /api/v1/marketplace/search-suggestions/?q={partial}
Get search suggestions as user types.

#### POST /api/v1/marketplace/nl-search/
Natural language search with conversation context.

### Optional: OpenAI Integration

To enable LLM-powered query parsing (optional):

```bash
pip install openai
export OPENAI_API_KEY=your_key
export USE_OPENAI_LLM=true
```

Without OpenAI, the system uses rule-based parsing which works well for most queries.

### Files
- `market/semantic_search.py`: Core search engine (no external ML dependencies)
- `market/views_semantic_search.py`: API views

---

## 4. Bulk Import/Export with Background Processing

### Overview
System for importing and exporting products in bulk using CSV or Excel files with asynchronous processing via Celery.

### Key Features
- **CSV Import**: Simple text-based format
- **Excel Import**: Rich formatting with multiple sheets
- **Background Processing**: Non-blocking via Celery tasks
- **Progress Tracking**: Real-time status updates
- **Validation**: Pre-import validation without changes
- **Error Reporting**: Detailed error messages per row
- **Update Existing**: Option to update or skip existing products
- **Template Generation**: Download import templates

### Supported Fields

**Required:**
- `name`: Product name
- `price`: Selling price
- `stock`: Current stock quantity

**Optional:**
- `sku`: Unique product code
- `description`: Product description
- `cost_price`: Cost price
- `reorder_level`: Reorder threshold
- `category_id`: Category ID
- `subcategory_id`: Subcategory ID
- `brand_id`: Brand ID
- `size`: Product size
- `color`: Product color
- `is_active`: Yes/No

### API Endpoints

#### POST /api/v1/producer/import/
Upload and import products from file.

**Request:**
- Content-Type: multipart/form-data
- Fields:
  - `file`: CSV or Excel file
  - `update_existing`: true/false (default: true)

**Response:**
```json
{
  "success": true,
  "job_id": "uuid",
  "task_id": "celery-task-id",
  "status": "processing",
  "check_status_url": "/api/v1/producer/import/uuid/status/"
}
```

#### GET /api/v1/producer/import/{job_id}/status/
Check import progress.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "processing",
  "progress": {
    "processed": 150,
    "total": 500,
    "percent": 30
  }
}
```

#### GET /api/v1/producer/import/{job_id}/result/
Get detailed results of completed import.

**Query Parameters:**
- `include_errors`: true/false (include failed rows)

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "summary": {
    "total_rows": 500,
    "success_count": 485,
    "error_count": 15,
    "created_products": 200,
    "updated_products": 285
  },
  "errors": {
    "total_errors": 15,
    "failed_rows": [...]
  }
}
```

#### GET /api/v1/producer/import/template/?format={csv|excel}
Download import template.

#### POST /api/v1/producer/import/validate/
Validate import file without importing.

#### POST /api/v1/producer/export/
Start export job.

**Request:**
```json
{
  "format": "csv",
  "filters": {
    "category_id": 1,
    "is_active": true
  }
}
```

#### GET /api/v1/producer/export/?format={csv|excel}
Quick synchronous export (for small datasets).

#### GET /api/v1/producer/export/{job_id}/status/
Check export status and get download URL.

### Import Process

1. **Upload**: Client uploads file
2. **Validation**: File type and format validation
3. **Queue**: Job queued via Celery
4. **Processing**: 
   - Read file in batches (100 rows at a time)
   - Validate each row
   - Create/update products
   - Update progress in cache
5. **Completion**: Results stored in cache for 24 hours

### Export Process

1. **Request**: Client requests export with filters
2. **Queue**: Job queued via Celery
3. **Processing**:
   - Query products
   - Format as CSV/Excel
   - Save to storage
4. **Download**: URL provided for download

### Files
- `producer/bulk_operations.py`: Core import/export logic
- `producer/tasks_bulk.py`: Celery tasks
- `producer/views_bulk.py`: API views

---

## Celery Configuration

Ensure these settings are in your Celery Beat schedule:

```python
CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...
    
    "cleanup-old-export-files": {
        "task": "producer.tasks_bulk.cleanup_old_export_files",
        "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM
    },
}
```

---

## Dependencies

Add to `pyproject.toml`:

```toml
[tool.poetry.dependencies]
# ... existing dependencies ...
openpyxl = "*"
# sentence-transformers removed - not required
```

Or install via pip:

```bash
pip install openpyxl
```

### Required Dependencies (Already in Project)
- `numpy` - For analytics calculations
- `scipy` - For statistical functions
- `faiss-cpu` - Already included (can be used for other features)

### Optional Dependencies
- `openpyxl` - For Excel import/export (required for Excel support)
- `openai` - For LLM-powered query parsing (optional)

---

## Usage Examples

### Advanced Filtering

```bash
# Search with multiple filters
curl "https://api.example.com/api/v1/marketplace/advanced-search/?\
category_id=1&\
min_price=1000&\
max_price=5000&\
min_rating=4&\
in_stock=true&\
sort_by=price_asc"
```

### Inventory Forecast

```bash
# Get 30-day forecast using ensemble method
curl "https://api.example.com/api/v1/producer/products/1/forecast/?\
days=30&\
method=ensemble" \
  -H "Authorization: Bearer token"
```

### Enhanced Search

```bash
# Natural language product search
curl "https://api.example.com/api/v1/marketplace/semantic-search/?\
q=comfortable%20office%20chairs%20under%205000"
```

### Bulk Import

```bash
# Upload CSV file for import
curl -X POST "https://api.example.com/api/v1/producer/import/" \
  -H "Authorization: Bearer token" \
  -F "file=@products.csv" \
  -F "update_existing=true"
```

---

## Testing

Run tests for the new features:

```bash
# Test advanced filters
python manage.py test market.tests.test_advanced_filters

# Test inventory analytics
python manage.py test producer.tests.test_inventory_analytics

# Test enhanced search
python manage.py test market.tests.test_semantic_search

# Test bulk operations
python manage.py test producer.tests.test_bulk_operations
```

---

## Performance Considerations

1. **Advanced Filtering**: Uses database indexes on price, category, brand. Consider adding composite indexes for common filter combinations.

2. **Inventory Analytics**: Forecasting is CPU-intensive. Use batch forecasting for multiple products. Results are computed in real-time.

3. **Enhanced Search**: Rule-based parsing is fast and doesn't require model loading. Searches use standard database queries with scoring computed in Python.

4. **Bulk Import**: Processing happens in background. Large files (10k+ rows) may take several minutes. Monitor Celery worker memory usage.

---

## Future Enhancements

1. **Advanced Filtering**: Add faceted search caching, more filter types (date ranges, tags)
2. **Inventory Analytics**: Add more forecasting models (ARIMA, Prophet), automated reorder suggestions
3. **Enhanced Search**: Consider adding external vector database (Pinecone, Weaviate) for true semantic search if needed
4. **Bulk Operations**: Scheduled imports from URLs, import from external APIs, export scheduling
