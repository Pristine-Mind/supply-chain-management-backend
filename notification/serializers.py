from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationEvent,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)

User = get_user_model()


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Serializer for notification templates"""

    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "name",
            "template_type",
            "title_template",
            "body_template",
            "action_url_template",
            "icon_url",
            "variables",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_variables(self, value):
        """Validate that variables is a list"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Variables must be a list")
        return value


class NotificationRuleSerializer(serializers.ModelSerializer):
    """Serializer for notification rules"""

    template_name = serializers.CharField(source="template.name", read_only=True)

    class Meta:
        model = NotificationRule
        fields = [
            "id",
            "name",
            "description",
            "trigger_event",
            "conditions",
            "template",
            "template_name",
            "target_users",
            "delay_minutes",
            "is_active",
            "priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_conditions(self, value):
        """Validate conditions format"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Conditions must be a list")

        for condition in value:
            if not isinstance(condition, dict):
                raise serializers.ValidationError("Each condition must be a dictionary")

            required_fields = ["field", "operator", "value"]
            for field in required_fields:
                if field not in condition:
                    raise serializers.ValidationError(f"Condition missing required field: {field}")

        return value

    def validate_target_users(self, value):
        """Validate target users configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Target users must be a dictionary")
        return value


class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for user notification preferences"""

    class Meta:
        model = UserNotificationPreference
        fields = [
            "push_enabled",
            "email_enabled",
            "sms_enabled",
            "in_app_enabled",
            "order_notifications",
            "payment_notifications",
            "marketing_notifications",
            "delivery_notifications",
            "quiet_hours_enabled",
            "quiet_start_time",
            "quiet_end_time",
            "timezone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class DeviceTokenSerializer(serializers.ModelSerializer):
    """Serializer for device tokens"""

    class Meta:
        model = DeviceToken
        fields = ["id", "token", "device_type", "device_id", "is_active", "last_used", "created_at"]
        read_only_fields = ["id", "last_used", "created_at"]

    def create(self, validated_data):
        """Create or update device token"""
        user = self.context["request"].user
        token = validated_data["token"]

        # Check if token already exists
        existing_token = DeviceToken.objects.filter(token=token).first()
        if existing_token:
            # Update existing token
            for key, value in validated_data.items():
                setattr(existing_token, key, value)
            existing_token.user = user
            existing_token.save()
            return existing_token

        # Create new token
        validated_data["user"] = user
        return super().create(validated_data)


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "user_name",
            "notification_type",
            "title",
            "body",
            "action_url",
            "icon_url",
            "template",
            "template_name",
            "rule",
            "rule_name",
            "event_data",
            "status",
            "priority",
            "scheduled_at",
            "sent_at",
            "delivered_at",
            "read_at",
            "error_message",
            "retry_count",
            "max_retries",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user_name",
            "template_name",
            "rule_name",
            "sent_at",
            "delivered_at",
            "read_at",
            "error_message",
            "retry_count",
            "created_at",
            "updated_at",
        ]


class NotificationListSerializer(serializers.ModelSerializer):
    """Simplified serializer for notification lists"""

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "action_url",
            "icon_url",
            "status",
            "priority",
            "created_at",
            "read_at",
        ]
        read_only_fields = ["id", "created_at", "read_at"]


class NotificationBatchSerializer(serializers.ModelSerializer):
    """Serializer for notification batches"""

    template_name = serializers.CharField(source="template.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    target_user_count = serializers.IntegerField(source="target_users.count", read_only=True)

    class Meta:
        model = NotificationBatch
        fields = [
            "id",
            "name",
            "description",
            "template",
            "template_name",
            "status",
            "total_count",
            "sent_count",
            "failed_count",
            "scheduled_at",
            "started_at",
            "completed_at",
            "context_data",
            "created_by",
            "created_by_name",
            "target_user_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "template_name",
            "created_by_name",
            "target_user_count",
            "status",
            "total_count",
            "sent_count",
            "failed_count",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        """Create notification batch"""
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class NotificationEventSerializer(serializers.ModelSerializer):
    """Serializer for notification events"""

    class Meta:
        model = NotificationEvent
        fields = ["id", "notification", "event_type", "timestamp", "metadata"]
        read_only_fields = ["id", "timestamp"]


class BulkNotificationSerializer(serializers.Serializer):
    """Serializer for bulk notification creation"""

    template_id = serializers.UUIDField()
    user_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    context_data = serializers.DictField(default=dict)
    notification_type = serializers.ChoiceField(choices=["push", "email", "sms", "in_app"], default="push")
    priority = serializers.IntegerField(min_value=1, max_value=10, default=5)
    scheduled_at = serializers.DateTimeField(required=False)

    def validate_template_id(self, value):
        """Validate that template exists"""
        try:
            NotificationTemplate.objects.get(id=value, is_active=True)
        except NotificationTemplate.DoesNotExist:
            raise serializers.ValidationError("Template not found or inactive")
        return value

    def validate_user_ids(self, value):
        """Validate that users exist"""
        existing_users = User.objects.filter(id__in=value).count()
        if existing_users != len(value):
            raise serializers.ValidationError("Some users not found")
        return value


class NotificationStatsSerializer(serializers.Serializer):
    """Serializer for notification statistics"""

    total = serializers.IntegerField()
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    failed = serializers.IntegerField()
    read = serializers.IntegerField()
    delivery_rate = serializers.FloatField()
    read_rate = serializers.FloatField()
    failure_rate = serializers.FloatField()


class TriggerEventSerializer(serializers.Serializer):
    """Serializer for triggering notification events"""

    event_name = serializers.CharField(max_length=100)
    event_data = serializers.DictField()
    user_id = serializers.IntegerField(required=False)

    def validate_user_id(self, value):
        """Validate that user exists if provided"""
        if value:
            try:
                User.objects.get(id=value)
            except User.DoesNotExist:
                raise serializers.ValidationError("User not found")
        return value


class DeviceTokenUpdateSerializer(serializers.Serializer):
    """Serializer for updating device token"""

    token = serializers.CharField(max_length=500)
    device_type = serializers.ChoiceField(choices=["ios", "android", "web"])
    device_id = serializers.CharField(max_length=255, required=False)


class NotificationActionSerializer(serializers.Serializer):
    """Serializer for notification actions (mark as read, etc.)"""

    action = serializers.ChoiceField(choices=["read", "unread"])
    notification_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)

    def validate_notification_ids(self, value):
        """Validate that notifications exist and belong to user"""
        user = self.context["request"].user
        existing_notifications = Notification.objects.filter(id__in=value, user=user).count()

        if existing_notifications != len(value):
            raise serializers.ValidationError("Some notifications not found or don't belong to user")

        return value
