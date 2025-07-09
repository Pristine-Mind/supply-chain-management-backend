import math
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from market.models import Bid

from .models import MarketplaceProduct, Product, StockList


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


# def get_bids_last_hour(product):
#     one_hour_ago = timezone.now() - timedelta(hours=1)
#     return Bid.objects.filter(product=product, bid_date__gte=one_hour_ago).count()


# def get_bids_last_day(product):
#     one_day_ago = timezone.now() - timedelta(days=1)
#     return Bid.objects.filter(product=product, bid_date__gte=one_day_ago).count()


# @shared_task
# def update_bid_end_dates():
#     products = MarketplaceProduct.objects.filter(is_available=True)

#     for product in products:
#         bids_last_hour = get_bids_last_hour(product)
#         bids_last_day = get_bids_last_day(product)
#         product.update_bid_end_date(bids_last_hour, bids_last_day)


SERVICE_LEVEL_Z = 1.65


@shared_task
def recalc_inventory_parameters():
    """
    Recalculate replenishment parameters for every product:

    - safety_stock: service level factor × stddev of demand during lead time
    - reorder_point: (average daily demand × lead time) + safety_stock
    - reorder_quantity: Economic Order Quantity (EOQ) = √((2 × annual demand × order cost) / holding cost)

    Updates each Product’s safety_stock, reorder_point, and reorder_quantity fields.
    """
    for product in Product.objects.all():
        average_daily_demand = product.avg_daily_demand
        demand_stddev = product.stddev_daily_demand
        lead_time_days = product.lead_time_days

        sigma_demand_lead_time = math.sqrt(lead_time_days * demand_stddev**2)
        safety_stock = math.ceil(SERVICE_LEVEL_Z * sigma_demand_lead_time)

        reorder_point = math.ceil(average_daily_demand * lead_time_days + safety_stock)

        annual_demand = average_daily_demand * 365
        order_cost = 50
        holding_cost = 2
        eoq = math.ceil(math.sqrt((2 * annual_demand * order_cost) / holding_cost))

        product.safety_stock = safety_stock
        product.reorder_point = reorder_point
        product.reorder_quantity = eoq
        product.save()
