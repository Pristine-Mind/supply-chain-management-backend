from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Delivery, DeliveryRating, Transporter, TransportStatus


@receiver(post_save, sender=Transporter)
def create_transporter_permissions(sender, instance, created, **kwargs):
    """Create transporter group and assign permissions when a transporter is created."""
    if created:
        # Get or create transporter group
        transporter_group, _ = Group.objects.get_or_create(name="Transporters")

        # Add user to transporter group
        instance.user.groups.add(transporter_group)

        # Add specific permissions to the group if not already added
        if not transporter_group.permissions.exists():
            # Get content types
            delivery_ct = ContentType.objects.get_for_model(Delivery)
            transporter_ct = ContentType.objects.get_for_model(Transporter)

            # Define permissions
            permissions = [
                Permission.objects.get_or_create(
                    codename="can_accept_delivery", name="Can accept delivery", content_type=delivery_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_update_delivery_status", name="Can update delivery status", content_type=delivery_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_view_available_deliveries", name="Can view available deliveries", content_type=delivery_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_update_location", name="Can update location", content_type=transporter_ct
                )[0],
            ]

            transporter_group.permissions.set(permissions)


@receiver(post_save, sender=DeliveryRating)
def update_transporter_rating(sender, instance, created, **kwargs):
    """Update transporter's average rating when a new rating is added."""
    if created:
        instance.transporter.update_rating()


@receiver(pre_save, sender=Delivery)
def validate_delivery_status_change(sender, instance, **kwargs):
    """Validate delivery status changes."""
    if instance.pk:  # Only for updates, not new creations
        try:
            old_instance = Delivery.objects.get(pk=instance.pk)

            # Define valid status transitions
            valid_transitions = {
                TransportStatus.AVAILABLE: [TransportStatus.ASSIGNED, TransportStatus.CANCELLED],
                TransportStatus.ASSIGNED: [TransportStatus.PICKED_UP, TransportStatus.CANCELLED],
                TransportStatus.PICKED_UP: [TransportStatus.IN_TRANSIT, TransportStatus.RETURNED],
                TransportStatus.IN_TRANSIT: [TransportStatus.DELIVERED, TransportStatus.RETURNED],
                TransportStatus.DELIVERED: [],  # Final state
                TransportStatus.CANCELLED: [],  # Final state
                TransportStatus.RETURNED: [TransportStatus.AVAILABLE],
            }

            # Check if status change is valid
            old_status = old_instance.status
            new_status = instance.status

            if old_status != new_status:
                allowed_statuses = valid_transitions.get(old_status, [])
                if new_status not in allowed_statuses:
                    raise ValueError(f"Invalid status transition from {old_status} to {new_status}")
        except Delivery.DoesNotExist:
            pass  # New instance, no validation needed
