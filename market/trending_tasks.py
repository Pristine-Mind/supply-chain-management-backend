from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .trending_utils import TrendingProductUtils


@shared_task
def update_trending_metrics():
    """
    Periodic task to update trending product metrics
    Should be run every hour or as needed
    """
    try:
        TrendingProductUtils.update_recent_purchases_count()
        return "Trending metrics updated successfully"
    except Exception as e:
        return f"Error updating trending metrics: {str(e)}"


@shared_task
def generate_trending_report():
    """
    Generate a summary report of trending products
    """
    try:
        summary = TrendingProductUtils.get_trending_summary()
        # You can send this to admin email, save to database, etc.
        return summary
    except Exception as e:
        return f"Error generating trending report: {str(e)}"
