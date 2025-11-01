from django.db.models import Count, F, Q, Avg, Case, When, Window, FloatField, Min, Max, Value, CharField, Sum
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
                'sales', 
                filter=Q(sales__sale_date__gte=day_ago)
            ),
            weekly_sales_count=Count(
                'sales',
                filter=Q(sales__sale_date__gte=week_ago)
            ),
            total_sales=Count('sales'),
            
            # View metrics
            weekly_view_count=Count(
                'views',
                filter=Q(views__timestamp__gte=week_ago)
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
            
            # Calculate final trending score (with explicit type casting)
            trending_score=Case(
                When(
                    is_available=True,
                    then=(
                        # Recent purchases weight (50%) - cast to float
                        (F('recent_purchases_count') * 3.0 + F('weekly_sales_count') * 1.0) * 0.5 +
                        # View count weight (30%) - cast to float
                        (F('view_count') * 1.0 / 100.0) * 0.3 +
                        # Rating weight (20%) - cast to float
                        (Coalesce(F('rank_score'), 0.0) / 5.0) * 0.2
                    )
                ),
                default=0.0,
                output_field=FloatField()
            ),
            
            # Price trend indicator (simplified)
            price_trend=Case(
                When(discounted_price__isnull=False, then=Value('decreasing')),
                When(
                    Q(offer_start__isnull=False) & Q(offer_end__isnull=False), 
                    then=Value('promotional')
                ),
                default=Value('stable'),
                output_field=CharField()
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
            category_name=F('product__category')
        ).annotate(
            product_count=Count('id'),
            total_sales=Count('sales'),
            weekly_sales=Count(
                'sales',
                filter=Q(sales__sale_date__gte=week_ago)
            ),
            avg_rating=Avg('rank_score'),
            trending_score=F('weekly_sales') * 2.0 + F('product_count') * 0.5
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
            'product__user__user_profile'
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

    @action(detail=False, methods=['get'])
    def deals(self, request):
        """
        Get all current deals and discounted products
        """
        now = timezone.now()
        queryset = self.get_queryset().filter(
            Q(discounted_price__isnull=False) |
            (
                Q(offer_start__isnull=False) & 
                Q(offer_end__isnull=False) &
                Q(offer_start__lte=now) &
                Q(offer_end__gte=now)
            )
        ).order_by('-trending_score')
        
        # Apply category filter if provided
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(product__category__icontains=category)
        
        # Apply discount percentage filter
        min_discount = request.query_params.get('min_discount')
        if min_discount:
            try:
                min_discount = float(min_discount)
                # Calculate discount percentage: ((listed - discounted) / listed) * 100
                queryset = queryset.extra(
                    where=[
                        "((listed_price - COALESCE(discounted_price, listed_price)) / listed_price * 100) >= %s"
                    ],
                    params=[min_discount]
                )
            except (ValueError, TypeError):
                pass
        
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
            'timestamp': timezone.now().isoformat(),
            'type': 'deals'
        })

    @action(detail=False, methods=['get'])
    def flash_sales(self, request):
        """
        Get products with active time-limited offers (flash sales)
        """
        now = timezone.now()
        # Products with active offers ending within 24 hours
        tomorrow = now + timedelta(days=1)
        
        queryset = self.get_queryset().filter(
            offer_start__isnull=False,
            offer_end__isnull=False,
            offer_start__lte=now,
            offer_end__gte=now,
            offer_end__lte=tomorrow  # Ending within 24 hours
        ).order_by('offer_end', '-trending_score')[:15]
        
        serializer = self.get_serializer(queryset, many=True)
        
        # Add countdown information to each product
        results = []
        for product_data in serializer.data:
            # Get the actual product to calculate countdown
            try:
                product = MarketplaceProduct.objects.get(id=product_data['id'])
                countdown_seconds = (product.offer_end - now).total_seconds()
                product_data['countdown_seconds'] = max(0, countdown_seconds)
                product_data['countdown_hours'] = max(0, countdown_seconds / 3600)
            except MarketplaceProduct.DoesNotExist:
                product_data['countdown_seconds'] = 0
                product_data['countdown_hours'] = 0
            
            results.append(product_data)
        
        return Response({
            'results': results,
            'count': len(results),
            'timestamp': timezone.now().isoformat(),
            'type': 'flash_sales'
        })

    @action(detail=False, methods=['get'])
    def best_discounts(self, request):
        """
        Get products with the highest discount percentages
        """
        queryset = self.get_queryset().filter(
            discounted_price__isnull=False,
            listed_price__gt=0
        ).extra(
            select={
                'discount_percentage': '((listed_price - discounted_price) / listed_price * 100)'
            }
        ).order_by('-discount_percentage', '-trending_score')
        
        # Filter by minimum discount if specified
        min_discount = request.query_params.get('min_discount', 10)
        try:
            min_discount = float(min_discount)
            queryset = queryset.extra(
                where=["((listed_price - discounted_price) / listed_price * 100) >= %s"],
                params=[min_discount]
            )
        except (ValueError, TypeError):
            pass
        
        # Limit results
        limit = request.query_params.get('limit', 15)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:15]
        
        serializer = self.get_serializer(queryset, many=True)
        
        # Add discount percentage to each result
        results = []
        for product_data in serializer.data:
            try:
                product = MarketplaceProduct.objects.get(id=product_data['id'])
                if product.discounted_price and product.listed_price > 0:
                    discount_pct = ((product.listed_price - product.discounted_price) / product.listed_price) * 100
                    product_data['discount_percentage'] = round(discount_pct, 1)
                    product_data['savings_amount'] = round(product.listed_price - product.discounted_price, 2)
                else:
                    product_data['discount_percentage'] = 0
                    product_data['savings_amount'] = 0
            except MarketplaceProduct.DoesNotExist:
                product_data['discount_percentage'] = 0
                product_data['savings_amount'] = 0
            
            results.append(product_data)
        
        return Response({
            'results': results,
            'count': len(results),
            'timestamp': timezone.now().isoformat(),
            'type': 'best_discounts'
        })

    @action(detail=False, methods=['get'])
    def seasonal_deals(self, request):
        """
        Get seasonal deals and special promotional products
        """
        now = timezone.now()
        
        # Products with active offers or discounts
        queryset = self.get_queryset().filter(
            Q(discounted_price__isnull=False) |
            (
                Q(offer_start__isnull=False) & 
                Q(offer_end__isnull=False) &
                Q(offer_start__lte=now) &
                Q(offer_end__gte=now)
            )
        )
        
        # Filter by season/duration if specified
        duration = request.query_params.get('duration', 'week')
        if duration == 'today':
            end_time = now + timedelta(days=1)
        elif duration == 'week':
            end_time = now + timedelta(days=7)
        elif duration == 'month':
            end_time = now + timedelta(days=30)
        else:
            end_time = now + timedelta(days=7)
        
        # Filter offers ending within the specified duration
        queryset = queryset.filter(
            Q(offer_end__isnull=True) |  # No end date (permanent discount)
            Q(offer_end__lte=end_time)   # Ending within specified duration
        ).order_by('-trending_score')
        
        # Apply category filter
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(product__category__icontains=category)
        
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
            'timestamp': timezone.now().isoformat(),
            'type': 'seasonal_deals',
            'duration': duration
        })

    @action(detail=False, methods=['get'])
    def deal_categories(self, request):
        """
        Get categories with the most deals and their statistics
        """
        now = timezone.now()
        
        # Get categories with active deals
        categories_with_deals = MarketplaceProduct.objects.filter(
            is_available=True
        ).filter(
            Q(discounted_price__isnull=False) |
            (
                Q(offer_start__isnull=False) & 
                Q(offer_end__isnull=False) &
                Q(offer_start__lte=now) &
                Q(offer_end__gte=now)
            )
        ).values(
            category_name=F('product__category')
        ).annotate(
            deal_count=Count('id'),
            avg_discount=Avg(
                Case(
                    When(
                        discounted_price__isnull=False,
                        then=((F('listed_price') - F('discounted_price')) / F('listed_price')) * 100
                    ),
                    default=0,
                    output_field=FloatField()
                )
            ),
            max_discount=Max(
                Case(
                    When(
                        discounted_price__isnull=False,
                        then=((F('listed_price') - F('discounted_price')) / F('listed_price')) * 100
                    ),
                    default=0,
                    output_field=FloatField()
                )
            ),
            total_savings=Sum(
                Case(
                    When(
                        discounted_price__isnull=False,
                        then=F('listed_price') - F('discounted_price')
                    ),
                    default=0,
                    output_field=FloatField()
                )
            )
        ).order_by('-deal_count', '-avg_discount')[:10]
        
        return Response({
            'results': list(categories_with_deals),
            'count': len(categories_with_deals),
            'timestamp': timezone.now().isoformat(),
            'type': 'deal_categories'
        })

    @action(detail=False, methods=['get'])
    def deal_stats(self, request):
        """
        Get comprehensive statistics about current deals
        """
        now = timezone.now()
        queryset = self.get_queryset()
        
        # Count different types of deals
        total_deals = queryset.filter(
            Q(discounted_price__isnull=False) |
            (
                Q(offer_start__isnull=False) & 
                Q(offer_end__isnull=False) &
                Q(offer_start__lte=now) &
                Q(offer_end__gte=now)
            )
        ).count()
        
        discount_deals = queryset.filter(discounted_price__isnull=False).count()
        
        active_offers = queryset.filter(
            offer_start__isnull=False,
            offer_end__isnull=False,
            offer_start__lte=now,
            offer_end__gte=now
        ).count()
        
        # Calculate average discount
        avg_discount_info = queryset.filter(
            discounted_price__isnull=False,
            listed_price__gt=0
        ).aggregate(
            avg_discount=Avg(
                ((F('listed_price') - F('discounted_price')) / F('listed_price')) * 100,
                output_field=FloatField()
            ),
            max_discount=Max(
                ((F('listed_price') - F('discounted_price')) / F('listed_price')) * 100,
                output_field=FloatField()
            ),
            total_savings=Sum(
                F('listed_price') - F('discounted_price'),
                output_field=FloatField()
            )
        )
        
        # Flash sales ending soon (within 24 hours)
        tomorrow = now + timedelta(days=1)
        flash_sales_count = queryset.filter(
            offer_start__isnull=False,
            offer_end__isnull=False,
            offer_start__lte=now,
            offer_end__gte=now,
            offer_end__lte=tomorrow
        ).count()
        
        stats_data = {
            'total_deals': total_deals,
            'discount_deals': discount_deals,
            'active_offers': active_offers,
            'flash_sales_ending_soon': flash_sales_count,
            'average_discount_percentage': round(avg_discount_info['avg_discount'] or 0, 2),
            'maximum_discount_percentage': round(avg_discount_info['max_discount'] or 0, 2),
            'total_savings_amount': round(avg_discount_info['total_savings'] or 0, 2),
            'deals_percentage': round((total_deals / queryset.count() * 100) if queryset.count() > 0 else 0, 2)
        }
        
        return Response({
            'stats': stats_data,
            'timestamp': timezone.now().isoformat(),
            'type': 'deal_statistics'
        })