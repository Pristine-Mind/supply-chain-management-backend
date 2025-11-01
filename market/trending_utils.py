from django.utils import timezone
from django.db.models import F, Count
from datetime import timedelta
from producer.models import MarketplaceProduct


class TrendingProductUtils:
    """
    Utility functions for managing trending products and their metrics
    """
    
    @staticmethod
    def update_product_view_count(product_id, user_id=None):
        """
        Update view count for a marketplace product
        """
        try:
            product = MarketplaceProduct.objects.get(id=product_id)
            product.view_count = F('view_count') + 1
            product.save(update_fields=['view_count'])
            return True
        except MarketplaceProduct.DoesNotExist:
            return False
    
    @staticmethod
    def update_recent_purchases_count():
        """
        Update recent purchases count for all marketplace products
        This should be run periodically (e.g., every hour via Celery)
        """
        now = timezone.now()
        day_ago = now - timedelta(days=1)
        
        # Reset all counts first
        _ = MarketplaceProduct.objects.all().update(recent_purchases_count=0)
        
        # Update with current counts
        from market.models import Purchase
        recent_purchases = Purchase.objects.filter(
            purchase_date__gte=day_ago
        ).values('product_id').annotate(
            count=Count('id')
        )
        
        for purchase_data in recent_purchases:
            _ = MarketplaceProduct.objects.filter(
                id=purchase_data['product_id']
            ).update(
                recent_purchases_count=purchase_data['count']
            )
    
    @staticmethod
    def get_trending_summary():
        """
        Get a summary of trending products statistics
        """
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        
        total_products = MarketplaceProduct.objects.filter(is_available=True).count()
        trending_products = MarketplaceProduct.objects.filter(
            is_available=True,
            view_count__gt=0
        ).count()
        
        weekly_sales = 0
        try:
            from market.models import Purchase
            weekly_sales = Purchase.objects.filter(
                purchase_date__gte=week_ago
            ).count()
        except ImportError:
            weekly_sales = 0
        
        return {
            'total_products': total_products,
            'trending_products': trending_products,
            'weekly_sales': weekly_sales,
            'trending_percentage': round((trending_products / total_products * 100), 2) if total_products > 0 else 0
        }
    
    @staticmethod
    def boost_product_ranking(product_id, boost_factor=1.1):
        """
        Boost a product's ranking score (for featured/promoted products)
        """
        try:
            product = MarketplaceProduct.objects.get(id=product_id)
            product.rank_score = F('rank_score') * boost_factor
            product.save(update_fields=['rank_score'])
            return True
        except MarketplaceProduct.DoesNotExist:
            return False