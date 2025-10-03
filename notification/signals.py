import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import UserNotificationPreference
from .rules_engine import (
    NotificationRulesEngine,
    trigger_delivery_event,
    trigger_order_event,
    trigger_payment_event,
    trigger_stock_event,
    trigger_user_event,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_notification_preferences(sender, instance, created, **kwargs):
    """Create default notification preferences for new users"""
    if created:
        UserNotificationPreference.objects.get_or_create(user=instance)

        # Trigger user registration event
        try:
            trigger_user_event(instance, "registered")
        except Exception as e:
            logger.error(f"Error triggering user registration event: {e}")


@receiver(user_logged_in)
def user_login_notification(sender, request, user, **kwargs):
    """Trigger notification for user login if needed"""
    try:
        # You can add logic here to trigger login notifications
        # For example, for suspicious login attempts
        pass
    except Exception as e:
        logger.error(f"Error handling user login notification: {e}")


# Order-related signals
try:
    from market.models import Order  # Adjust import based on your order model

    @receiver(post_save, sender=Order)
    def order_status_changed(sender, instance, created, **kwargs):
        """Trigger notifications when order status changes"""
        try:
            if created:
                trigger_order_event(instance, "created")
            else:
                # Check if status changed
                if hasattr(instance, "_state") and instance._state.db:
                    try:
                        old_instance = Order.objects.get(pk=instance.pk)
                        if old_instance.status != instance.status:
                            # Status changed, trigger appropriate event
                            status_map = {
                                "confirmed": "confirmed",
                                "shipped": "shipped",
                                "delivered": "delivered",
                                "cancelled": "cancelled",
                            }

                            event_type = status_map.get(instance.status)
                            if event_type:
                                trigger_order_event(instance, event_type)
                    except Order.DoesNotExist:
                        pass
        except Exception as e:
            logger.error(f"Error triggering order notification: {e}")

except ImportError:
    logger.warning("Order model not found, order notifications disabled")


# Payment-related signals
try:
    from payment.models import Payment  # Adjust import based on your payment model

    @receiver(post_save, sender=Payment)
    def payment_status_changed(sender, instance, created, **kwargs):
        """Trigger notifications when payment status changes"""
        try:
            if created:
                # New payment created
                if instance.status == "completed":
                    trigger_payment_event(instance, "received")
                elif instance.status == "failed":
                    trigger_payment_event(instance, "failed")
            else:
                # Payment status updated
                if hasattr(instance, "_state") and instance._state.db:
                    try:
                        old_instance = Payment.objects.get(pk=instance.pk)
                        if old_instance.status != instance.status:
                            if instance.status == "completed":
                                trigger_payment_event(instance, "received")
                            elif instance.status == "failed":
                                trigger_payment_event(instance, "failed")
                    except Payment.DoesNotExist:
                        pass
        except Exception as e:
            logger.error(f"Error triggering payment notification: {e}")

except ImportError:
    logger.warning("Payment model not found, payment notifications disabled")


# Delivery-related signals
try:
    from transport.models import Delivery  # Adjust import based on your delivery model

    @receiver(post_save, sender=Delivery)
    def delivery_status_changed(sender, instance, created, **kwargs):
        """Trigger notifications when delivery status changes"""
        try:
            if created:
                trigger_delivery_event(instance, "assigned")
            else:
                # Check if status changed
                if hasattr(instance, "_state") and instance._state.db:
                    try:
                        old_instance = Delivery.objects.get(pk=instance.pk)
                        if old_instance.status != instance.status:
                            status_map = {
                                "picked_up": "picked_up",
                                "in_transit": "in_transit",
                                "delivered": "completed",
                                "failed": "failed",
                            }

                            event_type = status_map.get(instance.status)
                            if event_type:
                                trigger_delivery_event(instance, event_type)
                    except Delivery.DoesNotExist:
                        pass
        except Exception as e:
            logger.error(f"Error triggering delivery notification: {e}")

except ImportError:
    logger.warning("Delivery model not found, delivery notifications disabled")


# Stock-related signals
try:
    from producer.models import Product  # Adjust import based on your product model

    @receiver(post_save, sender=Product)
    def product_stock_changed(sender, instance, created, **kwargs):
        """Trigger notifications when product stock changes"""
        try:
            if not created and hasattr(instance, "stock_quantity"):
                # Check if stock is low
                low_threshold = getattr(instance, "low_stock_threshold", 10)

                if instance.stock_quantity <= 0:
                    trigger_stock_event(instance, "out")
                elif instance.stock_quantity <= low_threshold:
                    trigger_stock_event(instance, "low")
        except Exception as e:
            logger.error(f"Error triggering stock notification: {e}")

except ImportError:
    logger.warning("Product model not found, stock notifications disabled")


# Custom signal handlers for specific business logic
def trigger_custom_notification(event_name, event_data, user_id=None):
    """Helper function to trigger custom notifications from anywhere in the app"""
    try:
        engine = NotificationRulesEngine()
        engine.trigger_event(event_name, event_data, user_id)
    except Exception as e:
        logger.error(f"Error triggering custom notification {event_name}: {e}")


# Bid-related signals (if applicable)
try:
    from market.models import Bid  # Adjust import based on your bid model

    @receiver(post_save, sender=Bid)
    def bid_status_changed(sender, instance, created, **kwargs):
        """Trigger notifications when bid status changes"""
        try:
            if created:
                # New bid created
                engine = NotificationRulesEngine()
                event_data = {
                    "event_category": "bid",
                    "event_type": "created",
                    "bid_id": instance.id,
                    "bidder_id": instance.bidder.id if hasattr(instance, "bidder") else None,
                    "product_id": instance.product.id if hasattr(instance, "product") else None,
                    "amount": float(getattr(instance, "amount", 0)),
                    "producer_id": getattr(instance, "producer_id", None),
                }
                engine.trigger_event("bid_created", event_data)
            else:
                # Check if bid was accepted
                if hasattr(instance, "status") and instance.status == "accepted":
                    engine = NotificationRulesEngine()
                    event_data = {
                        "event_category": "bid",
                        "event_type": "accepted",
                        "bid_id": instance.id,
                        "bidder_id": instance.bidder.id if hasattr(instance, "bidder") else None,
                        "product_id": instance.product.id if hasattr(instance, "product") else None,
                        "amount": float(getattr(instance, "amount", 0)),
                        "producer_id": getattr(instance, "producer_id", None),
                    }
                    engine.trigger_event("bid_accepted", event_data)
        except Exception as e:
            logger.error(f"Error triggering bid notification: {e}")

except ImportError:
    logger.warning("Bid model not found, bid notifications disabled")


# Generic signal for any model changes
@receiver(post_save)
def generic_model_change_handler(sender, instance, created, **kwargs):
    """Generic handler for model changes that might need notifications"""
    try:
        # Skip notification models to avoid recursion
        if sender.__name__ in ["Notification", "NotificationEvent", "DeviceToken"]:
            return

        # You can add custom logic here for specific models
        # that don't have dedicated handlers above

        # Example: Handle user profile updates
        if sender.__name__ == "UserProfile" and not created:
            # Trigger profile update notification if needed
            pass

    except Exception as e:
        logger.error(f"Error in generic model change handler: {e}")


# Signal to clean up device tokens when user is deleted
@receiver(post_delete, sender=User)
def cleanup_user_data(sender, instance, **kwargs):
    """Clean up user-related notification data when user is deleted"""
    try:
        # Device tokens are automatically deleted due to foreign key cascade
        # But we can log this event
        logger.info(f"Cleaned up notification data for deleted user {instance.id}")
    except Exception as e:
        logger.error(f"Error cleaning up user notification data: {e}")


# Signal to handle notification template changes
@receiver(post_save, sender="notification.NotificationTemplate")
def notification_template_changed(sender, instance, created, **kwargs):
    """Handle notification template changes"""
    try:
        if created:
            logger.info(f"New notification template created: {instance.name}")
        else:
            logger.info(f"Notification template updated: {instance.name}")
    except Exception as e:
        logger.error(f"Error handling template change: {e}")


# Signal to handle notification rule changes
@receiver(post_save, sender="notification.NotificationRule")
def notification_rule_changed(sender, instance, created, **kwargs):
    """Handle notification rule changes"""
    try:
        if created:
            logger.info(f"New notification rule created: {instance.name}")
        else:
            logger.info(f"Notification rule updated: {instance.name}")
    except Exception as e:
        logger.error(f"Error handling rule change: {e}")
