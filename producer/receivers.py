from datetime import timedelta

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

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


# TODO: Uncomment this later
# @receiver(post_save, sender=Product)
# def sync_product_to_marketplace(sender, instance: Product, created, **kwargs):
#     """
#     Synchronize product changes to marketplace products.
#     Updates size, color, and additional_information in all related marketplace products.
#     """
#     if not created:  # Only sync on updates, not creation
#         marketplace_products = MarketplaceProduct.objects.filter(product=instance)
#         for mp in marketplace_products:
#             # Only update if the marketplace product doesn't have custom values
#             update_fields = []

#             # Sync size if marketplace product doesn't have a custom size
#             if not mp.size or mp.size == getattr(instance, '_old_size', None):
#                 mp.size = instance.size
#                 update_fields.append('size')

#             # Sync color if marketplace product doesn't have a custom color
#             if not mp.color or mp.color == getattr(instance, '_old_color', None):
#                 mp.color = instance.color
#                 update_fields.append('color')

#             # Always sync additional_information
#             mp.additional_information = instance.additional_information
#             update_fields.append('additional_information')

#             if update_fields:
#                 mp.save(update_fields=update_fields)


# @receiver(pre_save, sender=Product)
# def track_product_changes(sender, instance: Product, **kwargs):
#     """
#     Track changes to product fields before saving.
#     """
#     if instance.pk:
#         try:
#             old_instance = Product.objects.get(pk=instance.pk)
#             instance._old_size = old_instance.size
#             instance._old_color = old_instance.color
#         except Product.DoesNotExist:
#             pass


# @receiver(post_save, sender=MarketplaceProduct)
# def validate_marketplace_product_attributes(sender, instance: MarketplaceProduct, created, **kwargs):
#     """
#     Validate that marketplace product attributes are consistent with product choices.
#     """
#     if created or instance.size or instance.color:
#         # Ensure size and color choices are valid
#         if instance.size and instance.size not in [choice[0] for choice in MarketplaceProduct.SizeChoices.choices]:
#             # If invalid, fall back to product's size or None
#             instance.size = instance.product.size if instance.product.size else None
#             instance.save(update_fields=['size'])

#         if instance.color and instance.color not in [choice[0] for choice in MarketplaceProduct.ColorChoices.choices]:
#             # If invalid, fall back to product's color or None
#             instance.color = instance.product.color if instance.product.color else None
#             instance.save(update_fields=['color'])
