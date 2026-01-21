from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserLocationSnapshot


@receiver(post_save, sender=UserLocationSnapshot)
def on_location_snapshot_created(sender, instance, created, **kwargs):
    if created:
        # Store latest location in cache for quick access
        from django.core.cache import cache

        cache_key = f"user_location_{instance.user.id}"
        cache.set(
            cache_key,
            {
                "latitude": instance.latitude,
                "longitude": instance.longitude,
                "zone": instance.zone.name if instance.zone else None,
                "timestamp": instance.created_at.isoformat(),
            },
            timeout=3600,  # 1 hour
        )
