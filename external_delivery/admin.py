from django.contrib import admin
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    APIUsageLog,
    ExternalBusiness,
    ExternalDelivery,
    ExternalDeliveryStatusHistory,
    RateLimitLog,
    WebhookLog,
)


@admin.register(ExternalBusiness)
class ExternalBusinessAdmin(admin.ModelAdmin):
    list_display = [
        "business_name",
        "status_badge",
        "plan_badge",
        "contact_email",
        "delivery_count",
        "success_rate",
        "created_at",
    ]
    list_filter = ["status", "plan", "created_at", "approved_at"]
    search_fields = ["business_name", "business_email", "contact_person", "api_key"]
    readonly_fields = ["api_key", "webhook_secret", "created_at", "updated_at", "usage_stats", "api_usage_summary"]
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "business_name",
                    "business_email",
                    "contact_person",
                    "contact_phone",
                    "business_address",
                    "registration_number",
                    "website",
                )
            },
        ),
        (
            "API Configuration",
            {"fields": ("api_key", "webhook_secret", "webhook_url", "rate_limit_per_minute", "rate_limit_per_hour")},
        ),
        (
            "Business Settings",
            {"fields": ("plan", "status", "max_delivery_value", "allowed_pickup_cities", "allowed_delivery_cities")},
        ),
        ("Billing", {"fields": ("monthly_fee", "per_delivery_fee")}),
        ("Approval Information", {"fields": ("created_by", "approved_by", "approved_at", "created_at", "updated_at")}),
        ("Statistics", {"fields": ("usage_stats", "api_usage_summary")}),
    )

    def status_badge(self, obj):
        colors = {"pending": "#FFA500", "approved": "#28A745", "suspended": "#DC3545", "rejected": "#6C757D"}
        color = colors.get(obj.status, "#6C757D")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def plan_badge(self, obj):
        colors = {"free": "#6C757D", "starter": "#17A2B8", "business": "#FFC107", "enterprise": "#28A745"}
        color = colors.get(obj.plan, "#6C757D")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_plan_display(),
        )

    plan_badge.short_description = "Plan"

    def contact_email(self, obj):
        return obj.business_email

    contact_email.short_description = "Email"

    def delivery_count(self, obj):
        return obj.external_deliveries.count()

    delivery_count.short_description = "Deliveries"

    def success_rate(self, obj):
        total = obj.external_deliveries.count()
        if total == 0:
            return "N/A"
        successful = obj.external_deliveries.filter(status="delivered").count()
        rate = (successful / total) * 100
        return f"{rate:.1f}%"

    success_rate.short_description = "Success Rate"

    def usage_stats(self, obj):
        stats = obj.get_usage_stats()
        return format_html(
            "<strong>This Month:</strong> {} deliveries<br>"
            "<strong>Total:</strong> {} deliveries<br>"
            "<strong>Successful:</strong> {}",
            stats["current_month_deliveries"],
            stats["total_deliveries"],
            stats["successful_deliveries"],
        )

    usage_stats.short_description = "Usage Statistics"

    def api_usage_summary(self, obj):
        last_30_days = timezone.now() - timezone.timedelta(days=30)
        logs = obj.api_usage_logs.filter(created_at__gte=last_30_days)

        total_requests = logs.count()
        error_requests = logs.filter(response_status__gte=400).count()
        avg_response_time = logs.aggregate(avg_time=Avg("response_time"))["avg_time"] or 0

        return format_html(
            "<strong>Last 30 Days:</strong><br>" "Requests: {} (Errors: {})<br>" "Avg Response Time: {:.3f}s",
            total_requests,
            error_requests,
            avg_response_time,
        )

    api_usage_summary.short_description = "API Usage (30d)"

    actions = ["approve_businesses", "suspend_businesses", "generate_new_api_keys"]

    def approve_businesses(self, request, queryset):
        updated = queryset.filter(status="pending").update(
            status="approved", approved_by=request.user, approved_at=timezone.now()
        )
        self.message_user(request, f"Approved {updated} businesses.")

    approve_businesses.short_description = "Approve selected businesses"

    def suspend_businesses(self, request, queryset):
        updated = queryset.exclude(status="suspended").update(status="suspended")
        self.message_user(request, f"Suspended {updated} businesses.")

    suspend_businesses.short_description = "Suspend selected businesses"

    def generate_new_api_keys(self, request, queryset):
        for business in queryset:
            business.api_key = business.generate_api_key()
            business.webhook_secret = business.generate_webhook_secret()
            business.save(update_fields=["api_key", "webhook_secret"])
        self.message_user(request, f"Generated new API keys for {queryset.count()} businesses.")

    generate_new_api_keys.short_description = "Generate new API keys"


