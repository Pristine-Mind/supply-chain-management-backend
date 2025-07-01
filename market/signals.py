from django.db.models.signals import post_save
from django.dispatch import receiver

from producer.models import MarketplaceProduct, Product, ProductImage

from .models import MarketplaceUserProduct


@receiver(post_save, sender=MarketplaceUserProduct)
def create_marketplace_product(sender, instance, created, **kwargs):
    if created:
        product = Product.objects.create(
            producer=None,
            name=instance.name,
            description=instance.description,
            sku=f"MP-{instance.pk}",
            price=instance.price,
            cost_price=instance.price,
            stock=instance.stock,
            reorder_level=5,
            is_active=True,
            category=instance.category,
            is_marketplace_created=True,
            user=instance.user,
            location=instance.location,
            # unit=instance.unit
        )

        MarketplaceProduct.objects.create(
            product=product,
            listed_price=instance.price,
            is_available=not instance.is_sold,
            bid_end_date=instance.bid_end_date,
        )
        # If the MarketplaceUserProduct has an image, create a ProductImage
        if instance.image:
            ProductImage.objects.create(
                product=product,
                image=instance.image,
                alt_text=f"Image for {instance.name}",
            )
