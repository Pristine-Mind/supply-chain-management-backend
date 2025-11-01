from django.db.models import Count, F, Q, Avg, Case, When, Window, FloatField, Min, Max
from django.db.models.functions import Rank, Coalesce
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from producer.models import MarketplaceProduct
from .trending_serializers import TrendingProductSerializer, TrendingCategorySerializer, TrendingStatsSerializer


class TrendingProductsManager:
    """
    Manager class to handle trending products calculations and queries
    """
    
    @staticmethod
    def calculate_trending_score(queryset):
        """
        Calculate trending score based on multiple factors:
        - Recent purchases (40% weight)
        - View count (30% weight)  
        - Average rating (20% weight)
        - Recency factor (10% weight)
        """
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        day_ago = now - timedelta(days=1)
        
        return queryset.annotate(
            # Recent sales metrics
            recent_sales_count=Count(
                'product__purchase', 
                filter=Q(product__purchase__purchase_date__gte=day_ago)
            ),
            weekly_sales_count=Count(
                'product__purchase',
                filter=Q(product__purchase__purchase_date__gte=week_ago)
            ),
            total_sales=Count('product__purchase'),
            
            # View metrics
            weekly_view_count=Count(
                'product__productview',
                filter=Q(product__productview__viewed_at__gte=week_ago)
            ),
            
            # Sales velocity (sales per day over last week)
            sales_velocity=Case(
                When(weekly_sales_count__gt=0, then=F('weekly_sales_count') / 7.0),
                default=0.0,
                output_field=FloatField()
            ),
            
            # Engagement rate (views to sales ratio)
            engagement_rate=Case(
                When(
                    weekly_view_count__gt=0,
                    then=(F('weekly_sales_count') * 100.0) / F('weekly_view_count')
                ),
                default=0.0,
                output_field=FloatField()
            ),
            
            # Calculate final trending score (without complex recency calculation)
            trending_score=Case(
                When(
                    is_available=True,
                    then=(
                        # Recent purchases weight (50%)
                        (F('recent_purchases_count') * 3 + F('weekly_sales_count')) * 0.5 +
                        # View count weight (30%)
                        (F('view_count') / 100.0) * 0.3 +
                        # Rating weight (20%)
                        (Coalesce(F('rank_score'), 0) / 5.0) * 0.2
                    )
                ),
                default=0.0,
                output_field=FloatField()
            ),
            
            # Price trend indicator
            price_trend=Case(
                When(discounted_price__isnull=False, then='decreasing'),
                When(is_offer_active=True, then='promotional'),
                default='stable'
            )
        ).annotate(
            # Add ranking based on trending score
            trending_rank=Window(
                expression=Rank(),
                order_by=F('trending_score').desc()
            )
        )

    @staticmethod
    def get_trending_categories():
        """
        Get trending product categories with metrics
        """
        week_ago = timezone.now() - timedelta(days=7)
        
        return MarketplaceProduct.objects.filter(
            is_available=True
        ).values(
            category_name=F('product__category__name')
        ).annotate(
            product_count=Count('id'),
            total_sales=Count('product__purchase'),
            weekly_sales=Count(
                'product__purchase',
                filter=Q(product__purchase__purchase_date__gte=week_ago)
            ),
            avg_rating=Avg('rank_score'),
            trending_score=F('weekly_sales') * 2 + F('product_count') * 0.5
        ).order_by('-trending_score')[:10]


class TrendingProductsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for trending marketplace products with various filtering options
    """
    serializer_class = TrendingProductSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        """
        Get base queryset with trending calculations
        """
        queryset = MarketplaceProduct.objects.filter(
            is_available=True
        ).select_related(
            'product', 
            'product__user', 
            'product__user__user_profile',
            'product__category'
        ).prefetch_related(
            'bulk_price_tiers', 
            'variants', 
            'reviews'
        )
        
        return TrendingProductsManager.calculate_trending_score(queryset)
    
    def list(self, request, *args, **kwargs):
        """
        List trending products with optional filtering
        """
        queryset = self.get_queryset()
        
        # Apply filters
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(product__category__name__icontains=category)
        
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(listed_price__gte=min_price)
        if max_price:
            queryset = queryset.filter(listed_price__lte=max_price)
        
        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(product__user__user_profile__city__icontains=location)
        
        # Order by trending score
        queryset = queryset.order_by('-trending_score', '-weekly_sales_count')
        
        # Limit results
        limit = request.query_params.get('limit', 20)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:20]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data),
            'timestamp': timezone.now().isoformat()
        })

    @action(detail=False, methods=['get'])
    def top_weekly(self, request):
        """
        Get top trending products from the last week
        """
        queryset = self.get_queryset().filter(
            weekly_sales_count__gt=0
        ).order_by('-weekly_sales_count', '-trending_score')[:10]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'period': 'weekly',
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def most_viewed(self, request):
        """
        Get most viewed trending products
        """
        queryset = self.get_queryset().filter(
            view_count__gt=0
        ).order_by('-view_count', '-trending_score')[:10]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'period': 'most_viewed',
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def fastest_selling(self, request):
        """
        Get products with highest sales velocity
        """
        queryset = self.get_queryset().filter(
            sales_velocity__gt=0
        ).order_by('-sales_velocity', '-trending_score')[:10]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'period': 'fastest_selling',
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def new_trending(self, request):
        """
        Get newly listed products that are trending
        """
        week_ago = timezone.now() - timedelta(days=7)
        queryset = self.get_queryset().filter(
            listed_date__gte=week_ago,
            trending_score__gt=0.1
        ).order_by('-trending_score', '-listed_date')[:10]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'period': 'new_trending',
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """
        Get trending categories
        """
        categories = TrendingProductsManager.get_trending_categories()
        serializer = TrendingCategorySerializer(categories, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get trending products statistics
        """
        queryset = self.get_queryset()
        
        total_trending = queryset.filter(trending_score__gt=0).count()
        avg_trending_score = queryset.aggregate(
            avg_score=Avg('trending_score')
        )['avg_score'] or 0
        
        # Price range of trending products
        price_stats = queryset.filter(trending_score__gt=0).aggregate(
            min_price=Min('listed_price'),
            max_price=Max('listed_price'),
            avg_price=Avg('listed_price')
        )
        
        categories = TrendingProductsManager.get_trending_categories()
        
        stats_data = {
            'total_trending_products': total_trending,
            'trending_categories': categories,
            'top_performing_timeframe': 'weekly',
            'average_trending_score': round(avg_trending_score, 2),
            'price_range': {
                'min': price_stats['min_price'] or 0,
                'max': price_stats['max_price'] or 0,
                'average': round(price_stats['avg_price'] or 0, 2)
            }
        }
        
        serializer = TrendingStatsSerializer(stats_data)
        return Response(serializer.data)