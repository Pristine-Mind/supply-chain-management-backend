# Predictive Inventory Analytics API Documentation

API documentation for inventory forecasting, stockout prediction, and optimization features.

**Base URL:** `/api/v1/producer/`

**Authentication:** Required (Bearer Token)

---

## 1. Get Product Demand Forecast

Get ML-based demand forecast for a specific product.

### Endpoint

```
GET /api/v1/producer/products/{product_id}/forecast/
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `days` | integer | No | 30 | Forecast period in days (max: 90) |
| `method` | string | No | "ensemble" | Forecasting method: `moving_average`, `exponential_smoothing`, `seasonal`, `ensemble` |

### Methods Explained

- `moving_average`: Simple average of recent sales (good for stable demand)
- `exponential_smoothing`: Weights recent data more heavily (good for trends)
- `seasonal`: Detects weekly patterns (good for products with day-of-week variations)
- `ensemble`: Combines all methods for best accuracy (recommended)

### Response

```json
{
  "product_id": 123,
  "product_name": "Wireless Mouse",
  "forecast": {
    "daily_forecast": 12.5,
    "forecast_period_days": 30,
    "total_forecast": 375,
    "confidence_interval": [10.2, 14.8],
    "method": "ensemble",
    "methods_used": [
      "moving_average",
      "exponential_smoothing",
      "seasonal_decomposition"
    ],
    "std_deviation": 2.3,
    "individual_forecasts": [
      {
        "daily_forecast": 11.8,
        "method": "moving_average",
        "window_used": 30
      },
      {
        "daily_forecast": 13.2,
        "method": "exponential_smoothing",
        "alpha": 0.3
      }
    ]
  },
  "method_used": "ensemble",
  "forecast_days": 30
}
```

### Error Responses

```json
// 404 Not Found
{
  "error": "Product not found"
}

