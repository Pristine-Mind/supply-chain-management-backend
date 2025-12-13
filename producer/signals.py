from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

User = apps.get_model(settings.AUTH_USER_MODEL)
CreatorProfile = apps.get_model("producer", "CreatorProfile")
ShoppableVideo = apps.get_model("market", "ShoppableVideo")


@receiver(post_save, sender=ShoppableVideo)
def increment_creator_posts(sender, instance, created, **kwargs):
    """Increment posts_count on creator profile when a ShoppableVideo is created."""
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
    """Recompute posts_count when a ShoppableVideo is deleted."""
    try:
        cp = instance.uploader.creator_profile
        cp.posts_count = ShoppableVideo.objects.filter(uploader=instance.uploader).count()
        cp.save()
    except Exception:
        pass


@receiver(post_save, sender=CreatorProfile)
def backfill_shoppable_videos_creator_profile(sender, instance, created, **kwargs):
    """When a CreatorProfile is created, backfill existing videos uploaded by the user.

    This keeps `ShoppableVideo.creator_profile` in sync for past videos.
    """
    try:
        if created:
            # Update videos where creator_profile is null
            ShoppableVideo.objects.filter(uploader=instance.user, creator_profile__isnull=True).update(
                creator_profile=instance
            )
    except Exception:
        pass
