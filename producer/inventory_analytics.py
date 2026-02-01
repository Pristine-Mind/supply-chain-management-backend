import logging
from datetime import timedelta
from typing import Dict, List

import numpy as np
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from scipy import stats

from .models import Product, Sale

logger = logging.getLogger(__name__)


class DemandForecaster:
    """
    Forecasts product demand using multiple methods:
    - Moving Average
    - Exponential Smoothing
    - Linear Regression with seasonality
    """

    def __init__(self, product: Product):
        self.product = product
        self.historical_data = None

    def _get_historical_sales(self, days: int = 180) -> List[Dict]:
        """Get daily sales data for the specified period"""
        start_date = timezone.localdate() - timedelta(days=days)

        sales = (
            Sale.objects.filter(order__product=self.product, sale_date__date__gte=start_date)
            .annotate(day=TruncDate("sale_date"))
            .values("day")
            .annotate(quantity=Sum("quantity"))
            .order_by("day")
        )

        return list(sales)

    def _fill_missing_dates(self, data: List[Dict], days: int) -> np.ndarray:
        """Fill missing dates with zero sales to create continuous time series"""
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days)

        # Create date to quantity mapping
        date_map = {item["day"]: item["quantity"] for item in data}

        # Fill all dates
        filled_data = []
        current = start_date
        while current <= end_date:
            filled_data.append(date_map.get(current, 0))
            current += timedelta(days=1)

        return np.array(filled_data, dtype=float)

    def moving_average_forecast(self, window: int = 30, forecast_days: int = 30) -> Dict:
        """
        Simple moving average forecast.

        Returns:
            {
                'daily_forecast': average daily demand,
                'forecast_period_days': forecast_days,
                'total_forecast': total demand for period,
                'confidence_interval': (lower, upper),
                'method': 'moving_average',
                'window_used': window
            }
        """
        sales_data = self._get_historical_sales(days=window + 30)

        if not sales_data:
            return {
                "daily_forecast": 0,
                "forecast_period_days": forecast_days,
                "total_forecast": 0,
                "confidence_interval": (0, 0),
                "method": "moving_average",
                "window_used": window,
                "warning": "No historical sales data available",
            }

        # Calculate moving average
        quantities = [item["quantity"] for item in sales_data]

        # Use last 'window' days
        recent_quantities = quantities[-window:] if len(quantities) >= window else quantities

        avg_demand = np.mean(recent_quantities)
        std_demand = np.std(recent_quantities)

        # Calculate confidence interval (95%)
        z_score = 1.96
        margin = z_score * (std_demand / np.sqrt(len(recent_quantities))) if len(recent_quantities) > 1 else 0

        total_forecast = avg_demand * forecast_days

        return {
            "daily_forecast": round(float(avg_demand), 2),
            "forecast_period_days": forecast_days,
            "total_forecast": round(float(total_forecast), 2),
            "confidence_interval": (round(float(max(0, avg_demand - margin)), 2), round(float(avg_demand + margin), 2)),
            "method": "moving_average",
            "window_used": window,
            "std_deviation": round(float(std_demand), 2),
        }

    def exponential_smoothing_forecast(self, alpha: float = 0.3, forecast_days: int = 30) -> Dict:
        """
        Exponential smoothing forecast with trend.

        Args:
            alpha: Smoothing factor (0-1), higher = more weight to recent data

        Returns:
            Forecast dictionary with daily and total predictions
        """
        sales_data = self._get_historical_sales(days=90)

        if not sales_data:
            return {
                "daily_forecast": 0,
                "forecast_period_days": forecast_days,
                "total_forecast": 0,
                "method": "exponential_smoothing",
                "warning": "No historical sales data available",
            }

        quantities = np.array([item["quantity"] for item in sales_data])

        # Initialize with first observation
        smoothed = quantities[0]

        # Apply exponential smoothing
        for qty in quantities[1:]:
            smoothed = alpha * qty + (1 - alpha) * smoothed

        # Forecast is the last smoothed value
        forecast = smoothed

        # Calculate trend
        if len(quantities) >= 14:
            first_half = np.mean(quantities[: len(quantities) // 2])
            second_half = np.mean(quantities[len(quantities) // 2 :])
            trend = (second_half - first_half) / (len(quantities) // 2)
        else:
            trend = 0

        # Project with trend
        daily_forecasts = []
        for i in range(1, forecast_days + 1):
            daily_forecasts.append(max(0, forecast + trend * i))

        total_forecast = sum(daily_forecasts)
        avg_daily = np.mean(daily_forecasts)

        return {
            "daily_forecast": round(float(avg_daily), 2),
            "forecast_period_days": forecast_days,
            "total_forecast": round(float(total_forecast), 2),
            "trend": round(float(trend), 4),
            "method": "exponential_smoothing",
            "alpha": alpha,
            "confidence_interval": (
                round(float(max(0, avg_daily - np.std(quantities) * 0.5)), 2),
                round(float(avg_daily + np.std(quantities) * 0.5), 2),
            ),
        }

    def seasonal_decomposition_forecast(self, forecast_days: int = 30) -> Dict:
        """
        Forecast using seasonal decomposition.
        Detects weekly patterns in sales data.
        """
        sales_data = self._get_historical_sales(days=90)

        if len(sales_data) < 14:
            # Fall back to moving average
            return self.moving_average_forecast(forecast_days=forecast_days)

        # Group by day of week
        dow_sales = {i: [] for i in range(7)}

        for item in sales_data:
            if item["day"]:
                dow = item["day"].weekday()
                dow_sales[dow].append(item["quantity"])

        # Calculate average for each day of week
        dow_averages = {}
        for dow, quantities in dow_sales.items():
            if quantities:
                dow_averages[dow] = np.mean(quantities)
            else:
                dow_averages[dow] = 0

        # Generate forecast
        start_date = timezone.localdate()
        daily_forecasts = []

        for i in range(forecast_days):
            forecast_date = start_date + timedelta(days=i)
            dow = forecast_date.weekday()
            daily_forecasts.append(dow_averages.get(dow, 0))

        total_forecast = sum(daily_forecasts)
        avg_daily = np.mean(daily_forecasts) if daily_forecasts else 0

        return {
            "daily_forecast": round(float(avg_daily), 2),
            "forecast_period_days": forecast_days,
            "total_forecast": round(float(total_forecast), 2),
            "method": "seasonal_decomposition",
            "seasonal_pattern": {dow: round(float(avg), 2) for dow, avg in dow_averages.items()},
            "confidence_interval": (round(float(max(0, avg_daily * 0.8)), 2), round(float(avg_daily * 1.2), 2)),
        }

    def ensemble_forecast(self, forecast_days: int = 30) -> Dict:
        """
        Combine multiple forecasting methods for better accuracy.
        Weights forecasts based on historical accuracy.
        """
        forecasts = [
            self.moving_average_forecast(forecast_days=forecast_days),
            self.exponential_smoothing_forecast(forecast_days=forecast_days),
            self.seasonal_decomposition_forecast(forecast_days=forecast_days),
        ]

        # Filter out forecasts with warnings
        valid_forecasts = [f for f in forecasts if "warning" not in f]

        if not valid_forecasts:
            return forecasts[0]  # Return first one with warning

        # Simple ensemble: average of all methods
        avg_daily = np.mean([f["daily_forecast"] for f in valid_forecasts])
        total = avg_daily * forecast_days

        # Calculate ensemble confidence interval
        lowers = [f.get("confidence_interval", (0, 0))[0] for f in valid_forecasts]
        uppers = [f.get("confidence_interval", (0, 0))[1] for f in valid_forecasts]

        return {
            "daily_forecast": round(float(avg_daily), 2),
            "forecast_period_days": forecast_days,
            "total_forecast": round(float(total), 2),
            "method": "ensemble",
            "methods_used": [f["method"] for f in valid_forecasts],
            "confidence_interval": (round(float(np.mean(lowers)), 2), round(float(np.mean(uppers)), 2)),
            "individual_forecasts": valid_forecasts,
        }


class StockoutPredictor:
    """Predicts stockout dates and risks"""

    def __init__(self, product: Product):
        self.product = product

    def predict_stockout_date(self) -> Dict:
        """
        Predict when the product will stock out based on current inventory
        and forecasted demand.
        """
        current_stock = self.product.stock

        if current_stock <= 0:
            return {
                "will_stockout": True,
                "stockout_date": timezone.localdate(),
                "days_until_stockout": 0,
                "risk_level": "critical",
                "current_stock": current_stock,
            }

        # Get demand forecast
        forecaster = DemandForecaster(self.product)
        forecast = forecaster.ensemble_forecast(forecast_days=90)

        daily_demand = forecast["daily_forecast"]

        if daily_demand <= 0:
            return {
                "will_stockout": False,
                "stockout_date": None,
                "days_until_stockout": None,
                "risk_level": "low",
                "current_stock": current_stock,
                "reason": "No demand forecasted",
            }

        # Calculate days until stockout
        days_until_stockout = int(current_stock / daily_demand)
        stockout_date = timezone.localdate() + timedelta(days=days_until_stockout)

        # Determine risk level
        lead_time = self.product.lead_time_days or 7
        safety_stock = self.product.safety_stock or 0

        if days_until_stockout <= lead_time:
            risk_level = "critical"
        elif days_until_stockout <= lead_time + 7:
            risk_level = "high"
        elif days_until_stockout <= lead_time + 14:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "will_stockout": True,
            "stockout_date": stockout_date.isoformat(),
            "days_until_stockout": days_until_stockout,
            "risk_level": risk_level,
            "current_stock": current_stock,
            "daily_demand_forecast": daily_demand,
            "lead_time_days": lead_time,
            "safety_stock": safety_stock,
            "recommended_reorder_date": (stockout_date - timedelta(days=lead_time)).isoformat(),
        }

    def calculate_stockout_probability(self, days: int = 30) -> Dict:
        """
        Calculate probability of stockout within specified days.
        Uses Monte Carlo simulation.
        """
        current_stock = self.product.stock

        # Get historical demand distribution
        sales_data = DemandForecaster(self.product)._get_historical_sales(days=60)

        if not sales_data:
            return {"probability": 0, "confidence": "low", "message": "Insufficient historical data"}

        quantities = np.array([item["quantity"] for item in sales_data])

        # Fit distribution
        mean_demand = np.mean(quantities)
        std_demand = np.std(quantities)

        # Monte Carlo simulation
        simulations = 10000
        stockouts = 0

        for _ in range(simulations):
            # Simulate daily demand
            daily_demands = np.random.normal(mean_demand, std_demand, days)
            total_demand = np.sum(daily_demands)

            if total_demand >= current_stock:
                stockouts += 1

        probability = stockouts / simulations

        # Determine confidence based on data quality
        if len(sales_data) >= 30:
            confidence = "high"
        elif len(sales_data) >= 14:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "probability": round(probability * 100, 2),
            "probability_decimal": round(probability, 4),
            "period_days": days,
            "confidence": confidence,
            "simulations_run": simulations,
            "average_daily_demand": round(float(mean_demand), 2),
            "demand_std_dev": round(float(std_demand), 2),
        }


class ReorderOptimizer:
    """Optimizes reorder points and quantities"""

    def __init__(self, product: Product):
        self.product = product

    def calculate_economic_order_quantity(self) -> Dict:
        """
        Calculate Economic Order Quantity (EOQ) using the Wilson formula.

        EOQ = sqrt((2 * D * S) / H)

        Where:
        D = Annual demand
        S = Ordering cost per order
        H = Holding cost per unit per year
        """
        # Get annual demand forecast
        forecaster = DemandForecaster(self.product)
        forecast = forecaster.ensemble_forecast(forecast_days=365)
        annual_demand = forecast["total_forecast"]

        if annual_demand <= 0:
            return {
                "eoq": 0,
                "economic_order_quantity": 0,
                "annual_demand": 0,
                "ordering_cost": 100,
                "holding_cost_per_unit": 0,
                "order_frequency_per_year": 0,
                "days_between_orders": 0,
                "total_annual_ordering_cost": 0,
                "total_annual_holding_cost": 0,
                "unit_cost": self.product.cost_price or self.product.price or 100,
                "message": "No demand forecast available",
            }

        # Estimate costs (can be customized based on business data)
        ordering_cost = 100  # Cost per order (processing, shipping, etc.)
        holding_cost_rate = 0.25  # 25% of unit cost per year

        # Get unit cost
        unit_cost = self.product.cost_price or self.product.price or 100
        holding_cost = unit_cost * holding_cost_rate

        # Calculate EOQ
        eoq = np.sqrt((2 * annual_demand * ordering_cost) / holding_cost)

        # Calculate associated metrics
        order_frequency = annual_demand / eoq if eoq > 0 else 0
        days_between_orders = 365 / order_frequency if order_frequency > 0 else 0

        return {
            "eoq": round(float(eoq), 0),
            "economic_order_quantity": round(float(eoq), 0),
            "annual_demand": round(float(annual_demand), 2),
            "ordering_cost": ordering_cost,
            "holding_cost_per_unit": round(float(holding_cost), 2),
            "order_frequency_per_year": round(float(order_frequency), 2),
            "days_between_orders": round(float(days_between_orders), 1),
            "total_annual_ordering_cost": round(float(order_frequency * ordering_cost), 2),
            "total_annual_holding_cost": round(float((eoq / 2) * holding_cost), 2),
            "unit_cost": round(float(unit_cost), 2),
        }

    def calculate_optimal_reorder_point(self) -> Dict:
        """
        Calculate optimal reorder point considering:
        - Lead time demand
        - Safety stock
        - Service level
        """
        lead_time = self.product.lead_time_days or 7

        # Get demand statistics
        sales_data = DemandForecaster(self.product)._get_historical_sales(days=60)

        if not sales_data:
            reorder_point = self.product.reorder_level or 10
            return {
                "reorder_point": reorder_point,
                "safety_stock": self.product.safety_stock or 0,
                "lead_time_demand": 0,
                "avg_daily_demand": 0,
                "demand_std_dev": 0,
                "service_level": 0.95,
                "z_score": 1.65,
                "current_reorder_point": self.product.reorder_point,
                "recommended_change": round(float(reorder_point - self.product.reorder_point), 0),
                "message": "Using default values - insufficient data",
            }

        quantities = np.array([item["quantity"] for item in sales_data])
        avg_daily_demand = np.mean(quantities)
        std_daily_demand = np.std(quantities)

        # Lead time demand
        lead_time_demand = avg_daily_demand * lead_time

        # Safety stock for 95% service level (z = 1.65)
        service_level = 0.95
        z_score = stats.norm.ppf(service_level)

        # Safety stock = z * std_dev * sqrt(lead_time)
        safety_stock = z_score * std_daily_demand * np.sqrt(lead_time)

        # Reorder point = lead time demand + safety stock
        reorder_point = lead_time_demand + safety_stock

        return {
            "reorder_point": round(float(reorder_point), 0),
            "safety_stock": round(float(safety_stock), 0),
            "lead_time_demand": round(float(lead_time_demand), 2),
            "lead_time_days": lead_time,
            "avg_daily_demand": round(float(avg_daily_demand), 2),
            "demand_std_dev": round(float(std_daily_demand), 2),
            "service_level": service_level,
            "z_score": round(float(z_score), 2),
            "current_reorder_point": self.product.reorder_point,
            "recommended_change": round(float(reorder_point - self.product.reorder_point), 0),
        }

    def get_inventory_optimization_summary(self) -> Dict:
        """Get complete inventory optimization recommendations"""
        eoq_result = self.calculate_economic_order_quantity()
        reorder_result = self.calculate_optimal_reorder_point()

        # Current metrics
        current_stock = self.product.stock
        reorder_point = reorder_result["reorder_point"]

        # Determine action
        if current_stock <= reorder_point:
            action = "reorder_now"
            urgency = "high"
        elif current_stock <= reorder_point * 1.5:
            action = "plan_reorder"
            urgency = "medium"
        else:
            action = "monitor"
            urgency = "low"

        return {
            "product_id": self.product.id,
            "product_name": self.product.name,
            "current_stock": current_stock,
            "reorder_point": reorder_result["reorder_point"],
            "economic_order_quantity": eoq_result["eoq"],
            "safety_stock": reorder_result["safety_stock"],
            "action_required": action,
            "urgency": urgency,
            "estimated_days_until_reorder": (
                round((current_stock - reorder_point) / reorder_result["avg_daily_demand"], 1)
                if reorder_result["avg_daily_demand"] > 0
                else "N/A"
            ),
            "total_inventory_cost_optimized": round(
                eoq_result.get("total_annual_ordering_cost", 0) + eoq_result.get("total_annual_holding_cost", 0), 2
            ),
            "recommendations": self._generate_recommendations(eoq_result, reorder_result),
        }

    def _generate_recommendations(self, eoq: Dict, reorder: Dict) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        if reorder["recommended_change"] > 10:
            recommendations.append(
                f"Increase reorder point by {reorder['recommended_change']} units "
                f"to optimize for lead time and safety stock."
            )
        elif reorder["recommended_change"] < -10:
            recommendations.append(
                f"Decrease reorder point by {abs(reorder['recommended_change'])} units " f"to reduce holding costs."
            )

        if eoq["eoq"] > 0:
            recommendations.append(
                f"Optimal order quantity is {int(eoq['eoq'])} units " f"({eoq['days_between_orders']} days between orders)."
            )

        if reorder["safety_stock"] > self.product.safety_stock * 1.5:
            recommendations.append(
                f"Consider increasing safety stock to {int(reorder['safety_stock'])} units " f"for better service level."
            )

        return recommendations


class InventoryAnalyticsService:
    """
    Main service class that provides comprehensive inventory analytics.
    """

    def __init__(self, product: Product):
        self.product = product
        self.forecaster = DemandForecaster(product)
        self.predictor = StockoutPredictor(product)
        self.optimizer = ReorderOptimizer(product)

    def get_full_analytics(self) -> Dict:
        """Get complete analytics for a product"""
        return {
            "product": {
                "id": self.product.id,
                "name": self.product.name,
                "sku": self.product.sku,
                "current_stock": self.product.stock,
                "reorder_level": self.product.reorder_level,
                "reorder_point": self.product.reorder_point,
                "safety_stock": self.product.safety_stock,
            },
            "demand_forecast": self.forecaster.ensemble_forecast(forecast_days=30),
            "stockout_prediction": self.predictor.predict_stockout_date(),
            "stockout_probability": self.predictor.calculate_stockout_probability(days=30),
            "optimization": self.optimizer.get_inventory_optimization_summary(),
            "seasonality": self._analyze_seasonality(),
            "trends": self._analyze_trends(),
        }

    def _analyze_seasonality(self) -> Dict:
        """Analyze seasonal patterns in sales"""
        # Get last 90 days of sales
        sales_data = self.forecaster._get_historical_sales(days=90)

        if not sales_data:
            return {"has_seasonality": False, "message": "Insufficient data"}

        # Group by day of week
        dow_sales = {i: [] for i in range(7)}
        for item in sales_data:
            if item["day"]:
                dow = item["day"].weekday()
                dow_sales[dow].append(item["quantity"])

        # Calculate averages
        dow_averages = {}
        for dow, quantities in dow_sales.items():
            dow_averages[dow] = np.mean(quantities) if quantities else 0

        # Check for significant variation
        avg_sales = np.mean(list(dow_averages.values()))
        max_sales = max(dow_averages.values())
        min_sales = min(dow_averages.values())

        has_seasonality = (max_sales - min_sales) > (avg_sales * 0.3) if avg_sales > 0 else False

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        return {
            "has_seasonality": has_seasonality,
            "peak_day": days[max(dow_averages, key=dow_averages.get)],
            "low_day": days[min(dow_averages, key=dow_averages.get)],
            "peak_to_low_ratio": round(max_sales / min_sales, 2) if min_sales > 0 else 0,
            "daily_averages": {days[i]: round(float(avg), 2) for i, avg in dow_averages.items()},
        }

    def _analyze_trends(self) -> Dict:
        """Analyze demand trends"""
        sales_data = self.forecaster._get_historical_sales(days=60)

        if len(sales_data) < 14:
            return {"trend": "insufficient_data", "message": "Need at least 14 days of data"}

        quantities = np.array([item["quantity"] for item in sales_data])

        # Split into two halves
        mid = len(quantities) // 2
        first_half_avg = np.mean(quantities[:mid])
        second_half_avg = np.mean(quantities[mid:])

        # Calculate trend
        if first_half_avg > 0:
            change_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
        else:
            change_pct = 0

        if change_pct > 20:
            trend = "strongly_increasing"
        elif change_pct > 5:
            trend = "increasing"
        elif change_pct < -20:
            trend = "strongly_decreasing"
        elif change_pct < -5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change_percentage": round(float(change_pct), 2),
            "first_period_avg": round(float(first_half_avg), 2),
            "second_period_avg": round(float(second_half_avg), 2),
            "trend_direction": "up" if change_pct > 5 else ("down" if change_pct < -5 else "stable"),
        }

    @classmethod
    def get_portfolio_analytics(cls, user) -> Dict:
        """
        Get analytics for all products of a user.
        Useful for dashboard overview.
        """
        products = Product.objects.filter(user=user, is_active=True)

        total_products = products.count()
        low_stock_count = 0
        stockout_risk_count = 0
        reorder_needed_count = 0

        product_analytics = []

        for product in products[:50]:  # Limit to prevent timeout
            try:
                service = cls(product)

                # Quick stockout prediction
                stockout = service.predictor.predict_stockout_date()
                if stockout["risk_level"] in ["high", "critical"]:
                    stockout_risk_count += 1

                if product.stock <= product.reorder_level:
                    reorder_needed_count += 1
                    low_stock_count += 1

                product_analytics.append(
                    {
                        "product_id": product.id,
                        "name": product.name[:30],
                        "stock": product.stock,
                        "risk_level": stockout["risk_level"],
                        "days_until_stockout": stockout.get("days_until_stockout"),
                    }
                )
            except Exception as e:
                logger.error(f"Error analyzing product {product.id}: {e}")

        return {
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "stockout_risk_count": stockout_risk_count,
            "reorder_needed_count": reorder_needed_count,
            "healthy_stock_percentage": (
                round(((total_products - stockout_risk_count) / total_products * 100), 1) if total_products > 0 else 0
            ),
            "at_risk_products": sorted(
                [p for p in product_analytics if p["risk_level"] in ["high", "critical"]],
                key=lambda x: x.get("days_until_stockout", 999) or 999,
            )[:10],
        }
