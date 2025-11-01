from django.db.models import Count, Sum, F, Q, Avg, Case, When, DecimalField
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from producer.models import MarketplaceProduct
from producer.serializers import MarketplaceProductSerializer


class TrendingProductSerializer(MarketplaceProductSerializer):
    """
    Extended serializer for trending products with additional trending metrics
    """
    trending_score = serializers.FloatField(read_only=True)
    total_sales = serializers.IntegerField(read_only=True)
    recent_sales_count = serializers.IntegerField(read_only=True)
    weekly_sales_count = serializers.IntegerField(read_only=True)
    weekly_view_count = serializers.IntegerField(read_only=True)
    sales_velocity = serializers.FloatField(read_only=True)
    engagement_rate = serializers.FloatField(read_only=True)
    trending_rank = serializers.IntegerField(read_only=True)
    price_trend = serializers.CharField(read_only=True)
    
    class Meta(MarketplaceProductSerializer.Meta):
        fields = MarketplaceProductSerializer.Meta.fields + [
            'trending_score',
            'total_sales',
            'recent_sales_count',
            'weekly_sales_count',
            'weekly_view_count',
            'sales_velocity',
            'engagement_rate',
            'trending_rank',
            'price_trend',
        ]


class TrendingCategorySerializer(serializers.Serializer):
    """
    Serializer for trending product categories
    """
    category_name = serializers.CharField()
    product_count = serializers.IntegerField()
    total_sales = serializers.IntegerField()
    avg_rating = serializers.FloatField()
    trending_score = serializers.FloatField()


class TrendingStatsSerializer(serializers.Serializer):
    """
    Serializer for trending products statistics
    """
    total_trending_products = serializers.IntegerField()
    trending_categories = TrendingCategorySerializer(many=True)
    top_performing_timeframe = serializers.CharField()
    average_trending_score = serializers.FloatField()
    price_range = serializers.DictField()