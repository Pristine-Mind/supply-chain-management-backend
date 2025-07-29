import csv
from datetime import datetime, timedelta

from django.contrib import admin, messages
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Delivery,
    DeliveryPriority,
    DeliveryRating,
    DeliveryRoute,
    DeliveryTracking,
    RouteDelivery,
    Transporter,
    TransporterStatus,
    TransportStatus,
)


class DeliveryTrackingInline(admin.TabularInline):
    model = DeliveryTracking
    extra = 0
    readonly_fields = ["timestamp", "created_by"]
    fields = ["status", "latitude", "longitude", "notes", "created_by", "timestamp"]
    ordering = ["-timestamp"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("created_by")


class DeliveryRatingInline(admin.TabularInline):
    model = DeliveryRating
    extra = 0
    readonly_fields = ["created_at", "overall_rating"]
    fields = [
        "rated_by",
        "overall_rating",
        "punctuality_rating",
        "communication_rating",
        "package_handling_rating",
        "comment",
        "is_anonymous",
        "created_at",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("rated_by")


class RouteDeliveryInline(admin.TabularInline):
    model = RouteDelivery
    extra = 0
    fields = ["delivery", "order"]
    ordering = ["order"]


@admin.register(Transporter)
class TransporterAdmin(admin.ModelAdmin):

    list_display = [
        "user_full_name",
        "license_number",
        "vehicle_type",
        "vehicle_capacity",
        "rating_display",
        "total_deliveries",
        "success_rate_display",
        "cancellation_rate_display",
        "status_display",
        "is_available",
        "is_verified",
        "documents_status",
    ]
    list_filter = [
        "vehicle_type",
        "is_available",
        "is_verified",
        "status",
        "created_at",
        "rating",
        "license_expiry",
        "insurance_expiry",
    ]
    search_fields = [
        "user__first_name",
        "user__last_name",
        "user__email",
        "license_number",
        "vehicle_number",
        "phone",
        "business_name",
    ]
    readonly_fields = [
        "rating",
        "total_deliveries",
        "successful_deliveries",
        "cancelled_deliveries",
        "success_rate_display",
        "cancellation_rate_display",
        "earnings_total",
        "created_at",
        "updated_at",
        "current_location_display",
        "last_location_update",
        "documents_status_detail",
    ]

    fieldsets = (
        ("User Information", {"fields": ("user", "phone", "emergency_contact")}),
        ("Business Information", {"fields": ("business_name", "tax_id"), "classes": ("collapse",)}),
        (
            "License & Vehicle",
            {
                "fields": (
                    "license_number",
                    "license_expiry",
                    "vehicle_type",
                    "vehicle_number",
                    "vehicle_capacity",
                    "vehicle_image",
                    "vehicle_documents",
                    "insurance_expiry",
                )
            },
        ),
        (
            "Location & Availability",
            {
                "fields": (
                    "current_location_display",
                    "service_radius",
                    "is_available",
                    "status",
                    "current_latitude",
                    "current_longitude",
                    "last_location_update",
                )
            },
        ),
        (
            "Performance Metrics",
            {
                "fields": (
                    "rating",
                    "total_deliveries",
                    "successful_deliveries",
                    "cancelled_deliveries",
                    "success_rate_display",
                    "cancellation_rate_display",
                )
            },
        ),
        ("Financial Information", {"fields": ("earnings_total", "commission_rate"), "classes": ("collapse",)}),
        ("Account Status", {"fields": ("is_verified", "verification_documents", "documents_status_detail")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = [
        "verify_transporters",
        "unverify_transporters",
        "activate_transporters",
        "deactivate_transporters",
        "export_transporter_data",
        "check_document_expiry",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def user_full_name(self, obj):
        full_name = obj.user.get_full_name()
        if obj.business_name:
            return f"{full_name} ({obj.business_name})"
        return full_name or obj.user.username

    user_full_name.short_description = "Name/Business"
    user_full_name.admin_order_field = "user__first_name"

    def rating_display(self, obj):
        if obj.rating > 0:
            stars = "★" * int(obj.rating) + "☆" * (5 - int(obj.rating))
            return format_html('<span style="color: gold;" title="{:.2f}/5.00">{}</span>', obj.rating, stars)
        return "No ratings"

    rating_display.short_description = "Rating"
    rating_display.admin_order_field = "rating"

    def success_rate_display(self, obj):
        rate = obj.success_rate
        if rate >= 95:
            color = "green"
        elif rate >= 85:
            color = "orange"
        else:
            color = "red"
        return format_html('<span style="color: {};">{:}%</span>', color, rate)

    success_rate_display.short_description = "Success Rate"

    def cancellation_rate_display(self, obj):
        rate = obj.cancellation_rate
        if rate <= 5:
            color = "green"
        elif rate <= 15:
            color = "orange"
        else:
            color = "red"
        return format_html('<span style="color: {};">{:}%</span>', color, rate)

    cancellation_rate_display.short_description = "Cancel Rate"

    def status_display(self, obj):
        colors = {
            TransporterStatus.ACTIVE: "green",
            TransporterStatus.INACTIVE: "gray",
            TransporterStatus.SUSPENDED: "red",
            TransporterStatus.OFFLINE: "orange",
        }
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = "Status"
    status_display.admin_order_field = "status"

    def documents_status(self, obj):
        if obj.is_documents_expired():
            return format_html('<span style="color: red;">⚠ Expired</span>')
        elif obj.license_expiry and (obj.license_expiry - datetime.now().date()).days <= 30:
            return format_html('<span style="color: orange;">⚠ Expiring Soon</span>')
        return format_html('<span style="color: green;">✓ Valid</span>')

    documents_status.short_description = "Documents"

    def documents_status_detail(self, obj):
        details = []
        today = datetime.now().date()

        if obj.license_expiry:
            days_left = (obj.license_expiry - today).days
            if days_left < 0:
                details.append(f"License: Expired {abs(days_left)} days ago")
            elif days_left <= 30:
                details.append(f"License: Expires in {days_left} days")
            else:
                details.append(f"License: Valid until {obj.license_expiry}")

        if obj.insurance_expiry:
            days_left = (obj.insurance_expiry - today).days
            if days_left < 0:
                details.append(f"Insurance: Expired {abs(days_left)} days ago")
            elif days_left <= 30:
                details.append(f"Insurance: Expires in {days_left} days")
            else:
                details.append(f"Insurance: Valid until {obj.insurance_expiry}")

        return mark_safe("<br>".join(details)) if details else "No expiry dates set"

    documents_status_detail.short_description = "Document Details"

    def current_location_display(self, obj):
        if obj.current_latitude and obj.current_longitude:
            maps_url = f"https://maps.google.com/?q={obj.current_latitude},{obj.current_longitude}"
            last_update = ""
            if obj.last_location_update:
                last_update = f"<br><small>Updated: {obj.last_location_update.strftime('%Y-%m-%d %H:%M')}</small>"
            return format_html(
                '<a href="{}" target="_blank">View on Map</a><br>' "Lat: {:.6f}, Lng: {:.6f}{}",
                maps_url,
                obj.current_latitude,
                obj.current_longitude,
                last_update,
            )
        return "Not available"

    current_location_display.short_description = "Current Location"

    def verify_transporters(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} transporters verified.")

    verify_transporters.short_description = "Verify selected transporters"

    def unverify_transporters(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f"{updated} transporters unverified.")

    unverify_transporters.short_description = "Unverify selected transporters"

    def activate_transporters(self, request, queryset):
        updated = queryset.update(status=TransporterStatus.ACTIVE)
        self.message_user(request, f"{updated} transporters activated.")

    activate_transporters.short_description = "Activate selected transporters"

    def deactivate_transporters(self, request, queryset):
        updated = queryset.update(status=TransporterStatus.INACTIVE)
        self.message_user(request, f"{updated} transporters deactivated.")

    deactivate_transporters.short_description = "Deactivate selected transporters"

    def check_document_expiry(self, request, queryset):
        expired_count = 0
        expiring_count = 0
        today = datetime.now().date()
        thirty_days = today + timedelta(days=30)

        for transporter in queryset:
            if transporter.is_documents_expired():
                expired_count += 1
            elif (transporter.license_expiry and transporter.license_expiry <= thirty_days) or (
                transporter.insurance_expiry and transporter.insurance_expiry <= thirty_days
            ):
                expiring_count += 1

        self.message_user(
            request, f"Document check complete: {expired_count} expired, {expiring_count} expiring within 30 days."
        )

    check_document_expiry.short_description = "Check document expiry status"

    def export_transporter_data(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="transporters.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Name",
                "Email",
                "Phone",
                "License Number",
                "Vehicle Type",
                "Vehicle Capacity",
                "Rating",
                "Total Deliveries",
                "Success Rate",
                "Status",
                "Is Verified",
                "Created At",
            ]
        )

        for transporter in queryset:
            writer.writerow(
                [
                    transporter.user.get_full_name(),
                    transporter.user.email,
                    str(transporter.phone),
                    transporter.license_number,
                    transporter.get_vehicle_type_display(),
                    transporter.vehicle_capacity,
                    transporter.rating,
                    transporter.total_deliveries,
                    f"{transporter.success_rate:.1f}%",
                    transporter.get_status_display(),
                    transporter.is_verified,
                    transporter.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        return response

    export_transporter_data.short_description = "Export transporter data to CSV"


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "tracking_number_display",
        "delivery_id_short",
        "order_number",
        "status_colored",
        "priority_colored",
        "transporter_name",
        "package_weight",
        "delivery_fee",
        "requested_pickup_date",
        "delivered_at",
        "attempts_display",
        "is_overdue_display",
    ]
    list_filter = [
        "status",
        "priority",
        "fragile",
        "requires_signature",
        "requested_pickup_date",
        "created_at",
        "transporter__vehicle_type",
        "delivery_attempts",
    ]
    search_fields = [
        "delivery_id",
        "tracking_number",
        "pickup_address",
        "delivery_address",
        "pickup_contact_name",
        "delivery_contact_name",
        "transporter__user__first_name",
        "transporter__user__last_name",
    ]
    readonly_fields = [
        "delivery_id",
        "tracking_number",
        "created_at",
        "updated_at",
        "assigned_at",
        "picked_up_at",
        "delivered_at",
        "cancelled_at",
        "actual_pickup_time",
        "pickup_location_display",
        "delivery_location_display",
        "delivery_timeline",
        "time_since_pickup_display",
    ]

    fieldsets = (
        ("Basic Information", {"fields": ("delivery_id", "tracking_number", "status", "priority")}),
        (
            "Pickup Details",
            {
                "fields": (
                    "pickup_address",
                    "pickup_location_display",
                    "pickup_contact_name",
                    "pickup_contact_phone",
                    "pickup_instructions",
                    "requested_pickup_date",
                    "actual_pickup_time",
                )
            },
        ),
        (
            "Delivery Details",
            {
                "fields": (
                    "delivery_address",
                    "delivery_location_display",
                    "delivery_contact_name",
                    "delivery_contact_phone",
                    "delivery_instructions",
                    "requested_delivery_date",
                )
            },
        ),
        (
            "Package Information",
            {
                "fields": (
                    "package_weight",
                    "package_dimensions",
                    "package_value",
                    "fragile",
                    "requires_signature",
                    "special_instructions",
                )
            },
        ),
        ("Transport Assignment", {"fields": ("transporter",)}),
        ("Pricing & Distance", {"fields": ("delivery_fee", "fuel_surcharge", "distance_km", "estimated_delivery_time")}),
        (
            "Delivery Management",
            {
                "fields": (
                    "delivery_attempts",
                    "max_delivery_attempts",
                    "delivery_photo",
                    "signature_image",
                    "delivery_notes",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Cancellation", {"fields": ("cancelled_at", "cancellation_reason"), "classes": ("collapse",)}),
        (
            "Timeline",
            {
                "fields": ("delivery_timeline", "assigned_at", "picked_up_at", "delivered_at", "time_since_pickup_display"),
                "classes": ("collapse",),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    inlines = [DeliveryTrackingInline, DeliveryRatingInline]
    actions = ["assign_to_transporter", "mark_as_urgent", "mark_as_same_day", "cancel_deliveries", "export_delivery_data"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("transporter__user", "marketplace_sale")
            .prefetch_related("tracking_updates")
        )

    def tracking_number_display(self, obj):
        return format_html("<strong>{}</strong>", obj.tracking_number or "Not generated")

    tracking_number_display.short_description = "Tracking #"
    tracking_number_display.admin_order_field = "tracking_number"

    def delivery_id_short(self, obj):
        return str(obj.delivery_id)[:8] + "..."

    delivery_id_short.short_description = "Delivery ID"
    delivery_id_short.admin_order_field = "delivery_id"

    def order_number(self, obj):
        return obj.marketplace_sale.order_number if obj.marketplace_sale else "N/A"

    order_number.short_description = "Order Number"
    order_number.admin_order_field = "marketplace_sale__order_number"

    def status_colored(self, obj):
        colors = {
            TransportStatus.AVAILABLE: "#28a745",
            TransportStatus.ASSIGNED: "#ffc107",
            TransportStatus.PICKED_UP: "#17a2b8",
            TransportStatus.IN_TRANSIT: "#007bff",
            TransportStatus.DELIVERED: "#28a745",
            TransportStatus.CANCELLED: "#dc3545",
            TransportStatus.RETURNED: "#6c757d",
            TransportStatus.FAILED: "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"
    status_colored.admin_order_field = "status"

    def priority_colored(self, obj):
        colors = {
            DeliveryPriority.LOW: "#6c757d",
            DeliveryPriority.NORMAL: "#28a745",
            DeliveryPriority.HIGH: "#ffc107",
            DeliveryPriority.URGENT: "#dc3545",
            DeliveryPriority.SAME_DAY: "#dc3545",
        }
        color = colors.get(obj.priority, "#6c757d")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_priority_display())

    priority_colored.short_description = "Priority"
    priority_colored.admin_order_field = "priority"

    def transporter_name(self, obj):
        if obj.transporter:
            return obj.transporter.user.get_full_name()
        return "-"

    transporter_name.short_description = "Transporter"
    transporter_name.admin_order_field = "transporter__user__first_name"

    def attempts_display(self, obj):
        if obj.delivery_attempts > 0:
            color = "red" if obj.delivery_attempts >= obj.max_delivery_attempts else "orange"
            return format_html(
                '<span style="color: {};">{}/{}</span>', color, obj.delivery_attempts, obj.max_delivery_attempts
            )
        return "0"

    attempts_display.short_description = "Attempts"
    attempts_display.admin_order_field = "delivery_attempts"

    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">⚠ Overdue</span>')
        return "On time"

    is_overdue_display.short_description = "Status"

    def time_since_pickup_display(self, obj):
        time_elapsed = obj.time_since_pickup
        if time_elapsed:
            hours = int(time_elapsed.total_seconds() // 3600)
            minutes = int((time_elapsed.total_seconds() % 3600) // 60)
            return f"{hours}h {minutes}m"
        return "Not picked up"

    time_since_pickup_display.short_description = "Time Since Pickup"

    def pickup_location_display(self, obj):
        if obj.pickup_latitude and obj.pickup_longitude:
            maps_url = f"https://maps.google.com/?q={obj.pickup_latitude},{obj.pickup_longitude}"
            return format_html('<a href="{}" target="_blank">View Pickup Location</a>', maps_url)
        return "Coordinates not available"

    pickup_location_display.short_description = "Pickup Location"

    def delivery_location_display(self, obj):
        if obj.delivery_latitude and obj.delivery_longitude:
            maps_url = f"https://maps.google.com/?q={obj.delivery_latitude},{obj.delivery_longitude}"
            return format_html('<a href="{}" target="_blank">View Delivery Location</a>', maps_url)
        return "Coordinates not available"

    delivery_location_display.short_description = "Delivery Location"

    def delivery_timeline(self, obj):
        timeline = []
        if obj.assigned_at:
            timeline.append(f"Assigned: {obj.assigned_at.strftime('%Y-%m-%d %H:%M')}")
        if obj.picked_up_at:
            timeline.append(f"Picked up: {obj.picked_up_at.strftime('%Y-%m-%d %H:%M')}")
        if obj.delivered_at:
            timeline.append(f"Delivered: {obj.delivered_at.strftime('%Y-%m-%d %H:%M')}")
        if obj.cancelled_at:
            timeline.append(f"Cancelled: {obj.cancelled_at.strftime('%Y-%m-%d %H:%M')}")

        if timeline:
            return mark_safe("<br>".join(timeline))
        return "No timeline data"

    delivery_timeline.short_description = "Delivery Timeline"

    def assign_to_transporter(self, request, queryset):
        available_deliveries = queryset.filter(status=TransportStatus.AVAILABLE)
        if available_deliveries.count() != queryset.count():
            messages.warning(request, "Some deliveries are not available for assignment.")

        messages.info(request, f"Assignment form would be displayed for {available_deliveries.count()} deliveries.")

    assign_to_transporter.short_description = "Assign to transporter"

    def mark_as_urgent(self, request, queryset):
        updated = queryset.update(priority=DeliveryPriority.URGENT)
        self.message_user(request, f"{updated} deliveries marked as urgent.")

    mark_as_urgent.short_description = "Mark as urgent"

    def mark_as_same_day(self, request, queryset):
        updated = queryset.update(priority=DeliveryPriority.SAME_DAY)
        self.message_user(request, f"{updated} deliveries marked as same day.")

    mark_as_same_day.short_description = "Mark as same day delivery"

    def cancel_deliveries(self, request, queryset):
        cancellable = queryset.exclude(status__in=[TransportStatus.DELIVERED, TransportStatus.CANCELLED])
        for delivery in cancellable:
            delivery.cancel_delivery(reason="Cancelled by admin", cancelled_by=request.user)

        self.message_user(request, f"{cancellable.count()} deliveries cancelled.")

    cancel_deliveries.short_description = "Cancel selected deliveries"

    def export_delivery_data(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="deliveries.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Tracking Number",
                "Status",
                "Priority",
                "Transporter",
                "Pickup Address",
                "Delivery Address",
                "Package Weight",
                "Delivery Fee",
                "Created At",
                "Delivered At",
            ]
        )

        for delivery in queryset:
            writer.writerow(
                [
                    delivery.tracking_number,
                    delivery.get_status_display(),
                    delivery.get_priority_display(),
                    delivery.transporter.user.get_full_name() if delivery.transporter else "Unassigned",
                    delivery.pickup_address,
                    delivery.delivery_address,
                    delivery.package_weight,
                    delivery.delivery_fee,
                    delivery.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    delivery.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if delivery.delivered_at else "Not delivered",
                ]
            )

        return response

    export_delivery_data.short_description = "Export delivery data to CSV"


@admin.register(DeliveryRoute)
class DeliveryRouteAdmin(admin.ModelAdmin):
    """Admin interface for DeliveryRoute model"""

    list_display = [
        "name",
        "transporter_name",
        "delivery_count",
        "estimated_distance",
        "estimated_duration",
        "status_display",
        "created_at",
    ]
    list_filter = ["created_at", "transporter__vehicle_type"]
    search_fields = ["name", "transporter__user__first_name", "transporter__user__last_name"]
    readonly_fields = ["created_at"]

    inlines = [RouteDeliveryInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("transporter__user").annotate(delivery_count=Count("deliveries"))

    def transporter_name(self, obj):
        return obj.transporter.user.get_full_name()

    transporter_name.short_description = "Transporter"
    transporter_name.admin_order_field = "transporter__user__first_name"

    def delivery_count(self, obj):
        return obj.delivery_count

    delivery_count.short_description = "Deliveries"
    delivery_count.admin_order_field = "delivery_count"

    def status_display(self, obj):
        if obj.completed_at:
            return format_html('<span style="color: green;">Completed</span>')
        elif obj.started_at:
            return format_html('<span style="color: blue;">In Progress</span>')
        else:
            return format_html('<span style="color: orange;">Planned</span>')

    status_display.short_description = "Status"


@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    """Enhanced admin interface for DeliveryTracking model"""

    list_display = [
        "delivery_tracking_display",
        "status_colored",
        "timestamp",
        "location_display",
        "created_by_display",
        "notes_short",
    ]
    list_filter = ["status", "timestamp"]
    search_fields = ["delivery__delivery_id", "delivery__tracking_number", "notes"]
    readonly_fields = ["timestamp"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("delivery", "created_by")

    def delivery_tracking_display(self, obj):
        return f"{obj.delivery.tracking_number} ({str(obj.delivery.delivery_id)[:8]}...)"

    delivery_tracking_display.short_description = "Delivery"
    delivery_tracking_display.admin_order_field = "delivery__tracking_number"

    def status_colored(self, obj):
        colors = {
            TransportStatus.AVAILABLE: "#28a745",
            TransportStatus.ASSIGNED: "#ffc107",
            TransportStatus.PICKED_UP: "#17a2b8",
            TransportStatus.IN_TRANSIT: "#007bff",
            TransportStatus.DELIVERED: "#28a745",
            TransportStatus.CANCELLED: "#dc3545",
            TransportStatus.RETURNED: "#6c757d",
            TransportStatus.FAILED: "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"
    status_colored.admin_order_field = "status"

    def location_display(self, obj):
        if obj.latitude and obj.longitude:
            maps_url = f"https://maps.google.com/?q={obj.latitude},{obj.longitude}"
            return format_html('<a href="{}" target="_blank">{:.4f}, {:.4f}</a>', maps_url, obj.latitude, obj.longitude)
        return "-"

    location_display.short_description = "Location"

    def created_by_display(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return "System"

    created_by_display.short_description = "Created By"
    created_by_display.admin_order_field = "created_by__first_name"

    def notes_short(self, obj):
        if obj.notes:
            return obj.notes[:50] + "..." if len(obj.notes) > 50 else obj.notes
        return "-"

    notes_short.short_description = "Notes"


@admin.register(DeliveryRating)
class DeliveryRatingAdmin(admin.ModelAdmin):
    """Enhanced admin interface for DeliveryRating model"""

    list_display = [
        "delivery_tracking_display",
        "transporter_name",
        "rated_by_name",
        "overall_rating_stars",
        "detailed_ratings_display",
        "comment_short",
        "is_anonymous",
        "created_at",
    ]
    list_filter = [
        "overall_rating",
        "punctuality_rating",
        "communication_rating",
        "package_handling_rating",
        "is_anonymous",
        "created_at",
    ]
    search_fields = [
        "delivery__delivery_id",
        "delivery__tracking_number",
        "transporter__user__first_name",
        "rated_by__first_name",
        "comment",
    ]
    readonly_fields = ["created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("delivery", "transporter__user", "rated_by")

    def delivery_tracking_display(self, obj):
        return f"{obj.delivery.tracking_number} ({str(obj.delivery.delivery_id)[:8]}...)"

    delivery_tracking_display.short_description = "Delivery"
    delivery_tracking_display.admin_order_field = "delivery__tracking_number"

    def transporter_name(self, obj):
        return obj.transporter.user.get_full_name()

    transporter_name.short_description = "Transporter"
    transporter_name.admin_order_field = "transporter__user__first_name"

    def rated_by_name(self, obj):
        if obj.is_anonymous:
            return "Anonymous User"
        return obj.rated_by.get_full_name()

    rated_by_name.short_description = "Rated By"
    rated_by_name.admin_order_field = "rated_by__first_name"

    def overall_rating_stars(self, obj):
        stars = "★" * obj.overall_rating + "☆" * (5 - obj.overall_rating)
        return format_html('<span style="color: gold;">{}</span>', stars)

    overall_rating_stars.short_description = "Overall Rating"
    overall_rating_stars.admin_order_field = "overall_rating"

    def detailed_ratings_display(self, obj):
        ratings = []
        if obj.punctuality_rating:
            ratings.append(f"P: {obj.punctuality_rating}")
        if obj.communication_rating:
            ratings.append(f"C: {obj.communication_rating}")
        if obj.package_handling_rating:
            ratings.append(f"H: {obj.package_handling_rating}")

        return " | ".join(ratings) if ratings else "-"

    detailed_ratings_display.short_description = "P/C/H Ratings"

    def comment_short(self, obj):
        if obj.comment:
            return obj.comment[:100] + "..." if len(obj.comment) > 100 else obj.comment
        return "-"

    comment_short.short_description = "Comment"


class TransportAdminSite(admin.AdminSite):
    site_header = "Transport Management System"
    site_title = "Transport Admin"
    index_title = "Transport Dashboard"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("dashboard/", self.admin_view(self.dashboard_view), name="transport_dashboard"),
            path("analytics/", self.admin_view(self.analytics_view), name="transport_analytics"),
        ]
        return custom_urls + urls

    def index(self, request, extra_context=None):
        """Custom admin index with comprehensive statistics"""
        extra_context = extra_context or {}

        total_deliveries = Delivery.objects.count()
        pending_deliveries = Delivery.objects.filter(status=TransportStatus.AVAILABLE).count()
        active_deliveries = Delivery.objects.filter(
            status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
        ).count()
        completed_deliveries = Delivery.objects.filter(status=TransportStatus.DELIVERED).count()
        cancelled_deliveries = Delivery.objects.filter(status=TransportStatus.CANCELLED).count()
        failed_deliveries = Delivery.objects.filter(status=TransportStatus.FAILED).count()

        total_transporters = Transporter.objects.count()
        active_transporters = Transporter.objects.filter(status=TransporterStatus.ACTIVE, is_available=True).count()
        verified_transporters = Transporter.objects.filter(is_verified=True).count()
        suspended_transporters = Transporter.objects.filter(status=TransporterStatus.SUSPENDED).count()

        avg_rating = Transporter.objects.filter(rating__gt=0).aggregate(avg_rating=Avg("rating"))["avg_rating"] or 0

        success_rate = 0
        if total_deliveries > 0:
            success_rate = (completed_deliveries / total_deliveries) * 100

        urgent_deliveries = Delivery.objects.filter(
            priority__in=[DeliveryPriority.URGENT, DeliveryPriority.SAME_DAY],
            status__in=[
                TransportStatus.AVAILABLE,
                TransportStatus.ASSIGNED,
                TransportStatus.PICKED_UP,
                TransportStatus.IN_TRANSIT,
            ],
        ).count()

        overdue_deliveries = Delivery.objects.filter(
            requested_delivery_date__lt=timezone.now(),
            status__in=[
                TransportStatus.AVAILABLE,
                TransportStatus.ASSIGNED,
                TransportStatus.PICKED_UP,
                TransportStatus.IN_TRANSIT,
            ],
        ).count()

        today = timezone.now().date()
        thirty_days = today + timedelta(days=30)
        expired_docs = Transporter.objects.filter(Q(license_expiry__lt=today) | Q(insurance_expiry__lt=today)).count()
        expiring_docs = (
            Transporter.objects.filter(
                Q(license_expiry__range=[today, thirty_days]) | Q(insurance_expiry__range=[today, thirty_days])
            )
            .exclude(Q(license_expiry__lt=today) | Q(insurance_expiry__lt=today))
            .count()
        )

        recent_deliveries = Delivery.objects.select_related("transporter__user", "marketplace_sale").order_by("-created_at")[
            :10
        ]
        top_transporters = Transporter.objects.filter(total_deliveries__gte=5, rating__gt=0).order_by(
            "-rating", "-total_deliveries"
        )[:5]

        extra_context.update(
            {
                "transport_stats": {
                    "total_deliveries": total_deliveries,
                    "pending_deliveries": pending_deliveries,
                    "active_deliveries": active_deliveries,
                    "completed_deliveries": completed_deliveries,
                    "cancelled_deliveries": cancelled_deliveries,
                    "failed_deliveries": failed_deliveries,
                    "total_transporters": total_transporters,
                    "active_transporters": active_transporters,
                    "verified_transporters": verified_transporters,
                    "suspended_transporters": suspended_transporters,
                    "avg_rating": round(avg_rating, 2),
                    "success_rate": round(success_rate, 1),
                    "urgent_deliveries": urgent_deliveries,
                    "overdue_deliveries": overdue_deliveries,
                    "expired_docs": expired_docs,
                    "expiring_docs": expiring_docs,
                },
                "recent_deliveries": recent_deliveries,
                "top_transporters": top_transporters,
                "alerts": {
                    "urgent_deliveries": urgent_deliveries,
                    "overdue_deliveries": overdue_deliveries,
                    "expired_docs": expired_docs,
                    "expiring_docs": expiring_docs,
                },
            }
        )

        return super().index(request, extra_context)

    def dashboard_view(self, request):
        """Advanced dashboard with charts and analytics"""

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        daily_deliveries = (
            Delivery.objects.filter(created_at__date__range=[start_date, end_date])
            .extra(select={"day": "date(created_at)"})
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        status_distribution = Delivery.objects.values("status").annotate(count=Count("id")).order_by("-count")

        vehicle_performance = (
            Transporter.objects.values("vehicle_type")
            .annotate(count=Count("id"), avg_rating=Avg("rating"), total_deliveries=Count("assigned_deliveries"))
            .order_by("-avg_rating")
        )

        context = {
            "title": "Transport Dashboard",
            "daily_deliveries": list(daily_deliveries),
            "status_distribution": list(status_distribution),
            "vehicle_performance": list(vehicle_performance),
            "date_range": f"{start_date} to {end_date}",
        }

        return render(request, "admin/transport_dashboard.html", context)

    def analytics_view(self, request):
        """Detailed analytics view"""
        context = {"title": "Transport Analytics", "message": "Advanced analytics would be implemented here"}
        return render(request, "admin/transport_analytics.html", context)


def bulk_verify_transporters(modeladmin, request, queryset):
    """Bulk verify transporters with validation"""
    verified_count = 0
    errors = []

    for transporter in queryset:
        try:
            if transporter.is_documents_expired():
                errors.append(f"{transporter.user.get_full_name()}: Documents expired")
            else:
                transporter.is_verified = True
                transporter.save()
                verified_count += 1
        except Exception as e:
            errors.append(f"{transporter.user.get_full_name()}: {str(e)}")

    if verified_count:
        messages.success(request, f"{verified_count} transporters verified successfully.")

    if errors:
        for error in errors[:5]:
            messages.error(request, error)
        if len(errors) > 5:
            messages.warning(request, f"... and {len(errors) - 5} more errors.")


bulk_verify_transporters.short_description = "Bulk verify transporters (with validation)"


def generate_performance_report(modeladmin, request, queryset):
    """Generate performance report for selected transporters"""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="transporter_performance_report.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Transporter",
            "Total Deliveries",
            "Successful",
            "Cancelled",
            "Success Rate",
            "Cancellation Rate",
            "Average Rating",
            "Total Earnings",
            "Status",
            "Last Active",
        ]
    )

    for transporter in queryset.select_related("user"):
        last_delivery = transporter.assigned_deliveries.order_by("-created_at").first()
        last_active = last_delivery.created_at if last_delivery else "Never"

        writer.writerow(
            [
                transporter.user.get_full_name(),
                transporter.total_deliveries,
                transporter.successful_deliveries,
                transporter.cancelled_deliveries,
                f"{transporter.success_rate:.1f}%",
                f"{transporter.cancellation_rate:.1f}%",
                f"{transporter.rating:.2f}/5.00",
                f"${transporter.earnings_total:.2f}",
                transporter.get_status_display(),
                last_active.strftime("%Y-%m-%d") if hasattr(last_active, "strftime") else last_active,
            ]
        )

    return response


generate_performance_report.short_description = "Generate performance report"


transport_admin_site = TransportAdminSite(name="transport_admin")
transport_admin_site.register(Transporter, TransporterAdmin)
transport_admin_site.register(Delivery, DeliveryAdmin)
transport_admin_site.register(DeliveryRoute, DeliveryRouteAdmin)
transport_admin_site.register(DeliveryTracking, DeliveryTrackingAdmin)
transport_admin_site.register(DeliveryRating, DeliveryRatingAdmin)

TransporterAdmin.actions.extend([bulk_verify_transporters, generate_performance_report])
