from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .inventory_analytics import (
    DemandForecaster,
    InventoryAnalyticsService,
    ReorderOptimizer,
    StockoutPredictor,
)
from .models import Product


class ProductForecastView(APIView):
    """
    Get demand forecast for a specific product.

    Query Parameters:
    - days: Forecast period (default: 30, max: 90)
    - method: 'moving_average', 'exponential_smoothing', 'seasonal', 'ensemble' (default)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, user=request.user)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        forecast_days = min(int(request.query_params.get("days", 30)), 90)
        method = request.query_params.get("method", "ensemble")

        forecaster = DemandForecaster(product)

        if method == "moving_average":
            forecast = forecaster.moving_average_forecast(forecast_days=forecast_days)
        elif method == "exponential_smoothing":
            forecast = forecaster.exponential_smoothing_forecast(forecast_days=forecast_days)
        elif method == "seasonal":
            forecast = forecaster.seasonal_decomposition_forecast(forecast_days=forecast_days)
        else:
            forecast = forecaster.ensemble_forecast(forecast_days=forecast_days)

        return Response(
            {
                "product_id": product_id,
                "product_name": product.name,
                "forecast": forecast,
                "method_used": method,
                "forecast_days": forecast_days,
            }
        )


class ProductStockoutPredictionView(APIView):
    """
    Get stockout prediction and risk assessment for a product.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, user=request.user)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        predictor = StockoutPredictor(product)

        stockout_prediction = predictor.predict_stockout_date()
        probability_30d = predictor.calculate_stockout_probability(days=30)
        probability_60d = predictor.calculate_stockout_probability(days=60)

        return Response(
            {
                "product_id": product_id,
                "product_name": product.name,
                "current_stock": product.stock,
                "stockout_prediction": stockout_prediction,
                "stockout_probability": {"30_days": probability_30d, "60_days": probability_60d},
                "risk_assessment": {
                    "level": stockout_prediction["risk_level"],
                    "action_required": stockout_prediction["risk_level"] in ["high", "critical"],
                    "recommended_action": self._get_recommended_action(stockout_prediction),
                },
            }
        )

    def _get_recommended_action(self, prediction):
        """Generate recommended action based on prediction"""
        risk_level = prediction.get("risk_level")
        days = prediction.get("days_until_stockout")

        if risk_level == "critical":
            return f"URGENT: Reorder immediately. Stockout predicted in {days} days."
        elif risk_level == "high":
            return f"Plan to reorder soon. Stockout expected in {days} days."
        elif risk_level == "medium":
            return f"Monitor stock levels. Reorder recommended in {max(0, days - 14)} days."
        else:
            return "Stock levels healthy. Continue monitoring."


class ProductOptimizationView(APIView):
    """
    Get inventory optimization recommendations for a product.
    Includes EOQ, reorder point, and safety stock calculations.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, user=request.user)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        optimizer = ReorderOptimizer(product)

        return Response(
            {
                "product_id": product_id,
                "product_name": product.name,
                "current_settings": {
                    "stock": product.stock,
                    "reorder_level": product.reorder_level,
                    "reorder_point": product.reorder_point,
                    "safety_stock": product.safety_stock,
                    "lead_time_days": product.lead_time_days,
                },
                "optimization": optimizer.get_inventory_optimization_summary(),
                "eoq_analysis": optimizer.calculate_economic_order_quantity(),
                "reorder_point_analysis": optimizer.calculate_optimal_reorder_point(),
            }
        )

    def post(self, request, product_id):
        """
        Apply optimization recommendations to product.
        Updates reorder point, safety stock, etc.
        """
        try:
            product = Product.objects.get(id=product_id, user=request.user)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        optimizer = ReorderOptimizer(product)
        reorder_calc = optimizer.calculate_optimal_reorder_point()
        eoq_calc = optimizer.calculate_economic_order_quantity()

        # Update product with optimized values
        updates = {}

        if request.data.get("apply_reorder_point", True):
            product.reorder_point = int(reorder_calc["reorder_point"])
            updates["reorder_point"] = product.reorder_point

        if request.data.get("apply_safety_stock", True):
            product.safety_stock = int(reorder_calc["safety_stock"])
            updates["safety_stock"] = product.safety_stock

        if request.data.get("apply_reorder_quantity", True):
            product.reorder_quantity = int(eoq_calc["eoq"])
            updates["reorder_quantity"] = product.reorder_quantity

        if updates:
            product.save(update_fields=list(updates.keys()))

        return Response(
            {
                "success": True,
                "message": "Optimization settings applied",
                "updates": updates,
                "product": {"id": product.id, "name": product.name, "updated_fields": list(updates.keys())},
            }
        )


class ProductFullAnalyticsView(APIView):
    """
    Get complete analytics for a product including:
    - Demand forecast
    - Stockout prediction
    - Optimization recommendations
    - Seasonality analysis
    - Trend analysis
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, user=request.user)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        service = InventoryAnalyticsService(product)
        analytics = service.get_full_analytics()

        return Response(analytics)


