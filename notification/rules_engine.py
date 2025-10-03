import logging
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import (
    Notification,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .services import NotificationServiceFactory
from .tasks import send_delayed_notification_task, send_notification_task

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationRulesEngine:
    """Engine for processing notification rules and triggering notifications"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def trigger_event(self, event_name: str, event_data: Dict[str, Any], user_id: Optional[int] = None):
        """Trigger notifications based on event"""
        try:
            # Get active rules for this event
            rules = (
                NotificationRule.objects.filter(trigger_event=event_name, is_active=True)
                .select_related("template")
                .order_by("priority")
            )

            self.logger.info(f"Processing {len(rules)} rules for event: {event_name}")

            for rule in rules:
                try:
                    # Evaluate rule conditions
                    if not rule.evaluate_conditions(event_data):
                        self.logger.debug(f"Rule {rule.name} conditions not met")
                        continue

                    # Get target users
                    target_users = self._get_target_users(rule, event_data, user_id)

                    if not target_users:
                        self.logger.debug(f"No target users found for rule {rule.name}")
                        continue

                    # Create notifications for each target user
                    for user in target_users:
                        self._create_notification_for_user(rule, user, event_data)

                except Exception as e:
                    self.logger.error(f"Error processing rule {rule.name}: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Error triggering event {event_name}: {e}")

    def _get_target_users(
        self, rule: NotificationRule, event_data: Dict[str, Any], user_id: Optional[int] = None
    ) -> List[User]:
        """Get target users based on rule configuration"""
        target_users = []
        target_config = rule.target_users

        try:
            # If specific user is provided, use that
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if self._user_matches_criteria(user, target_config, event_data):
                        target_users.append(user)
                except User.DoesNotExist:
                    pass
                return target_users

            # Build query based on target configuration
            query = Q()

            # User groups/roles
            if "user_types" in target_config:
                user_types = target_config["user_types"]
                if isinstance(user_types, list):
                    query |= Q(user_type__in=user_types)

            # Specific user IDs
            if "user_ids" in target_config:
                user_ids = target_config["user_ids"]
                if isinstance(user_ids, list):
                    query |= Q(id__in=user_ids)

            # All users (be careful with this)
            if target_config.get("all_users", False):
                query = Q()

            # Event-specific targeting
            if "event_based" in target_config:
                event_based = target_config["event_based"]

                # Target user from event data
                if event_based.get("use_event_user", False):
                    event_user_id = event_data.get("user_id")
                    if event_user_id:
                        query |= Q(id=event_user_id)

                # Target related users (e.g., order owner, producer, etc.)
                if "related_users" in event_based:
                    related_field = event_based["related_users"]
                    related_user_ids = event_data.get(related_field, [])
                    if isinstance(related_user_ids, (list, tuple)):
                        query |= Q(id__in=related_user_ids)
                    elif related_user_ids:
                        query |= Q(id=related_user_ids)

            # Get users matching the query
            users = User.objects.filter(query).distinct()

            # Apply additional filters
            for user in users:
                if self._user_matches_criteria(user, target_config, event_data):
                    target_users.append(user)

        except Exception as e:
            self.logger.error(f"Error getting target users: {e}")

        return target_users

    def _user_matches_criteria(self, user: User, target_config: Dict[str, Any], event_data: Dict[str, Any]) -> bool:
        """Check if user matches additional criteria"""
        try:
            # Check user preferences
            try:
                preferences = user.notification_preferences

                # Check if notifications are enabled for this user
                if not preferences.push_enabled and not preferences.email_enabled and not preferences.sms_enabled:
                    return False

                # Check event-specific preferences
                event_type = event_data.get("event_category", "general")
                if event_type == "order" and not preferences.order_notifications:
                    return False
                elif event_type == "payment" and not preferences.payment_notifications:
                    return False
                elif event_type == "delivery" and not preferences.delivery_notifications:
                    return False
                elif event_type == "marketing" and not preferences.marketing_notifications:
                    return False

                # Check quiet hours
                if preferences.is_quiet_time():
                    return False

            except UserNotificationPreference.DoesNotExist:
                # Create default preferences if they don't exist
                UserNotificationPreference.objects.create(user=user)

            # Additional custom criteria can be added here
            custom_criteria = target_config.get("custom_criteria", {})
            for field, value in custom_criteria.items():
                if hasattr(user, field):
                    user_value = getattr(user, field)
                    if user_value != value:
                        return False

            return True

        except Exception as e:
            self.logger.error(f"Error checking user criteria: {e}")
            return False

    def _create_notification_for_user(self, rule: NotificationRule, user: User, event_data: Dict[str, Any]):
        """Create notification for a specific user"""
        try:
            # Get user preferences to determine notification types
            try:
                preferences = user.notification_preferences
            except UserNotificationPreference.DoesNotExist:
                preferences = UserNotificationPreference.objects.create(user=user)

            # Determine which notification types to send
            notification_types = []
            if preferences.push_enabled and rule.template.template_type == "push":
                notification_types.append("push")
            if preferences.email_enabled and rule.template.template_type == "email":
                notification_types.append("email")
            if preferences.sms_enabled and rule.template.template_type == "sms":
                notification_types.append("sms")
            if preferences.in_app_enabled and rule.template.template_type == "in_app":
                notification_types.append("in_app")

            # If template type doesn't match preferences, use in_app as fallback
            if not notification_types:
                notification_types = ["in_app"]

            # Render template with event data
            try:
                rendered_content = rule.template.render(event_data)
            except ValueError as e:
                self.logger.error(f"Template rendering error for rule {rule.name}: {e}")
                return

            # Create notifications for each type
            for notification_type in notification_types:
                notification = Notification.objects.create(
                    user=user,
                    notification_type=notification_type,
                    title=rendered_content["title"],
                    body=rendered_content["body"],
                    action_url=rendered_content.get("action_url"),
                    icon_url=rendered_content.get("icon_url"),
                    template=rule.template,
                    rule=rule,
                    event_data=event_data,
                    priority=rule.priority,
                    scheduled_at=timezone.now() + timezone.timedelta(minutes=rule.delay_minutes),
                )

                # Schedule notification sending
                if rule.delay_minutes > 0:
                    # Send delayed notification
                    send_delayed_notification_task.apply_async(args=[str(notification.id)], eta=notification.scheduled_at)
                else:
                    # Send immediately
                    send_notification_task.delay(str(notification.id))

                self.logger.info(f"Created {notification_type} notification for user {user.id} from rule {rule.name}")

        except Exception as e:
            self.logger.error(f"Error creating notification for user {user.id}: {e}")


class EventDataBuilder:
    """Helper class to build event data for common scenarios"""

    @staticmethod
    def order_event(order, event_type: str) -> Dict[str, Any]:
        """Build event data for order-related events"""
        return {
            "event_category": "order",
            "event_type": event_type,
            "order_id": order.id,
            "order_number": getattr(order, "order_number", str(order.id)),
            "user_id": order.user.id if hasattr(order, "user") else None,
            "producer_id": getattr(order, "producer_id", None),
            "total_amount": float(getattr(order, "total_amount", 0)),
            "status": getattr(order, "status", ""),
            "created_at": order.created_at.isoformat() if hasattr(order, "created_at") else "",
            "customer_name": order.user.get_full_name() if hasattr(order, "user") else "",
        }

    @staticmethod
    def payment_event(payment, event_type: str) -> Dict[str, Any]:
        """Build event data for payment-related events"""
        return {
            "event_category": "payment",
            "event_type": event_type,
            "payment_id": payment.id,
            "user_id": payment.user.id if hasattr(payment, "user") else None,
            "amount": float(getattr(payment, "amount", 0)),
            "status": getattr(payment, "status", ""),
            "payment_method": getattr(payment, "payment_method", ""),
            "transaction_id": getattr(payment, "transaction_id", ""),
            "created_at": payment.created_at.isoformat() if hasattr(payment, "created_at") else "",
        }

    @staticmethod
    def delivery_event(delivery, event_type: str) -> Dict[str, Any]:
        """Build event data for delivery-related events"""
        return {
            "event_category": "delivery",
            "event_type": event_type,
            "delivery_id": delivery.id,
            "user_id": getattr(delivery, "customer_id", None),
            "transporter_id": getattr(delivery, "transporter_id", None),
            "status": getattr(delivery, "status", ""),
            "pickup_location": getattr(delivery, "pickup_location", ""),
            "delivery_location": getattr(delivery, "delivery_location", ""),
            "estimated_delivery": getattr(delivery, "estimated_delivery_time", ""),
            "tracking_number": getattr(delivery, "tracking_number", ""),
        }

    @staticmethod
    def stock_event(product, event_type: str) -> Dict[str, Any]:
        """Build event data for stock-related events"""
        return {
            "event_category": "inventory",
            "event_type": event_type,
            "product_id": product.id,
            "product_name": getattr(product, "name", ""),
            "current_stock": getattr(product, "stock_quantity", 0),
            "threshold": getattr(product, "low_stock_threshold", 0),
            "producer_id": getattr(product, "producer_id", None),
            "category": getattr(product, "category", ""),
        }

    @staticmethod
    def user_event(user, event_type: str) -> Dict[str, Any]:
        """Build event data for user-related events"""
        return {
            "event_category": "user",
            "event_type": event_type,
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.get_full_name(),
            "user_type": getattr(user, "user_type", ""),
            "created_at": user.date_joined.isoformat() if hasattr(user, "date_joined") else "",
        }


# Convenience functions for common events
def trigger_order_event(order, event_type: str):
    """Trigger order-related notification event"""
    engine = NotificationRulesEngine()
    event_data = EventDataBuilder.order_event(order, event_type)
    engine.trigger_event(f"order_{event_type}", event_data)


def trigger_payment_event(payment, event_type: str):
    """Trigger payment-related notification event"""
    engine = NotificationRulesEngine()
    event_data = EventDataBuilder.payment_event(payment, event_type)
    engine.trigger_event(f"payment_{event_type}", event_data)


def trigger_delivery_event(delivery, event_type: str):
    """Trigger delivery-related notification event"""
    engine = NotificationRulesEngine()
    event_data = EventDataBuilder.delivery_event(delivery, event_type)
    engine.trigger_event(f"delivery_{event_type}", event_data)


def trigger_stock_event(product, event_type: str):
    """Trigger stock-related notification event"""
    engine = NotificationRulesEngine()
    event_data = EventDataBuilder.stock_event(product, event_type)
    engine.trigger_event(f"stock_{event_type}", event_data)


def trigger_user_event(user, event_type: str):
    """Trigger user-related notification event"""
    engine = NotificationRulesEngine()
    event_data = EventDataBuilder.user_event(user, event_type)
    engine.trigger_event(f"user_{event_type}", event_data)
