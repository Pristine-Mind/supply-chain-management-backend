import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    DeviceToken,
    Notification,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .rules_engine import NotificationRulesEngine

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationHelper:
    """Helper class for common notification operations"""

    @staticmethod
    def create_quick_notification(
        user: User,
        title: str,
        body: str,
        notification_type: str = "push",
        action_url: Optional[str] = None,
        icon_url: Optional[str] = None,
        priority: int = 5,
        send_immediately: bool = True,
    ) -> Notification:
        """
        Create and optionally send a quick notification without templates

        Args:
            user: Target user
            title: Notification title
            body: Notification body
            notification_type: Type of notification (push, email, sms, in_app)
            action_url: Optional action URL
            icon_url: Optional icon URL
            priority: Priority level (1-10)
            send_immediately: Whether to send immediately

        Returns:
            Created notification instance
        """
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            body=body,
            action_url=action_url,
            icon_url=icon_url,
            priority=priority,
            scheduled_at=timezone.now(),
        )

        if send_immediately:
            from .tasks import send_notification_task

            send_notification_task.delay(str(notification.id))

        return notification

    @staticmethod
    def send_notification_to_users(
        user_ids: List[int],
        title: str,
        body: str,
        notification_type: str = "push",
        context_data: Optional[Dict] = None,
        priority: int = 5,
    ) -> List[str]:
        """
        Send notifications to multiple users

        Args:
            user_ids: List of user IDs
            title: Notification title
            body: Notification body
            notification_type: Type of notification
            context_data: Additional context data
            priority: Priority level

        Returns:
            List of created notification IDs
        """
        from .tasks import send_notification_task

        users = User.objects.filter(id__in=user_ids)
        notification_ids = []

        for user in users:
            notification = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                body=body,
                event_data=context_data or {},
                priority=priority,
                scheduled_at=timezone.now(),
            )

            notification_ids.append(str(notification.id))
            send_notification_task.delay(str(notification.id))

        return notification_ids

    @staticmethod
    def get_user_notification_summary(user: User, days: int = 7) -> Dict[str, Any]:
        """
        Get notification summary for a user

        Args:
            user: User instance
            days: Number of days to look back

        Returns:
            Dictionary with notification summary
        """
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        notifications = Notification.objects.filter(user=user, created_at__gte=start_date, created_at__lt=end_date)

        total = notifications.count()
        unread = notifications.filter(read_at__isnull=True).count()
        by_type = {}

        for notification in notifications:
            notification_type = notification.notification_type
            if notification_type not in by_type:
                by_type[notification_type] = 0
            by_type[notification_type] += 1

        return {"total": total, "unread": unread, "read": total - unread, "by_type": by_type, "period_days": days}

    @staticmethod
    def cleanup_inactive_device_tokens(days: int = 30) -> int:
        """
        Clean up device tokens that haven't been used recently

        Args:
            days: Number of days of inactivity

        Returns:
            Number of tokens cleaned up
        """
        cutoff_date = timezone.now() - timedelta(days=days)

        inactive_tokens = DeviceToken.objects.filter(last_used__lt=cutoff_date, is_active=True)

        count = inactive_tokens.count()
        inactive_tokens.update(is_active=False)

        logger.info(f"Deactivated {count} inactive device tokens")
        return count

    @staticmethod
    def get_notification_performance_metrics(days: int = 7) -> Dict[str, Any]:
        """
        Get performance metrics for notifications

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with performance metrics
        """
        from django.db.models import Avg, Count, Q

        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        notifications = Notification.objects.filter(created_at__gte=start_date, created_at__lt=end_date)

        total = notifications.count()
        if total == 0:
            return {
                "total_notifications": 0,
                "delivery_rate": 0,
                "read_rate": 0,
                "failure_rate": 0,
                "avg_delivery_time": 0,
                "by_status": {},
                "by_type": {},
            }

        # Status breakdown
        status_counts = notifications.values("status").annotate(count=Count("id"))
        by_status = {item["status"]: item["count"] for item in status_counts}

        # Type breakdown
        type_counts = notifications.values("notification_type").annotate(count=Count("id"))
        by_type = {item["notification_type"]: item["count"] for item in type_counts}

        # Calculate rates
        delivered = by_status.get("delivered", 0)
        read = by_status.get("read", 0)
        failed = by_status.get("failed", 0)

        delivery_rate = (delivered / total) * 100 if total > 0 else 0
        read_rate = (read / total) * 100 if total > 0 else 0
        failure_rate = (failed / total) * 100 if total > 0 else 0

        # Average delivery time (in seconds)
        delivered_notifications = notifications.filter(sent_at__isnull=False, delivered_at__isnull=False)

        avg_delivery_time = 0
        if delivered_notifications.exists():
            delivery_times = []
            for notification in delivered_notifications:
                if notification.sent_at and notification.delivered_at:
                    delta = notification.delivered_at - notification.sent_at
                    delivery_times.append(delta.total_seconds())

            if delivery_times:
                avg_delivery_time = sum(delivery_times) / len(delivery_times)

        return {
            "total_notifications": total,
            "delivery_rate": round(delivery_rate, 2),
            "read_rate": round(read_rate, 2),
            "failure_rate": round(failure_rate, 2),
            "avg_delivery_time": round(avg_delivery_time, 2),
            "by_status": by_status,
            "by_type": by_type,
            "period_days": days,
        }


