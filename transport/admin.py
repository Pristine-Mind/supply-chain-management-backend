from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Delivery,
    DeliveryPriority,
    DeliveryRating,
    DeliveryTracking,
    Transporter,
    TransportStatus,
)


class DeliveryTrackingInline(admin.TabularInline):
    """Inline admin for delivery tracking updates"""

    model = DeliveryTracking
    extra = 0
    readonly_fields = ["timestamp"]
    fields = ["status", "latitude", "longitude", "notes", "timestamp"]
    ordering = ["-timestamp"]


class DeliveryRatingInline(admin.TabularInline):
    """Inline admin for delivery ratings"""

    model = DeliveryRating
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["rated_by", "rating", "comment", "created_at"]


@admin.register(Transporter)
class TransporterAdmin(admin.ModelAdmin):
    """Admin interface for Transporter model"""

    list_display = [
        "user_full_name",
        "license_number",
        "vehicle_type",
        "vehicle_capacity",
        "rating",
        "total_deliveries",
        "success_rate_display",
        "is_available",
        "is_verified",
    ]
    list_filter = ["vehicle_type", "is_available", "is_verified", "created_at", "rating"]
    search_fields = ["user__first_name", "user__last_name", "user__email", "license_number", "vehicle_number", "phone"]
    readonly_fields = [
        "rating",
        "total_deliveries",
        "successful_deliveries",
        "success_rate_display",
        "created_at",
        "updated_at",
        "current_location_display",
    ]
    fieldsets = (
        ("User Information", {"fields": ("user", "phone")}),
        (
            "License & Vehicle",
            {
                "fields": (
                    "license_number",
                    "vehicle_type",
                    "vehicle_number",
                    "vehicle_capacity",
                    "vehicle_image",
                    "vehicle_documents",
                )
            },
        ),
        (
            "Location & Availability",
            {"fields": ("current_location_display", "is_available", "current_latitude", "current_longitude")},
        ),
        ("Performance Metrics", {"fields": ("rating", "total_deliveries", "successful_deliveries", "success_rate_display")}),
        ("Account Status", {"fields": ("is_verified",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = ["verify_transporters", "unverify_transporters", "export_transporter_data"]

    def user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    user_full_name.short_description = "Full Name"
    user_full_name.admin_order_field = "user__first_name"

    def success_rate_display(self, obj):
        rate = obj.success_rate
        if rate >= 95:
            color = "green"
        elif rate >= 85:
            color = "orange"
        else:
            color = "red"
        return format_html('<span style="color: {};">{:.1}%</span>', color, rate)

    success_rate_display.short_description = "Success Rate"
    success_rate_display.admin_order_field = "successful_deliveries"

    def current_location_display(self, obj):
        if obj.current_latitude and obj.current_longitude:
            maps_url = f"https://maps.google.com/?q={obj.current_latitude},{obj.current_longitude}"
            return format_html(
                '<a href="{}" target="_blank">View on Map</a><br>' "Lat: {:.6f}, Lng: {:.6f}",
                maps_url,
                obj.current_latitude,
                obj.current_longitude,
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

    def export_transporter_data(self, request, queryset):
        # This would typically generate a CSV/Excel file
        self.message_user(request, f"Export functionality would be implemented here for {queryset.count()} transporters.")

    export_transporter_data.short_description = "Export transporter data"


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    """Admin interface for Delivery model"""

    list_display = [
        "delivery_id_short",
        "order_number",
        "status_colored",
        "priority_colored",
        "transporter_name",
        "package_weight",
        "delivery_fee",
        "requested_pickup_date",
        "delivered_at",
    ]
    list_filter = ["status", "priority", "requested_pickup_date", "created_at", "transporter__vehicle_type"]
    search_fields = [
        "delivery_id",
        # "marketplace_sale__order_number",
        "pickup_address",
        "delivery_address",
        "transporter__user__first_name",
        "transporter__user__last_name",
    ]
    readonly_fields = [
        "delivery_id",
        # "marketplace_sale",
        "created_at",
        "updated_at",
        "assigned_at",
        "picked_up_at",
        "delivered_at",
        "pickup_location_display",
        "delivery_location_display",
        "delivery_timeline",
    ]

    fieldsets = (
        ("Basic Information", {"fields": ("delivery_id", "status", "priority")}),
        (
            "Pickup Details",
            {
                "fields": (
                    "pickup_address",
                    "pickup_location_display",
                    "pickup_contact_name",
                    "pickup_contact_phone",
                    "requested_pickup_date",
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
                    "requested_delivery_date",
                )
            },
        ),
        ("Package Information", {"fields": ("package_weight", "package_dimensions", "special_instructions")}),
        ("Transport Assignment", {"fields": ("transporter",)}),
        ("Pricing & Distance", {"fields": ("delivery_fee", "distance_km", "estimated_delivery_time")}),
        (
            "Timeline",
            {"fields": ("delivery_timeline", "assigned_at", "picked_up_at", "delivered_at"), "classes": ("collapse",)},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    inlines = [DeliveryTrackingInline, DeliveryRatingInline]
    actions = ["assign_to_transporter", "mark_as_urgent", "export_delivery_data"]

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
            TransportStatus.AVAILABLE: "#28a745",  # Green
            TransportStatus.ASSIGNED: "#ffc107",  # Yellow
            TransportStatus.PICKED_UP: "#17a2b8",  # Cyan
            TransportStatus.IN_TRANSIT: "#007bff",  # Blue
            TransportStatus.DELIVERED: "#28a745",  # Green
            TransportStatus.CANCELLED: "#dc3545",  # Red
            TransportStatus.RETURNED: "#6c757d",  # Gray
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"
    status_colored.admin_order_field = "status"

    def priority_colored(self, obj):
        colors = {
            DeliveryPriority.LOW: "#6c757d",  # Gray
            DeliveryPriority.NORMAL: "#28a745",  # Green
            DeliveryPriority.HIGH: "#ffc107",  # Yellow
            DeliveryPriority.URGENT: "#dc3545",  # Red
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

        if timeline:
            return mark_safe("<br>".join(timeline))
        return "No timeline data"

    delivery_timeline.short_description = "Delivery Timeline"

    def assign_to_transporter(self, request, queryset):
        # This would open a form to select transporter
        self.message_user(request, f"Assign functionality would be implemented for {queryset.count()} deliveries.")

    assign_to_transporter.short_description = "Assign to transporter"

    def mark_as_urgent(self, request, queryset):
        updated = queryset.update(priority=DeliveryPriority.URGENT)
        self.message_user(request, f"{updated} deliveries marked as urgent.")

    mark_as_urgent.short_description = "Mark as urgent"

    def export_delivery_data(self, request, queryset):
        self.message_user(request, f"Export functionality would be implemented for {queryset.count()} deliveries.")

    export_delivery_data.short_description = "Export delivery data"


@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    """Admin interface for DeliveryTracking model"""

    list_display = ["delivery_id_short", "status_colored", "timestamp", "location_display", "notes_short"]
    list_filter = ["status", "timestamp"]
    search_fields = ["delivery__delivery_id", "notes"]
    readonly_fields = ["timestamp"]

    def delivery_id_short(self, obj):
        return str(obj.delivery.delivery_id)[:8] + "..."

    delivery_id_short.short_description = "Delivery ID"
    delivery_id_short.admin_order_field = "delivery__delivery_id"

    def status_colored(self, obj):
        colors = {
            TransportStatus.AVAILABLE: "#28a745",
            TransportStatus.ASSIGNED: "#ffc107",
            TransportStatus.PICKED_UP: "#17a2b8",
            TransportStatus.IN_TRANSIT: "#007bff",
            TransportStatus.DELIVERED: "#28a745",
            TransportStatus.CANCELLED: "#dc3545",
            TransportStatus.RETURNED: "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"
    status_colored.admin_order_field = "status"

    def location_display(self, obj):
        if obj.latitude and obj.longitude:
            return f"{obj.latitude:.4f}, {obj.longitude:.4f}"
        return "-"

    location_display.short_description = "Location"

    def notes_short(self, obj):
        if obj.notes:
            return obj.notes[:50] + "..." if len(obj.notes) > 50 else obj.notes
        return "-"

    notes_short.short_description = "Notes"


@admin.register(DeliveryRating)
class DeliveryRatingAdmin(admin.ModelAdmin):
    """Admin interface for DeliveryRating model"""

    list_display = ["delivery_id_short", "transporter_name", "rated_by_name", "rating_stars", "comment_short", "created_at"]
    list_filter = ["rating", "created_at"]
    search_fields = ["delivery__delivery_id", "transporter__user__first_name", "rated_by__first_name", "comment"]
    readonly_fields = ["created_at"]

    def delivery_id_short(self, obj):
        return str(obj.delivery.delivery_id)[:8] + "..."

    delivery_id_short.short_description = "Delivery ID"
    delivery_id_short.admin_order_field = "delivery__delivery_id"

    def transporter_name(self, obj):
        return obj.transporter.user.get_full_name()

    transporter_name.short_description = "Transporter"
    transporter_name.admin_order_field = "transporter__user__first_name"

    def rated_by_name(self, obj):
        return obj.rated_by.get_full_name()

    rated_by_name.short_description = "Rated By"
    rated_by_name.admin_order_field = "rated_by__first_name"

    def rating_stars(self, obj):
        stars = "★" * obj.rating + "☆" * (5 - obj.rating)
        return format_html('<span style="color: gold;">{}</span>', stars)

    rating_stars.short_description = "Rating"
    rating_stars.admin_order_field = "rating"

    def comment_short(self, obj):
        if obj.comment:
            return obj.comment[:100] + "..." if len(obj.comment) > 100 else obj.comment
        return "-"

    comment_short.short_description = "Comment"


# Custom admin site configuration
class TransportAdminSite(admin.AdminSite):
    """Custom admin site for transport management"""

    site_header = "Transport Management System"
    site_title = "Transport Admin"
    index_title = "Transport Dashboard"

    def index(self, request, extra_context=None):
        """Custom admin index with statistics"""
        extra_context = extra_context or {}

        # Calculate statistics
        total_deliveries = Delivery.objects.count()
        pending_deliveries = Delivery.objects.filter(status=TransportStatus.AVAILABLE).count()
        active_deliveries = Delivery.objects.filter(
            status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
        ).count()
        completed_deliveries = Delivery.objects.filter(status=TransportStatus.DELIVERED).count()

        total_transporters = Transporter.objects.count()
        active_transporters = Transporter.objects.filter(is_available=True).count()
        verified_transporters = Transporter.objects.filter(is_verified=True).count()

        # Recent activity
        recent_deliveries = Delivery.objects.select_related("transporter__user", "marketplace_sale").order_by("-created_at")[
            :5
        ]

        extra_context.update(
            {
                "transport_stats": {
                    "total_deliveries": total_deliveries,
                    "pending_deliveries": pending_deliveries,
                    "active_deliveries": active_deliveries,
                    "completed_deliveries": completed_deliveries,
                    "total_transporters": total_transporters,
                    "active_transporters": active_transporters,
                    "verified_transporters": verified_transporters,
                },
                "recent_deliveries": recent_deliveries,
            }
        )

        return super().index(request, extra_context)


# Register models with custom admin site
transport_admin_site = TransportAdminSite(name="transport_admin")
transport_admin_site.register(Transporter, TransporterAdmin)
transport_admin_site.register(Delivery, DeliveryAdmin)
transport_admin_site.register(DeliveryTracking, DeliveryTrackingAdmin)
transport_admin_site.register(DeliveryRating, DeliveryRatingAdmin)
