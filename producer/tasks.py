from django.utils import timezone
from datetime import timedelta

from celery import shared_task
from .models import Product, StockList, MarketplaceProduct
from market.models import Bid


@shared_task
def move_large_stock_to_stocklist():
    LARGE_STOCK_THRESHOLD = 25

    products = Product.objects.filter(is_active=True)

    for product in products:
        if product.stock > LARGE_STOCK_THRESHOLD:
            if not StockList.objects.filter(product=product).exists():
                StockList.objects.create(product=product, user=product.user)
                product.is_active = False
                product.save()

    return f"{len(products)} products checked."


def get_bids_last_hour(product):
    one_hour_ago = timezone.now() - timedelta(hours=1)
    return Bid.objects.filter(product=product, bid_date__gte=one_hour_ago).count()


def get_bids_last_day(product):
    one_day_ago = timezone.now() - timedelta(days=1)
    return Bid.objects.filter(product=product, bid_date__gte=one_day_ago).count()


@shared_task
def update_bid_end_dates():
    products = MarketplaceProduct.objects.filter(is_available=True)

    for product in products:
        bids_last_hour = get_bids_last_hour(product)
        bids_last_day = get_bids_last_day(product)
        product.update_bid_end_date(bids_last_hour, bids_last_day)