class NotificationTemplateBuilder:
    """Builder class for creating notification templates"""

    def __init__(self):
        self.template_data = {}

    def name(self, name: str):
        """Set template name"""
        self.template_data["name"] = name
        return self

    def type(self, template_type: str):
        """Set template type"""
        self.template_data["template_type"] = template_type
        return self

    def title(self, title_template: str):
        """Set title template"""
        self.template_data["title_template"] = title_template
        return self

    def body(self, body_template: str):
        """Set body template"""
        self.template_data["body_template"] = body_template
        return self

    def action_url(self, action_url_template: str):
        """Set action URL template"""
        self.template_data["action_url_template"] = action_url_template
        return self

    def icon(self, icon_url: str):
        """Set icon URL"""
        self.template_data["icon_url"] = icon_url
        return self

    def variables(self, variables: List[str]):
        """Set template variables"""
        self.template_data["variables"] = variables
        return self

    def active(self, is_active: bool = True):
        """Set active status"""
        self.template_data["is_active"] = is_active
        return self

    def build(self) -> NotificationTemplate:
        """Build and save the template"""
        return NotificationTemplate.objects.create(**self.template_data)


class NotificationRuleBuilder:
    """Builder class for creating notification rules"""

    def __init__(self):
        self.rule_data = {}

    def name(self, name: str):
        """Set rule name"""
        self.rule_data["name"] = name
        return self

    def description(self, description: str):
        """Set rule description"""
        self.rule_data["description"] = description
        return self

    def trigger(self, trigger_event: str):
        """Set trigger event"""
        self.rule_data["trigger_event"] = trigger_event
        return self

    def template(self, template: Union[NotificationTemplate, str]):
        """Set template (instance or name)"""
        if isinstance(template, str):
            template = NotificationTemplate.objects.get(name=template)
        self.rule_data["template"] = template
        return self

    def conditions(self, conditions: List[Dict]):
        """Set rule conditions"""
        self.rule_data["conditions"] = conditions
        return self

    def target_users(self, target_config: Dict):
        """Set target user configuration"""
        self.rule_data["target_users"] = target_config
        return self

    def delay(self, delay_minutes: int):
        """Set delay in minutes"""
        self.rule_data["delay_minutes"] = delay_minutes
        return self

    def priority(self, priority: int):
        """Set priority (1-10)"""
        self.rule_data["priority"] = priority
        return self

    def active(self, is_active: bool = True):
        """Set active status"""
        self.rule_data["is_active"] = is_active
        return self

    def build(self) -> NotificationRule:
        """Build and save the rule"""
        return NotificationRule.objects.create(**self.rule_data)