class StatusHistoryInline(admin.TabularInline):
    model = ExternalDeliveryStatusHistory
    extra = 0
    readonly_fields = ["old_status", "new_status", "reason", "changed_by", "changed_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ExternalDelivery)
class ExternalDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "tracking_number",
        "business_name",
        "status_badge",
        "pickup_city",
        "delivery_city",
        "package_value",
        "delivery_fee",
        "created_at",
    ]
    list_filter = ["status", "external_business", "pickup_city", "delivery_city", "fragile", "is_cod", "created_at"]
    search_fields = [
        "tracking_number",
        "external_delivery_id",
        "external_business__business_name",
        "pickup_name",
        "delivery_name",
        "delivery_phone",
    ]
    readonly_fields = [
        "tracking_number",
        "created_at",
        "updated_at",
        "accepted_at",
        "picked_up_at",
        "delivered_at",
        "cancelled_at",
        "fee_breakdown",
    ]
    inlines = [StatusHistoryInline]

    fieldsets = (
        ("Business & Tracking", {"fields": ("external_business", "external_delivery_id", "tracking_number", "status")}),
        (
            "Pickup Information",
            {
                "fields": (
                    "pickup_name",
                    "pickup_phone",
                    "pickup_address",
                    "pickup_city",
                    "pickup_latitude",
                    "pickup_longitude",
                    "pickup_instructions",
                )
            },
        ),
        (
            "Delivery Information",
            {
                "fields": (
                    "delivery_name",
                    "delivery_phone",
                    "delivery_address",
                    "delivery_city",
                    "delivery_latitude",
                    "delivery_longitude",
                    "delivery_instructions",
                )
            },
        ),
        ("Package Details", {"fields": ("package_description", "package_weight", "package_value", "fragile")}),
        ("Payment & COD", {"fields": ("is_cod", "cod_amount", "fee_breakdown")}),
        ("Scheduling", {"fields": ("scheduled_pickup_time", "scheduled_delivery_time")}),
        ("Assignment & Internal", {"fields": ("assigned_transporter",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at", "accepted_at", "picked_up_at", "delivered_at", "cancelled_at")},
        ),
        ("Notes & Reasons", {"fields": ("notes", "cancellation_reason", "failure_reason")}),
    )

    def business_name(self, obj):
        return obj.external_business.business_name

    business_name.short_description = "Business"

    def status_badge(self, obj):
        colors = {
            "pending": "#FFA500",
            "accepted": "#17A2B8",
            "picked_up": "#6F42C1",
            "in_transit": "#FD7E14",
            "delivered": "#28A745",
            "cancelled": "#6C757D",
            "failed": "#DC3545",
        }
        color = colors.get(obj.status, "#6C757D")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def fee_breakdown(self, obj):
        if not obj.delivery_fee:
            return "Not calculated"

        return format_html(
            "<strong>Delivery Fee:</strong> NPR {}<br>"
            "<strong>Platform Commission:</strong> NPR {}<br>"
            "<strong>Transporter Earnings:</strong> NPR {}",
            obj.delivery_fee or 0,
            obj.platform_commission or 0,
            obj.transporter_earnings or 0,
        )

    fee_breakdown.short_description = "Fee Breakdown"

    actions = ["calculate_delivery_fees", "export_delivery_data"]

    def calculate_delivery_fees(self, request, queryset):
        for delivery in queryset.filter(delivery_fee__isnull=True):
            fees = delivery.calculate_delivery_fee()
            delivery.delivery_fee = fees["delivery_fee"]
            delivery.platform_commission = fees["platform_commission"]
            delivery.transporter_earnings = fees["transporter_earnings"]
            delivery.save(update_fields=["delivery_fee", "platform_commission", "transporter_earnings"])
        self.message_user(request, f"Calculated fees for {queryset.count()} deliveries.")

    calculate_delivery_fees.short_description = "Calculate delivery fees"


@admin.register(ExternalDeliveryStatusHistory)
class ExternalDeliveryStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ["delivery_tracking", "old_status", "new_status", "changed_by", "changed_at"]
    list_filter = ["old_status", "new_status", "changed_at"]
    search_fields = ["delivery__tracking_number", "delivery__external_business__business_name"]
    readonly_fields = ["delivery", "old_status", "new_status", "reason", "changed_by", "changed_at"]

    def delivery_tracking(self, obj):
        return obj.delivery.tracking_number

    delivery_tracking.short_description = "Tracking Number"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(APIUsageLog)
class APIUsageLogAdmin(admin.ModelAdmin):
    list_display = ["business_name", "method", "endpoint", "response_status", "response_time", "created_at"]
    list_filter = ["external_business", "method", "response_status", "created_at"]
    search_fields = ["external_business__business_name", "endpoint", "request_ip"]
    readonly_fields = [
        "external_business",
        "endpoint",
        "method",
        "request_ip",
        "user_agent",
        "request_size",
        "response_status",
        "response_size",
        "response_time",
        "created_at",
        "request_data",
        "response_data",
        "error_message",
    ]

    def business_name(self, obj):
        return obj.external_business.business_name

    business_name.short_description = "Business"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ["business_name", "event_type", "success_badge", "response_status", "retry_count", "created_at"]
    list_filter = ["external_business", "event_type", "success", "created_at"]
    search_fields = ["external_business__business_name", "webhook_url"]
    readonly_fields = [
        "external_business",
        "delivery",
        "event_type",
        "webhook_url",
        "payload",
        "response_status",
        "response_body",
        "response_time",
        "success",
        "error_message",
        "retry_count",
        "next_retry_at",
        "created_at",
    ]

    def business_name(self, obj):
        return obj.external_business.business_name

    business_name.short_description = "Business"

    def success_badge(self, obj):
        if obj.success:
            return format_html(
                '<span style="background-color: #28A745; color: white; padding: 3px 8px; border-radius: 3px;">✓</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #DC3545; color: white; padding: 3px 8px; border-radius: 3px;">✗</span>'
            )

    success_badge.short_description = "Success"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RateLimitLog)
class RateLimitLogAdmin(admin.ModelAdmin):
    list_display = ["business_name", "endpoint", "request_count", "time_window", "blocked_badge", "created_at"]
    list_filter = ["external_business", "time_window", "blocked", "created_at"]
    search_fields = ["external_business__business_name", "endpoint", "request_ip"]
    readonly_fields = [
        "external_business",
        "request_ip",
        "endpoint",
        "request_count",
        "time_window",
        "blocked",
        "created_at",
    ]

    def business_name(self, obj):
        return obj.external_business.business_name

    business_name.short_description = "Business"

    def blocked_badge(self, obj):
        if obj.blocked:
            return format_html(
                '<span style="background-color: #DC3545; color: white; padding: 3px 8px; border-radius: 3px;">BLOCKED</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #28A745; color: white; padding: 3px 8px; border-radius: 3px;">ALLOWED</span>'
            )

    blocked_badge.short_description = "Status"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