class PortfolioAnalyticsView(APIView):
    """
    Get portfolio-level analytics for all user's products.
    Provides dashboard overview data.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        analytics = InventoryAnalyticsService.get_portfolio_analytics(request.user)

        return Response({"portfolio_analytics": analytics, "generated_at": timezone.now().isoformat()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reorder_recommendations(request):
    """
    Get a list of products that need reordering with recommendations.

    Query Parameters:
    - risk_level: Filter by risk level (critical, high, medium, low)
    - limit: Maximum number of products (default: 20)
    """
    risk_filter = request.query_params.get("risk_level")
    limit = min(int(request.query_params.get("limit", 20)), 100)

    products = Product.objects.filter(user=request.user, is_active=True)
    recommendations = []

    for product in products:
        try:
            service = InventoryAnalyticsService(product)
            stockout = service.predictor.predict_stockout_date()
            optimization = service.optimizer.get_inventory_optimization_summary()

            if risk_filter and stockout["risk_level"] != risk_filter:
                continue

            if stockout["risk_level"] in ["critical", "high"]:
                recommendations.append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "sku": product.sku,
                        "current_stock": product.stock,
                        "risk_level": stockout["risk_level"],
                        "days_until_stockout": stockout.get("days_until_stockout"),
                        "stockout_date": stockout.get("stockout_date"),
                        "recommended_order_quantity": optimization["economic_order_quantity"],
                        "urgency": optimization["urgency"],
                        "action": optimization["action_required"],
                    }
                )
        except Exception as e:
            continue

    # Sort by urgency
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda x: urgency_order.get(x["risk_level"], 4))

    return Response(
        {
            "recommendations": recommendations[:limit],
            "total_recommended": len(recommendations),
            "critical_count": sum(1 for r in recommendations if r["risk_level"] == "critical"),
            "high_count": sum(1 for r in recommendations if r["risk_level"] == "high"),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def batch_forecast(request):
    """
    Get forecasts for multiple products at once.

    Request Body:
    {
        "product_ids": [1, 2, 3],
        "days": 30
    }
    """
    product_ids = request.data.get("product_ids", [])
    days = min(request.data.get("days", 30), 90)

    if not product_ids:
        return Response({"error": "No product_ids provided"}, status=status.HTTP_400_BAD_REQUEST)

    forecasts = []
    errors = []

    for product_id in product_ids[:50]:  # Limit batch size
        try:
            product = Product.objects.get(id=product_id, user=request.user)
            forecaster = DemandForecaster(product)
            forecast = forecaster.ensemble_forecast(forecast_days=days)

            forecasts.append({"product_id": product_id, "product_name": product.name, "forecast": forecast})
        except Product.DoesNotExist:
            errors.append(f"Product {product_id} not found")
        except Exception as e:
            errors.append(f"Error forecasting product {product_id}: {str(e)}")

    return Response({"forecasts": forecasts, "errors": errors if errors else None, "forecast_days": days})


from django.utils import timezone
