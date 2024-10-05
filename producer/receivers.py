from datetime import timedelta

from django.dispatch import receiver
from django.db.models.signals import post_save
from django.utils import timezone

from .models import MarketplaceProduct, StockList


@receiver(post_save, sender=StockList)
def push_to_marketplace(sender, instance, **kwargs):
    """
    Automatically list product in marketplace when added to stocklist.
    """
    MarketplaceProduct.objects.create(
        product=instance.product,
        listed_price=instance.product.price,
        is_available=True,
        bid_end_date=timezone.now() + timedelta(days=30),
    )
