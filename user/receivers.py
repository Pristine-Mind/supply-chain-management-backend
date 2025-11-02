import uuid

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Role, UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Get the general_user role
        general_user_role = Role.objects.get(code="general_user")

        # Create UserProfile for all new users with general_user role
        profile_data = {
            "user": instance,
            "role": general_user_role,
        }

        # Add shop_id only for superusers
        if instance.is_superuser:
            profile_data["shop_id"] = str(uuid.uuid4())

        _ = UserProfile.objects.create(**profile_data)


# @receiver(post_save, sender=User)
# def save_user_profile(sender, instance, **kwargs):
#     instance.userprofile.save()
