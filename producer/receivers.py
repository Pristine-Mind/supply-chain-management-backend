from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import MarketplaceProduct, Product, PurchaseOrder, StockList

# @receiver(post_save, sender=StockList)
# def push_to_marketplace(sender, instance, **kwargs):
#     """
#     Automatically list product in marketplace when added to stocklist.
#     """
#     MarketplaceProduct.objects.create(
#         product=instance.product,
#         listed_price=instance.product.price,
#         is_available=True,
#         bid_end_date=timezone.now() + timedelta(days=30),
#     )


@receiver(post_save, sender=Product)
def auto_create_po(sender, instance: Product, **kwargs):
    if instance.stock <= instance.reorder_point:
        if not PurchaseOrder.objects.filter(product=instance, approved=False).exists():
            PurchaseOrder.objects.create(product=instance, quantity=instance.reorder_quantity, user=instance.user)
