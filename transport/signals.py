from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Delivery,
    DeliveryRating,
    DeliveryRoute,
    DeliveryTracking,
    Transporter,
    TransportStatus,
)


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
            delivery_tracking_ct = ContentType.objects.get_for_model(DeliveryTracking)
            delivery_route_ct = ContentType.objects.get_for_model(DeliveryRoute)

            # Define permissions
            permissions = [
                # Delivery permissions
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
                    codename="can_mark_pickup", name="Can mark delivery as picked up", content_type=delivery_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_mark_delivered", name="Can mark delivery as delivered", content_type=delivery_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_cancel_delivery", name="Can cancel delivery", content_type=delivery_ct
                )[0],
                # Transporter permissions
                Permission.objects.get_or_create(
                    codename="can_update_location", name="Can update location", content_type=transporter_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_update_availability", name="Can update availability status", content_type=transporter_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_view_earnings", name="Can view earnings", content_type=transporter_ct
                )[0],
                # Tracking permissions
                Permission.objects.get_or_create(
                    codename="can_create_tracking", name="Can create delivery tracking", content_type=delivery_tracking_ct
                )[0],
                # Route permissions
                Permission.objects.get_or_create(
                    codename="can_create_routes", name="Can create delivery routes", content_type=delivery_route_ct
                )[0],
                Permission.objects.get_or_create(
                    codename="can_manage_own_routes", name="Can manage own delivery routes", content_type=delivery_route_ct
                )[0],
            ]

            transporter_group.permissions.set(permissions)


@receiver(post_save, sender=DeliveryRating)
def update_transporter_rating(sender, instance, created, **kwargs):
    """Update transporter's average rating when a new rating is added."""
    if created:
        instance.transporter.update_rating()


@receiver(post_delete, sender=DeliveryRating)
def recalculate_rating_on_delete(sender, instance, **kwargs):
    """Recalculate transporter rating when a rating is deleted."""
    instance.transporter.update_rating()


@receiver(pre_save, sender=Delivery)
def validate_delivery_status_change(sender, instance, **kwargs):
    """Validate delivery status changes and update timestamps."""
    if instance.pk:  # Only for updates, not new creations
        try:
            old_instance = Delivery.objects.get(pk=instance.pk)

            # Define valid status transitions
            valid_transitions = {
                TransportStatus.AVAILABLE: [TransportStatus.ASSIGNED, TransportStatus.CANCELLED],
                TransportStatus.ASSIGNED: [TransportStatus.PICKED_UP, TransportStatus.CANCELLED],
                TransportStatus.PICKED_UP: [TransportStatus.IN_TRANSIT, TransportStatus.RETURNED, TransportStatus.CANCELLED],
                TransportStatus.IN_TRANSIT: [TransportStatus.DELIVERED, TransportStatus.RETURNED, TransportStatus.FAILED],
                TransportStatus.DELIVERED: [],  # Final state
                TransportStatus.CANCELLED: [],  # Final state
                TransportStatus.RETURNED: [TransportStatus.AVAILABLE, TransportStatus.ASSIGNED],
                TransportStatus.FAILED: [TransportStatus.AVAILABLE],  # Allow retry
            }

            # Check if status change is valid
            old_status = old_instance.status
            new_status = instance.status

            if old_status != new_status:
                allowed_statuses = valid_transitions.get(old_status, [])
                if new_status not in allowed_statuses:
                    raise ValidationError(
                        f"Invalid status transition from {old_status} to {new_status}. "
                        f"Allowed transitions: {allowed_statuses}"
                    )

                # Update timestamps based on status change
                now = timezone.now()
                if new_status == TransportStatus.ASSIGNED and not instance.assigned_at:
                    instance.assigned_at = now
                elif new_status == TransportStatus.PICKED_UP and not instance.picked_up_at:
                    instance.picked_up_at = now
                    instance.actual_pickup_time = now
                elif new_status == TransportStatus.DELIVERED and not instance.delivered_at:
                    instance.delivered_at = now
                elif new_status == TransportStatus.CANCELLED and not instance.cancelled_at:
                    instance.cancelled_at = now

        except Delivery.DoesNotExist:
            pass  # New instance, no validation needed


@receiver(post_save, sender=Delivery)
def update_transporter_stats_and_tracking(sender, instance, created, **kwargs):
    """Update transporter statistics and create tracking entries on delivery status changes."""
    if not created and instance.transporter:
        # Get the previous instance to compare status
        try:
            old_instance = Delivery.objects.get(pk=instance.pk)
            if hasattr(old_instance, "_state") and old_instance._state.db:
                # Refresh to get the old values
                old_instance.refresh_from_db()
        except Delivery.DoesNotExist:
            old_instance = None

        # Update transporter statistics based on status changes
        if instance.status == TransportStatus.DELIVERED:
            # Check if this is a new delivery completion
            if not old_instance or old_instance.status != TransportStatus.DELIVERED:
                transporter = instance.transporter
                transporter.total_deliveries += 1
                transporter.successful_deliveries += 1

                # Calculate earnings (delivery fee minus commission)
                commission_amount = instance.delivery_fee * (transporter.commission_rate / 100)
                earnings = instance.delivery_fee - commission_amount
                transporter.earnings_total += earnings

                transporter.save(update_fields=["total_deliveries", "successful_deliveries", "earnings_total"])

        elif instance.status == TransportStatus.CANCELLED:
            # Check if this is a new cancellation
            if not old_instance or old_instance.status != TransportStatus.CANCELLED:
                transporter = instance.transporter
                transporter.cancelled_deliveries += 1
                transporter.save(update_fields=["cancelled_deliveries"])


@receiver(pre_save, sender=Transporter)
def validate_transporter_documents(sender, instance, **kwargs):
    """Validate transporter documents and license expiry."""
    if instance.pk:
        # Check if critical documents are expired
        if instance.is_documents_expired() and instance.is_available:
            # Automatically set as unavailable if documents are expired
            instance.is_available = False
            instance.status = "inactive"


@receiver(post_save, sender=Transporter)
def update_transporter_location_timestamp(sender, instance, created, **kwargs):
    """Update location timestamp when transporter location is updated."""
    if not created:
        # Check if location fields were updated
        old_instance = None
        if instance.pk:
            try:
                old_instance = Transporter.objects.get(pk=instance.pk)
            except Transporter.DoesNotExist:
                pass

        if old_instance:
            location_changed = (
                old_instance.current_latitude != instance.current_latitude
                or old_instance.current_longitude != instance.current_longitude
            )

            if location_changed and not instance.last_location_update:
                instance.last_location_update = timezone.now()
                # Use update to avoid triggering this signal again
                Transporter.objects.filter(pk=instance.pk).update(last_location_update=instance.last_location_update)
