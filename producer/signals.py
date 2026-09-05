from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import MarketplaceProduct
from .tasks import generate_and_save_product_tags

User = apps.get_model(settings.AUTH_USER_MODEL)
CreatorProfile = apps.get_model("producer", "CreatorProfile")
ShoppableVideo = apps.get_model("market", "ShoppableVideo")


@receiver(post_save, sender=MarketplaceProduct)
def handle_marketplace_product_save(sender, instance, created, **kwargs):
    update_fields = kwargs.get("update_fields")
    if update_fields and "search_tags" in update_fields:
        return
    if created or not instance.search_tags:
        generate_and_save_product_tags.delay(instance.pk)

    if not created:
        return

    try:
        cp = instance.uploader.creator_profile
        cp.posts_count = apps.get_model("producer", "CreatorProfile").objects.filter(user=instance.uploader).count()
        cp.save()
    except Exception:
        pass


@receiver(post_delete, sender=ShoppableVideo)
def decrement_creator_posts(sender, instance, **kwargs):
    try:
        cp = instance.uploader.creator_profile
        cp.posts_count = ShoppableVideo.objects.filter(uploader=instance.uploader).count()
        cp.save()
    except Exception:
        pass


@receiver(post_save, sender=CreatorProfile)
def backfill_shoppable_videos_creator_profile(sender, instance, created, **kwargs):
    try:
        if created:
            ShoppableVideo.objects.filter(uploader=instance.user, creator_profile__isnull=True).update(
                creator_profile=instance
            )
    except Exception:
        pass
