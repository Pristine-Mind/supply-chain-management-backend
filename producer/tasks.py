from celery import shared_task
from .models import Product, StockList


@shared_task
def move_large_stock_to_stocklist():
    LARGE_STOCK_THRESHOLD = 100

    products = Product.objects.filter(is_active=True)

    for product in products:
        if product.stock > LARGE_STOCK_THRESHOLD:
            if not StockList.objects.filter(product=product).exists():
                StockList.objects.create(product=product)
                product.is_active = False
                product.save()

    return f"{len(products)} products checked."