def create_default_templates():
    """Create default notification templates for common scenarios"""

    templates = [
        {
            "name": "order_created",
            "template_type": "push",
            "title_template": "Order Created",
            "body_template": "Your order #{order_number} has been created successfully.",
            "variables": ["order_number", "customer_name"],
        },
        {
            "name": "order_confirmed",
            "template_type": "push",
            "title_template": "Order Confirmed",
            "body_template": "Your order #{order_number} has been confirmed and is being processed.",
            "variables": ["order_number", "customer_name"],
        },
        {
            "name": "order_shipped",
            "template_type": "push",
            "title_template": "Order Shipped",
            "body_template": "Your order #{order_number} has been shipped. Track your order for updates.",
            "variables": ["order_number", "tracking_number", "customer_name"],
        },
        {
            "name": "order_delivered",
            "template_type": "push",
            "title_template": "Order Delivered",
            "body_template": "Your order #{order_number} has been delivered successfully.",
            "variables": ["order_number", "customer_name"],
        },
        {
            "name": "payment_received",
            "template_type": "push",
            "title_template": "Payment Received",
            "body_template": "Payment of Rs. {amount} has been received for order #{order_number}.",
            "variables": ["amount", "order_number", "customer_name"],
        },
        {
            "name": "payment_failed",
            "template_type": "push",
            "title_template": "Payment Failed",
            "body_template": "Payment for order #{order_number} failed. Please try again.",
            "variables": ["order_number", "customer_name"],
        },
        {
            "name": "stock_low",
            "template_type": "push",
            "title_template": "Low Stock Alert",
            "body_template": "Stock for {product_name} is running low. Only {current_stock} items left.",
            "variables": ["product_name", "current_stock", "threshold"],
        },
        {
            "name": "delivery_assigned",
            "template_type": "push",
            "title_template": "Delivery Assigned",
            "body_template": "A delivery has been assigned to you. Check your dashboard for details.",
            "variables": ["delivery_id", "pickup_location", "delivery_location"],
        },
        {
            "name": "welcome_user",
            "template_type": "push",
            "title_template": "Welcome to Mulya Bazzar!",
            "body_template": "Welcome {full_name}! Start exploring fresh products from local producers.",
            "variables": ["full_name", "username"],
        },
    ]

    created_templates = []
    for template_data in templates:
        template, created = NotificationTemplate.objects.get_or_create(name=template_data["name"], defaults=template_data)
        if created:
            created_templates.append(template)
            logger.info(f"Created default template: {template.name}")

    return created_templates


def create_default_rules():
    """Create default notification rules for common scenarios"""

    # Ensure default templates exist
    create_default_templates()

    rules = [
        {
            "name": "Order Creation Notification",
            "description": "Notify user when order is created",
            "trigger_event": "order_created",
            "template": "order_created",
            "target_users": {"event_based": {"use_event_user": True}},
            "priority": 8,
        },
        {
            "name": "Order Confirmation Notification",
            "description": "Notify user when order is confirmed",
            "trigger_event": "order_confirmed",
            "template": "order_confirmed",
            "target_users": {"event_based": {"use_event_user": True}},
            "priority": 9,
        },
        {
            "name": "Order Shipped Notification",
            "description": "Notify user when order is shipped",
            "trigger_event": "order_shipped",
            "template": "order_shipped",
            "target_users": {"event_based": {"use_event_user": True}},
            "priority": 8,
        },
        {
            "name": "Order Delivered Notification",
            "description": "Notify user when order is delivered",
            "trigger_event": "order_delivered",
            "template": "order_delivered",
            "target_users": {"event_based": {"use_event_user": True}},
            "priority": 9,
        },
        {
            "name": "Payment Success Notification",
            "description": "Notify user when payment is successful",
            "trigger_event": "payment_received",
            "template": "payment_received",
            "target_users": {"event_based": {"use_event_user": True}},
            "priority": 9,
        },
        {
            "name": "Payment Failed Notification",
            "description": "Notify user when payment fails",
            "trigger_event": "payment_failed",
            "template": "payment_failed",
            "target_users": {"event_based": {"use_event_user": True}},
            "priority": 10,
        },
        {
            "name": "Low Stock Alert for Producers",
            "description": "Alert producers when stock is low",
            "trigger_event": "stock_low",
            "template": "stock_low",
            "target_users": {"event_based": {"related_users": "producer_id"}},
            "priority": 7,
        },
        {
            "name": "Delivery Assignment Notification",
            "description": "Notify transporter when delivery is assigned",
            "trigger_event": "delivery_assigned",
            "template": "delivery_assigned",
            "target_users": {"event_based": {"related_users": "transporter_id"}},
            "priority": 9,
        },
        {
            "name": "Welcome New User",
            "description": "Welcome notification for new users",
            "trigger_event": "user_registered",
            "template": "welcome_user",
            "target_users": {"event_based": {"use_event_user": True}},
            "delay_minutes": 5,  # Send after 5 minutes
            "priority": 5,
        },
    ]

    created_rules = []
    for rule_data in rules:
        template_name = rule_data.pop("template")
        template = NotificationTemplate.objects.get(name=template_name)
        rule_data["template"] = template

        rule, created = NotificationRule.objects.get_or_create(name=rule_data["name"], defaults=rule_data)
        if created:
            created_rules.append(rule)
            logger.info(f"Created default rule: {rule.name}")

    return created_rules


def setup_notification_system():
    """Setup the notification system with default templates and rules"""
    logger.info("Setting up notification system...")

    templates = create_default_templates()
    rules = create_default_rules()

    logger.info(f"Setup complete: {len(templates)} templates, {len(rules)} rules created")

    return {"templates": templates, "rules": rules}
