from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationEvent,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "template_type", "is_active", "usage_count", "created_at"]
    list_filter = ["template_type", "is_active", "created_at"]
    search_fields = ["name", "title_template", "body_template"]
    readonly_fields = ["id", "created_at", "updated_at", "usage_count"]

    fieldsets = (
        ("Basic Information", {"fields": ("id", "name", "template_type", "is_active")}),
        ("Template Content", {"fields": ("title_template", "body_template", "action_url_template", "icon_url")}),
        ("Configuration", {"fields": ("variables",)}),
        ("Metadata", {"fields": ("created_at", "updated_at", "usage_count"), "classes": ("collapse",)}),
    )

    def usage_count(self, obj):
        """Show how many times this template has been used"""
        count = obj.notifications.count()
        return count

    usage_count.short_description = "Usage Count"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(notification_count=Count("notifications"))


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "trigger_event", "template", "is_active", "priority", "triggered_count", "created_at"]
    list_filter = ["trigger_event", "is_active", "priority", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["id", "created_at", "updated_at", "triggered_count"]
    autocomplete_fields = ["template"]

    fieldsets = (
        ("Basic Information", {"fields": ("id", "name", "description", "is_active")}),
        ("Trigger Configuration", {"fields": ("trigger_event", "conditions", "template")}),
        ("Target Configuration", {"fields": ("target_users", "delay_minutes", "priority")}),
        ("Metadata", {"fields": ("created_at", "updated_at", "triggered_count"), "classes": ("collapse",)}),
    )

    def triggered_count(self, obj):
        """Show how many times this rule has been triggered"""
        count = obj.notifications.count()
        return count

    triggered_count.short_description = "Triggered Count"


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "push_enabled",
        "email_enabled",
        "sms_enabled",
        "in_app_enabled",
        "quiet_hours_enabled",
        "updated_at",
    ]
    list_filter = [
        "push_enabled",
        "email_enabled",
        "sms_enabled",
        "in_app_enabled",
        "order_notifications",
        "payment_notifications",
        "marketing_notifications",
        "delivery_notifications",
        "quiet_hours_enabled",
    ]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["user"]

    fieldsets = (
        ("User", {"fields": ("user",)}),
        ("Channel Preferences", {"fields": ("push_enabled", "email_enabled", "sms_enabled", "in_app_enabled")}),
        (
            "Event Preferences",
            {
                "fields": (
                    "order_notifications",
                    "payment_notifications",
                    "marketing_notifications",
                    "delivery_notifications",
                )
            },
        ),
        ("Quiet Hours", {"fields": ("quiet_hours_enabled", "quiet_start_time", "quiet_end_time", "timezone")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "device_type", "masked_token", "is_active", "last_used", "created_at"]
    list_filter = ["device_type", "is_active", "created_at", "last_used"]
    search_fields = ["user__username", "user__email", "device_id"]
    readonly_fields = ["last_used", "created_at"]
    autocomplete_fields = ["user"]

    def masked_token(self, obj):
        """Show masked token for security"""
        if len(obj.token) > 20:
            return f"{obj.token[:10]}...{obj.token[-10:]}"
        return obj.token[:10] + "..."

    masked_token.short_description = "Token"


class NotificationEventInline(admin.TabularInline):
    model = NotificationEvent
    extra = 0
    readonly_fields = ["timestamp"]
    fields = ["event_type", "timestamp", "metadata"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "notification_type", "status", "priority", "scheduled_at", "sent_at", "created_at"]
    list_filter = ["notification_type", "status", "priority", "created_at", "scheduled_at", "sent_at"]
    search_fields = ["title", "body", "user__username", "user__email"]
    readonly_fields = ["id", "sent_at", "delivered_at", "read_at", "created_at", "updated_at"]
    autocomplete_fields = ["user", "template", "rule"]
    inlines = [NotificationEventInline]
    date_hierarchy = "created_at"

    fieldsets = (
        ("Basic Information", {"fields": ("id", "user", "notification_type", "status", "priority")}),
        ("Content", {"fields": ("title", "body", "action_url", "icon_url")}),
        ("Configuration", {"fields": ("template", "rule", "event_data")}),
        ("Scheduling", {"fields": ("scheduled_at", "sent_at", "delivered_at", "read_at")}),
        ("Error Handling", {"fields": ("error_message", "retry_count", "max_retries")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = ["mark_as_sent", "mark_as_failed", "retry_notifications"]

    def mark_as_sent(self, request, queryset):
        """Mark selected notifications as sent"""
        updated = queryset.filter(status="pending").update(status="sent", sent_at=timezone.now())
        self.message_user(request, f"{updated} notifications marked as sent.")

    mark_as_sent.short_description = "Mark selected notifications as sent"

    def mark_as_failed(self, request, queryset):
        """Mark selected notifications as failed"""
        updated = queryset.filter(status__in=["pending", "sent"]).update(
            status="failed", error_message="Manually marked as failed by admin"
        )
        self.message_user(request, f"{updated} notifications marked as failed.")

    mark_as_failed.short_description = "Mark selected notifications as failed"

    def retry_notifications(self, request, queryset):
        """Retry failed notifications"""
        from .tasks import send_notification_task

        retried = 0
        for notification in queryset.filter(status="failed"):
            if notification.can_retry():
                notification.status = "pending"
                notification.error_message = ""
                notification.save()
                send_notification_task.delay(str(notification.id))
                retried += 1

        self.message_user(request, f"{retried} notifications scheduled for retry.")

    retry_notifications.short_description = "Retry failed notifications"


@admin.register(NotificationBatch)
class NotificationBatchAdmin(admin.ModelAdmin):
    list_display = ["name", "template", "status", "total_count", "sent_count", "failed_count", "progress_bar", "created_at"]
    list_filter = ["status", "created_at", "scheduled_at"]
    search_fields = ["name", "description"]
    readonly_fields = [
        "id",
        "total_count",
        "sent_count",
        "failed_count",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    ]
    autocomplete_fields = ["template", "created_by"]
    filter_horizontal = ["target_users"]

    fieldsets = (
        ("Basic Information", {"fields": ("id", "name", "description", "template")}),
        ("Configuration", {"fields": ("target_users", "context_data", "scheduled_at")}),
        ("Status", {"fields": ("status", "total_count", "sent_count", "failed_count")}),
        ("Timing", {"fields": ("started_at", "completed_at")}),
        ("Metadata", {"fields": ("created_by", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def progress_bar(self, obj):
        """Show progress bar for batch processing"""
        if obj.total_count == 0:
            return format_html('<div style="width: 100px; background-color: #f0f0f0;">No data</div>')

        progress = (obj.sent_count / obj.total_count) * 100
        color = "#28a745" if obj.status == "completed" else "#007bff"

        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0;">'
            '<div style="width: {}%; background-color: {}; height: 20px; text-align: center; color: white;">'
            "{}%</div></div>",
            progress,
            color,
            int(progress),
        )

    progress_bar.short_description = "Progress"


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    list_display = ["notification", "event_type", "timestamp"]
    list_filter = ["event_type", "timestamp"]
    search_fields = ["notification__title", "notification__user__username"]
    readonly_fields = ["id", "timestamp"]
    autocomplete_fields = ["notification"]
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        """Disable adding events manually"""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable changing events"""
        return False


class NotificationAnalyticsAdmin(admin.ModelAdmin):
    """Custom admin for notification analytics"""

    def changelist_view(self, request, extra_context=None):
        from datetime import timedelta

        from django.db.models import Count

        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)

        total_notifications = Notification.objects.filter(created_at__gte=start_date).count()

        status_stats = Notification.objects.filter(created_at__gte=start_date).values("status").annotate(count=Count("id"))

        type_stats = (
            Notification.objects.filter(created_at__gte=start_date).values("notification_type").annotate(count=Count("id"))
        )

        active_tokens = DeviceToken.objects.filter(is_active=True).count()

        active_rules = NotificationRule.objects.filter(is_active=True).count()

        extra_context = extra_context or {}
        extra_context.update(
            {
                "total_notifications": total_notifications,
                "status_stats": list(status_stats),
                "type_stats": list(type_stats),
                "active_tokens": active_tokens,
                "active_rules": active_rules,
            }
        )

        return super().changelist_view(request, extra_context)


class NotificationAnalytics(Notification):
    """Proxy model for analytics dashboard"""

    class Meta:
        proxy = True
        verbose_name = "Notification Analytics"
        verbose_name_plural = "Notification Analytics"


admin.site.register(NotificationAnalytics, NotificationAnalyticsAdmin)
