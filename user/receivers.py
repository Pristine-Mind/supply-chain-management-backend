import uuid

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Role, UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Get the general_user role
        general_user_role = Role.objects.get(code="general_user")

        # Create UserProfile for all new users with general_user role.
        # Use get_or_create to avoid duplicate creation when an admin inline
        # or another piece of code created the profile earlier in the request.
        profile_data = {
            "role": general_user_role,
        }

        # Add shop_id only for superusers
        if instance.is_superuser:
            profile_data["shop_id"] = str(uuid.uuid4())

        def _create_profile():
            try:
                UserProfile.objects.get_or_create(user=instance, defaults=profile_data)
            except IntegrityError:
                # If a concurrent create slipped through, ignore it.
                pass

        # Delay creation until after the surrounding transaction commits.
        # This prevents a race where the admin inline creates the profile
        # in the same transaction and would otherwise cause a unique
        # constraint violation when both try to insert.
        transaction.on_commit(_create_profile)


# @receiver(post_save, sender=User)
# def save_user_profile(sender, instance, **kwargs):
#     instance.userprofile.save()