// 400 Bad Request
{
  "error": "Invalid method. Choose from: moving_average, exponential_smoothing, seasonal, ensemble"
}
```

### Frontend Integration Example

```javascript
// React/Axios example
const getForecast = async (productId, days = 30) => {
  const response = await axios.get(
    `/api/v1/producer/products/${productId}/forecast/?days=${days}&method=ensemble`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  return response.data;
};

// Display forecast chart
const ForecastChart = ({ productId }) => {
  const [forecast, setForecast] = useState(null);
  
  useEffect(() => {
    getForecast(productId).then(data => {
      setForecast(data.forecast);
    });
  }, [productId]);
  
  if (!forecast) return <Loading />;
  
  return (
    <div>
      <h3>30-Day Demand Forecast</h3>
      <p>Daily Average: {forecast.daily_forecast} units</p>
      <p>Total Forecast: {forecast.total_forecast} units</p>
      <p>Confidence Range: {forecast.confidence_interval[0]} - {forecast.confidence_interval[1]}</p>
      
      {/* Chart visualization */}
      <ForecastChartComponent 
        dailyForecast={forecast.daily_forecast}
        confidenceInterval={forecast.confidence_interval}
      />
    </div>
  );
};
```

---

## 2. Get Stockout Prediction

Predict when a product will run out of stock and assess risk level.

### Endpoint

```
GET /api/v1/producer/products/{product_id}/stockout-prediction/
```

### Response

```json
{
  "product_id": 123,
  "product_name": "Wireless Mouse",
  "current_stock": 50,
  "stockout_prediction": {
    "will_stockout": true,
    "stockout_date": "2024-03-15",
    "days_until_stockout": 4,
    "risk_level": "critical",
    "current_stock": 50,
    "daily_demand_forecast": 12.5,
    "lead_time_days": 7,
    "safety_stock": 10,
    "recommended_reorder_date": "2024-03-08"
  },
  "stockout_probability": {
    "30_days": {
      "probability": 85.5,
      "probability_decimal": 0.855,
      "period_days": 30,
      "confidence": "high",
      "simulations_run": 10000,
      "average_daily_demand": 12.5,
      "demand_std_dev": 2.3
    },
    "60_days": {
      "probability": 95.2,
      "probability_decimal": 0.952,
      "period_days": 60,
      "confidence": "medium",
      "simulations_run": 10000,
      "average_daily_demand": 12.5,
      "demand_std_dev": 2.3
    }
  },
  "risk_assessment": {
    "level": "critical",
    "action_required": true,
    "recommended_action": "URGENT: Reorder immediately. Stockout predicted in 4 days."
  }
}
```

### Risk Levels

| Level | Days Until Stockout | Action |
|-------|-------------------|--------|
| `critical` | ≤ lead_time | Reorder immediately |
| `high` | lead_time + 7 days | Plan to reorder soon |
| `medium` | lead_time + 14 days | Monitor stock levels |
| `low` | > lead_time + 14 days | Stock levels healthy |

### Frontend Integration Example

```javascript
const StockoutAlert = ({ productId }) => {
  const [prediction, setPrediction] = useState(null);
  
  useEffect(() => {
    axios.get(`/api/v1/producer/products/${productId}/stockout-prediction/`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => setPrediction(res.data));
  }, [productId]);
  
  if (!prediction) return null;
  
  const { risk_level, days_until_stockout, stockout_date } = prediction.stockout_prediction;
  const { probability } = prediction.stockout_probability['30_days'];
  
  const riskColors = {
    critical: 'red',
    high: 'orange',
    medium: 'yellow',
    low: 'green'
  };
  
  return (
    <Alert color={riskColors[risk_level]}>
      <AlertTitle>Risk Level: {risk_level.toUpperCase()}</AlertTitle>
      <p>Stockout predicted in {days_until_stockout} days ({stockout_date})</p>
      <p>30-day stockout probability: {probability}%</p>
      <p>{prediction.risk_assessment.recommended_action}</p>
    </Alert>
  );
};
```

---

## 3. Get Inventory Optimization

Get optimal reorder point, safety stock, and EOQ recommendations.

### Endpoint

```
GET /api/v1/producer/products/{product_id}/optimization/
```

### Response

```json
{
  "product_id": 123,
  "product_name": "Wireless Mouse",
  "current_settings": {
    "stock": 50,
    "reorder_level": 20,
    "reorder_point": 87,
    "safety_stock": 10,
    "lead_time_days": 7
  },
  "optimization": {
    "product_id": 123,
    "product_name": "Wireless Mouse",
    "current_stock": 50,
    "reorder_point": 87,
    "economic_order_quantity": 150,
    "safety_stock": 35,
    "action_required": "reorder_now",
    "urgency": "high",
    "estimated_days_until_reorder": -1.6,
    "total_inventory_cost_optimized": 12500.50,
    "recommendations": [
      "Increase reorder point by 24 units to optimize for lead time and safety stock.",
      "Optimal order quantity is 150 units (12.0 days between orders).",
      "Consider increasing safety stock to 35 units for better service level."
    ]
  },
  "eoq_analysis": {
    "eoq": 150,
    "economic_order_quantity": 150,
    "annual_demand": 4562.5,
    "ordering_cost": 100,
    "holding_cost_per_unit": 25.0,
    "order_frequency_per_year": 30.4,
    "days_between_orders": 12.0,
    "total_annual_ordering_cost": 3040.0,
    "total_annual_holding_cost": 1875.0,
    "unit_cost": 100.0
  },
  "reorder_point_analysis": {
    "reorder_point": 87,
    "safety_stock": 35,
    "lead_time_demand": 87.5,
    "lead_time_days": 7,
    "avg_daily_demand": 12.5,
    "demand_std_dev": 2.3,
    "service_level": 0.95,
    "z_score": 1.65,
    "current_reorder_point": 87,
    "recommended_change": 0
  }
}
```

### Actions

| Action | Description | UI Indicator |
|--------|-------------|--------------|
| `reorder_now` | Stock below reorder point | Red alert |
| `plan_reorder` | Stock approaching reorder point | Yellow warning |
| `monitor` | Stock levels healthy | Green status |

### Frontend Integration Example

```javascript
const OptimizationCard = ({ productId }) => {
  const [data, setData] = useState(null);
  
  useEffect(() => {
    axios.get(`/api/v1/producer/products/${productId}/optimization/`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => setData(res.data));
  }, [productId]);
  
  if (!data) return <Loading />;
  
  const { optimization, eoq_analysis, reorder_point_analysis } = data;
  
  return (
    <Card>
      <CardHeader>
        <h3>Inventory Optimization</h3>
        <Badge color={optimization.action_required === 'reorder_now' ? 'red' : 'green'}>
          {optimization.action_required}
        </Badge>
      </CardHeader>
      
      <CardBody>
        <Section title="Recommended Settings">
          <Row label="Reorder Point" value={optimization.reorder_point} />
          <Row label="Order Quantity (EOQ)" value={optimization.economic_order_quantity} />
          <Row label="Safety Stock" value={optimization.safety_stock} />
        </Section>
        
        <Section title="Cost Analysis">
          <Row label="Annual Ordering Cost" value={`$${eoq_analysis.total_annual_ordering_cost}`} />
          <Row label="Annual Holding Cost" value={`$${eoq_analysis.total_annual_holding_cost}`} />
          <Row label="Total Cost" value={`$${optimization.total_inventory_cost_optimized}`} />
        </Section>
        
        <Section title="Recommendations">
          {optimization.recommendations.map((rec, i) => (
            <Alert key={i} type="info">{rec}</Alert>
          ))}
        </Section>
        
        <Button onClick={() => applyOptimization(productId)}>
          Apply Recommendations
        </Button>
      </CardBody>
    </Card>
  );
};

// Apply optimization settings
const applyOptimization = async (productId) => {
  const response = await axios.post(
    `/api/v1/producer/products/${productId}/optimization/`,
    {
      apply_reorder_point: true,
      apply_safety_stock: true,
      apply_reorder_quantity: true
    },
    {
      headers: { 'Authorization': `Bearer ${token}` }
    }
  );
  
  if (response.data.success) {
    alert('Optimization settings applied successfully!');
  }
};
```

---

## 4. Get Full Product Analytics

Get comprehensive analytics including forecast, stockout prediction, optimization, seasonality, and trends.

### Endpoint

```
GET /api/v1/producer/products/{product_id}/analytics/
```

### Response

```json
{
  "product": {
    "id": 123,
    "name": "Wireless Mouse",
    "sku": "WM-001",
    "current_stock": 50,
    "reorder_level": 20,
    "reorder_point": 87,
    "safety_stock": 10
  },
  "demand_forecast": {
    "daily_forecast": 12.5,
    "forecast_period_days": 30,
    "total_forecast": 375,
    "confidence_interval": [10.2, 14.8],
    "method": "ensemble"
  },
  "stockout_prediction": {
    "will_stockout": true,
    "stockout_date": "2024-03-15",
    "days_until_stockout": 4,
    "risk_level": "critical"
  },
  "stockout_probability": {
    "probability": 85.5,
    "confidence": "high"
  },
  "optimization": {
    "reorder_point": 87,
    "economic_order_quantity": 150,
    "safety_stock": 35,
    "action_required": "reorder_now",
    "urgency": "high"
  },
  "seasonality": {
    "has_seasonality": true,
    "peak_day": "Saturday",
    "low_day": "Tuesday",
    "peak_to_low_ratio": 1.8,
    "daily_averages": {
      "Monday": 10.5,
      "Tuesday": 8.2,
      "Wednesday": 11.0,
      "Thursday": 12.5,
      "Friday": 14.0,
      "Saturday": 18.5,
      "Sunday": 15.2
    }
  },
  "trends": {
    "trend": "increasing",
    "change_percentage": 15.5,
    "first_period_avg": 10.8,
    "second_period_avg": 12.5,
    "trend_direction": "up"
  }
}
```

### Frontend Integration Example

```javascript
const ProductAnalyticsDashboard = ({ productId }) => {
  const [analytics, setAnalytics] = useState(null);
  
  useEffect(() => {
    axios.get(`/api/v1/producer/products/${productId}/analytics/`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => setAnalytics(res.data));
  }, [productId]);
  
  if (!analytics) return <Loading />;
  
  return (
    <Dashboard>
      <StockoutAlert data={analytics.stockout_prediction} />
      
      <ForecastChart data={analytics.demand_forecast} />
      
      <SeasonalityChart 
        dailyAverages={analytics.seasonality.daily_averages}
        peakDay={analytics.seasonality.peak_day}
        lowDay={analytics.seasonality.low_day}
      />
      
      <TrendIndicator 
        trend={analytics.trends.trend}
        change={analytics.trends.change_percentage}
      />
      
      <OptimizationSummary data={analytics.optimization} />
    </Dashboard>
  );
};
```

---

## 5. Get Portfolio Analytics

Get overview analytics for all products (for dashboard).

### Endpoint

```
GET /api/v1/producer/portfolio-analytics/
```

### Response

```json
{
  "portfolio_analytics": {
    "total_products": 150,
    "low_stock_count": 25,
    "stockout_risk_count": 12,
    "reorder_needed_count": 25,
    "healthy_stock_percentage": 83.3,
    "at_risk_products": [
      {
        "product_id": 123,
        "name": "Wireless Mouse",
        "stock": 5,
        "risk_level": "critical",
        "days_until_stockout": 2
      },
      {
        "product_id": 124,
        "name": "USB Cable",
        "stock": 8,
        "risk_level": "high",
        "days_until_stockout": 5
      }
    ]
  },
  "generated_at": "2024-03-10T10:30:00Z"
}
```

### Frontend Integration Example

```javascript
const PortfolioDashboard = () => {
  const [portfolio, setPortfolio] = useState(null);
  
  useEffect(() => {
    axios.get('/api/v1/producer/portfolio-analytics/', {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => setPortfolio(res.data.portfolio_analytics));
  }, []);
  
  if (!portfolio) return <Loading />;
  
  return (
    <Dashboard>
      <StatsRow>
        <StatCard 
          title="Total Products" 
          value={portfolio.total_products} 
          icon="box"
        />
        <StatCard 
          title="Low Stock" 
          value={portfolio.low_stock_count}
          color="orange"
          alert={portfolio.low_stock_count > 0}
        />
        <StatCard 
          title="Critical Risk" 
          value={portfolio.stockout_risk_count}
          color="red"
          alert={portfolio.stockout_risk_count > 0}
        />
        <StatCard 
          title="Healthy Stock" 
          value={`${portfolio.healthy_stock_percentage}%`}
          color="green"
        />
      </StatsRow>
      
      <Section title="At-Risk Products">
        <Table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Stock</th>
              <th>Risk Level</th>
              <th>Days Until Stockout</th>
            </tr>
          </thead>
          <tbody>
            {portfolio.at_risk_products.map(product => (
              <tr key={product.product_id}>
                <td>{product.name}</td>
                <td>{product.stock}</td>
                <td>
                  <Badge color={product.risk_level === 'critical' ? 'red' : 'orange'}>
                    {product.risk_level}
                  </Badge>
                </td>
                <td>{product.days_until_stockout}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>
    </Dashboard>
  );
};
```

---

## 6. Get Reorder Recommendations

Get a prioritized list of products that need reordering.

### Endpoint

```
GET /api/v1/producer/reorder-recommendations/
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `risk_level` | string | No | - | Filter by risk level: `critical`, `high`, `medium`, `low` |
| `limit` | integer | No | 20 | Maximum number of products (max: 100) |

### Response

```json
{
  "recommendations": [
    {
      "product_id": 123,
      "product_name": "Wireless Mouse",
      "sku": "WM-001",
      "current_stock": 5,
      "risk_level": "critical",
      "days_until_stockout": 2,
      "stockout_date": "2024-03-12",
      "recommended_order_quantity": 150,
      "urgency": "high",
      "action": "reorder_now"
    },
    {
      "product_id": 124,
      "product_name": "USB Cable",
      "sku": "UC-002",
      "current_stock": 8,
      "risk_level": "high",
      "days_until_stockout": 5,
      "stockout_date": "2024-03-15",
      "recommended_order_quantity": 200,
      "urgency": "medium",
      "action": "plan_reorder"
    }
  ],
  "total_recommended": 25,
  "critical_count": 12,
  "high_count": 13
}
```

### Frontend Integration Example

```javascript
const ReorderRecommendations = () => {
  const [recommendations, setRecommendations] = useState([]);
  const [filter, setFilter] = useState('all');
  
  useEffect(() => {
    const params = filter !== 'all' ? `?risk_level=${filter}` : '';
    axios.get(`/api/v1/producer/reorder-recommendations/${params}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => setRecommendations(res.data.recommendations));
  }, [filter]);
  
  return (
    <div>
      <FilterBar>
        <Button onClick={() => setFilter('all')}>All</Button>
        <Button onClick={() => setFilter('critical')} color="red">Critical</Button>
        <Button onClick={() => setFilter('high')} color="orange">High</Button>
      </FilterBar>
      
      <ReorderTable>
        {recommendations.map(item => (
          <ReorderRow key={item.product_id} priority={item.risk_level}>
            <ProductInfo>
              <Name>{item.product_name}</Name>
              <SKU>{item.sku}</SKU>
            </ProductInfo>
            
            <StockInfo>
              <CurrentStock>Stock: {item.current_stock}</CurrentStock>
              <DaysLeft>{item.days_until_stockout} days left</DaysLeft>
            </StockInfo>
            
            <RiskBadge level={item.risk_level}>
              {item.risk_level}
            </RiskBadge>
            
            <Recommendation>
              Order {item.recommended_order_quantity} units
            </Recommendation>
            
            <ActionButton 
              onClick={() => createPurchaseOrder(item)}
              urgency={item.urgency}
            >
              Create Order
            </ActionButton>
          </ReorderRow>
        ))}
      </ReorderTable>
    </div>
  );
};
```

---

## 7. Batch Forecast

Get forecasts for multiple products at once.

### Endpoint

```
POST /api/v1/producer/batch-forecast/
```

### Request Body

```json
{
  "product_ids": [123, 124, 125, 126],
  "days": 30
}
```

### Response

```json
{
  "forecasts": [
    {
      "product_id": 123,
      "product_name": "Wireless Mouse",
      "forecast": {
        "daily_forecast": 12.5,
        "forecast_period_days": 30,
        "total_forecast": 375,
        "method": "ensemble"
      }
    },
    {
      "product_id": 124,
      "product_name": "USB Cable",
      "forecast": {
        "daily_forecast": 25.0,
        "forecast_period_days": 30,
        "total_forecast": 750,
        "method": "ensemble"
      }
    }
  ],
  "errors": [
    "Product 125 not found",
    "Error forecasting product 126: insufficient data"
  ],
  "forecast_days": 30
}
```

### Frontend Integration Example

```javascript
const getBatchForecast = async (productIds) => {
  const response = await axios.post(
    '/api/v1/producer/batch-forecast/',
    {
      product_ids: productIds,
      days: 30
    },
    {
      headers: { 'Authorization': `Bearer ${token}` }
    }
  );
  return response.data;
};

// Usage in bulk forecast view
const BulkForecastTable = ({ productIds }) => {
  const [forecasts, setForecasts] = useState([]);
  
  useEffect(() => {
    getBatchForecast(productIds).then(data => {
      setForecasts(data.forecasts);
    });
  }, [productIds]);
  
  return (
    <Table>
      <thead>
        <tr>
          <th>Product</th>
          <th>Daily Forecast</th>
          <th>30-Day Total</th>
          <th>Method</th>
        </tr>
      </thead>
      <tbody>
        {forecasts.map(f => (
          <tr key={f.product_id}>
            <td>{f.product_name}</td>
            <td>{f.forecast.daily_forecast}</td>
            <td>{f.forecast.total_forecast}</td>
            <td>{f.forecast.method}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
};
```

---

## Common Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "error": "Product not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Error message details"
}
```

---

## Data Refresh Strategy

| Endpoint | Recommended Refresh Frequency |
|----------|------------------------------|
| `/forecast/` | Daily or on-demand |
| `/stockout-prediction/` | Every few hours or real-time |
| `/optimization/` | After inventory changes |
| `/analytics/` | Daily dashboard refresh |
| `/portfolio-analytics/` | Dashboard load + periodic refresh |
| `/reorder-recommendations/` | Daily or after stock changes |

---

## Performance Notes

1. Forecast calculations use historical sales data (last 60-90 days)
2. First request for a product may be slower (cache warmup)
3. Batch forecast limited to 50 products per request
4. Portfolio analytics limited to 50 at-risk products
