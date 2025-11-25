from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    ExternalBusiness,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
)
from .tasks import create_transport_delivery, send_delivery_notifications


@receiver(post_save, sender=ExternalDelivery)
def handle_external_delivery_created(sender, instance, created, **kwargs):
    """
    Handle external delivery creation
    """
    if created:
        # Process the delivery asynchronously
        from .tasks import process_external_delivery

        process_external_delivery.delay(instance.id)


@receiver(pre_save, sender=ExternalDelivery)
def handle_external_delivery_status_change(sender, instance, **kwargs):
    """
    Handle external delivery status changes
    """
    if instance.pk:
        try:
            old_instance = ExternalDelivery.objects.get(pk=instance.pk)

            # Check if status changed
            if old_instance.status != instance.status:
                # Send notification for status change
                send_delivery_notifications.delay(instance.id, instance.status)

        except ExternalDelivery.DoesNotExist:
            pass


@receiver(post_save, sender=ExternalBusiness)
def handle_external_business_approved(sender, instance, **kwargs):
    """
    Handle external business approval
    """
    if (
        instance.status == ExternalBusinessStatus.APPROVED
        and instance.approved_at
        and instance.approved_at > timezone.now() - timezone.timedelta(minutes=5)
    ):

        # Send welcome email or notification
        # This can be implemented as needed
        pass


@receiver(post_save, sender=ExternalBusiness)
def generate_api_credentials(sender, instance, created, **kwargs):
    """
    Generate API credentials for new external businesses
    """
    if created and not instance.api_key:
        instance.api_key = instance.generate_api_key()
        instance.webhook_secret = instance.generate_webhook_secret()
        # Use update to avoid recursion
        ExternalBusiness.objects.filter(pk=instance.pk).update(
            api_key=instance.api_key, webhook_secret=instance.webhook_secret
        )
