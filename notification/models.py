import json
import uuid

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

User = get_user_model()


class NotificationTemplate(models.Model):
    """Template for notification messages with dynamic content support"""

    TEMPLATE_TYPES = [
        ("push", "Push Notification"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("in_app", "In-App Notification"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    title_template = models.CharField(
        max_length=255, help_text="Template for notification title with {variable} placeholders"
    )
    body_template = models.TextField(help_text="Template for notification body with {variable} placeholders")
    action_url_template = models.URLField(blank=True, null=True, help_text="Optional action URL template")
    icon_url = models.URLField(blank=True, null=True)
    variables = models.JSONField(default=list, help_text="List of available variables for this template")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_templates"
        indexes = [
            models.Index(fields=["template_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.template_type})"

    def render(self, context: dict) -> dict:
        """Render template with provided context variables"""
        try:
            title = self.title_template.format(**context)
            body = self.body_template.format(**context)
            action_url = self.action_url_template.format(**context) if self.action_url_template else None

            return {
                "title": title,
                "body": body,
                "action_url": action_url,
                "icon_url": self.icon_url,
            }
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")


class NotificationRule(models.Model):
    """Rules engine for event-driven notification triggers"""

    TRIGGER_EVENTS = [
        ("order_created", "Order Created"),
        ("order_confirmed", "Order Confirmed"),
        ("order_shipped", "Order Shipped"),
        ("order_delivered", "Order Delivered"),
        ("order_cancelled", "Order Cancelled"),
        ("payment_received", "Payment Received"),
        ("payment_failed", "Payment Failed"),
        ("stock_low", "Stock Low"),
        ("stock_out", "Stock Out"),
        ("bid_created", "Bid Created"),
        ("bid_accepted", "Bid Accepted"),
        ("delivery_assigned", "Delivery Assigned"),
        ("delivery_completed", "Delivery Completed"),
        ("user_registered", "User Registered"),
        ("custom", "Custom Event"),
    ]

    CONDITION_OPERATORS = [
        ("eq", "Equals"),
        ("ne", "Not Equals"),
        ("gt", "Greater Than"),
        ("gte", "Greater Than or Equal"),
        ("lt", "Less Than"),
        ("lte", "Less Than or Equal"),
        ("contains", "Contains"),
        ("in", "In List"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    trigger_event = models.CharField(max_length=50, choices=TRIGGER_EVENTS)
    conditions = models.JSONField(default=list, help_text="List of conditions to match")
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE)
    target_users = models.JSONField(default=dict, help_text="Rules for selecting target users")
    delay_minutes = models.PositiveIntegerField(default=0, help_text="Delay before sending notification")
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_rules"
        indexes = [
            models.Index(fields=["trigger_event", "is_active"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.trigger_event}"

    def evaluate_conditions(self, event_data: dict) -> bool:
        """Evaluate if event data matches rule conditions"""
        if not self.conditions:
            return True

        for condition in self.conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")

            if field not in event_data:
                return False

            event_value = event_data[field]

            if operator == "eq" and event_value != value:
                return False
            elif operator == "ne" and event_value == value:
                return False
            elif operator == "gt" and event_value <= value:
                return False
            elif operator == "gte" and event_value < value:
                return False
            elif operator == "lt" and event_value >= value:
                return False
            elif operator == "lte" and event_value > value:
                return False
            elif operator == "contains" and value not in str(event_value):
                return False
            elif operator == "in" and event_value not in value:
                return False

        return True


class UserNotificationPreference(models.Model):
    """User preferences for notification delivery"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_preferences")
    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)

    # Event-specific preferences
    order_notifications = models.BooleanField(default=True)
    payment_notifications = models.BooleanField(default=True)
    marketing_notifications = models.BooleanField(default=False)
    delivery_notifications = models.BooleanField(default=True)

    # Quiet hours
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_start_time = models.TimeField(null=True, blank=True)
    quiet_end_time = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default="UTC")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_notification_preferences"

    def __str__(self):
        return f"Preferences for {self.user.username}"

    def is_quiet_time(self) -> bool:
        """Check if current time is within quiet hours"""
        if not self.quiet_hours_enabled or not self.quiet_start_time or not self.quiet_end_time:
            return False

        now = timezone.now().time()
        if self.quiet_start_time <= self.quiet_end_time:
            return self.quiet_start_time <= now <= self.quiet_end_time
        else:  # Quiet hours span midnight
            return now >= self.quiet_start_time or now <= self.quiet_end_time


class DeviceToken(models.Model):
    """Store device tokens for push notifications"""

    DEVICE_TYPES = [
        ("ios", "iOS"),
        ("android", "Android"),
        ("web", "Web"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.TextField(unique=True)
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    device_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "device_tokens"
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["device_type"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.device_type}"


class Notification(models.Model):
    """Individual notification records"""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("read", "Read"),
        ("cancelled", "Cancelled"),
    ]

    NOTIFICATION_TYPES = [
        ("push", "Push Notification"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("in_app", "In-App Notification"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    body = models.TextField()
    action_url = models.URLField(blank=True, null=True)
    icon_url = models.URLField(blank=True, null=True)

    # Metadata
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    rule = models.ForeignKey(NotificationRule, on_delete=models.SET_NULL, null=True, blank=True)
    event_data = models.JSONField(default=dict)

    # Related object (generic foreign key)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Status and delivery
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    priority = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    scheduled_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["notification_type", "status"]),
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["priority", "scheduled_at"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    def mark_as_sent(self):
        """Mark notification as sent"""
        self.status = "sent"
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])

    def mark_as_delivered(self):
        """Mark notification as delivered"""
        self.status = "delivered"
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at", "updated_at"])

    def mark_as_read(self):
        """Mark notification as read"""
        if self.status != "read":
            self.status = "read"
            self.read_at = timezone.now()
            self.save(update_fields=["status", "read_at", "updated_at"])

    def mark_as_failed(self, error_message: str = ""):
        """Mark notification as failed"""
        self.status = "failed"
        self.error_message = error_message
        self.retry_count += 1
        self.save(update_fields=["status", "error_message", "retry_count", "updated_at"])

    def can_retry(self) -> bool:
        """Check if notification can be retried"""
        return self.status == "failed" and self.retry_count < self.max_retries


class NotificationBatch(models.Model):
    """Batch processing for bulk notifications"""

    BATCH_STATUS = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE)
    target_users = models.ManyToManyField(User, related_name="notification_batches")

    status = models.CharField(max_length=20, choices=BATCH_STATUS, default="pending")
    total_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    scheduled_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    context_data = models.JSONField(default=dict, help_text="Context data for template rendering")

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_batches")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_batches"
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.status}"


class NotificationEvent(models.Model):
    """Log of notification events for analytics and debugging"""

    EVENT_TYPES = [
        ("triggered", "Rule Triggered"),
        ("created", "Notification Created"),
        ("sent", "Notification Sent"),
        ("delivered", "Notification Delivered"),
        ("failed", "Notification Failed"),
        ("read", "Notification Read"),
        ("clicked", "Notification Clicked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "notification_events"
        indexes = [
            models.Index(fields=["notification", "event_type"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"{self.notification.title} - {self.event_type}"
