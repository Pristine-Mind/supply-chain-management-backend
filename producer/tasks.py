import math
from datetime import timedelta
import statistics
from collections import defaultdict

from celery import shared_task
from django.utils import timezone
from django.db.models import Sum, functions


from .models import Product, StockList, Sale


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


SERVICE_LEVEL_Z = 1.65  # ~95% service level


# @shared_task
def recalc_inventory_parameters():
    today = timezone.localdate()
    cutoff_90 = today - timedelta(days=90)
    cutoff_14 = today - timedelta(days=14)

    # Bulk 90-day sales aggregated by product & day
    sales_90 = (
        Sale.objects.filter(sale_date__date__gte=cutoff_90)
        .annotate(day=functions.TruncDate("sale_date"))
        .values("order__product_id", "day")
        .annotate(units_sold=Sum("quantity"))
    )
    print(sales_90)
    sales_map = defaultdict(list)
    for row in sales_90:
        sales_map[row["order__product_id"]].append(row["units_sold"])

    # Bulk 14-day burn aggregated by product
    burn_14 = (
        Sale.objects.filter(sale_date__date__gte=cutoff_14).values("order__product_id").annotate(total_sold=Sum("quantity"))
    )
    burn_map = {row["order__product_id"]: row["total_sold"] for row in burn_14}

    for p in Product.objects.all():
        vals90 = sales_map.get(p.id, [])
        p.avg_daily_demand = statistics.mean(vals90) if vals90 else 0
        p.stddev_daily_demand = statistics.pstdev(vals90) if len(vals90) > 1 else 0

        # Safety stock & reorder point
        sigma_lt = math.sqrt(p.lead_time_days * p.stddev_daily_demand**2)
        p.safety_stock = math.ceil(SERVICE_LEVEL_Z * sigma_lt)
        p.reorder_point = math.ceil(p.avg_daily_demand * p.lead_time_days + p.safety_stock)

        # EOQ
        annual = p.avg_daily_demand * 365
        p.reorder_quantity = math.ceil(math.sqrt((2 * annual * 50) / 2))

        # Projected stock-out (persist to a DateField if you add one)
        burn = (burn_map.get(p.id, 0) or 0) / 14
        if burn > 0:
            p.projected_stockout_date_field = today + timedelta(days=p.stock / burn)
        else:
            p.projected_stockout_date_field = None

        p.save(
            update_fields=[
                "avg_daily_demand",
                "stddev_daily_demand",
                "safety_stock",
                "reorder_point",
                "reorder_quantity",
                "projected_stockout_date_field",
            ]
        )
