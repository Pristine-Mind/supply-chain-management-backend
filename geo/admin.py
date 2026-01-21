from django.contrib import admin
from django.utils.html import format_html

from .models import GeographicZone, SaleRegion, UserLocationSnapshot


@admin.register(GeographicZone)
class GeographicZoneAdmin(admin.ModelAdmin):
    """Admin for geographic zones"""

    list_display = [
        "name",
        "tier_badge",
        "shipping_cost",
        "estimated_delivery_days",
        "user_count",
        "is_active_badge",
        "created_at",
    ]

    list_filter = [
        "tier",
        "is_active",
        "created_at",
    ]

    search_fields = ["name", "description"]

    readonly_fields = [
        "created_at",
        "updated_at",
        "geometry_info",
    ]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "is_active")}),
        (
            "Geometry - Polygon Based",
            {
                "fields": ("geometry",),
                "classes": ("collapse",),
                "description": "Define zone using geographic polygon (PostGIS geometry)",
            },
        ),
        (
            "Geometry - Circle Based",
            {
                "fields": (
                    "center_latitude",
                    "center_longitude",
                    "radius_km",
                ),
                "classes": ("collapse",),
                "description": "Define zone using center point and radius",
            },
        ),
        (
            "Delivery Configuration",
            {
                "fields": (
                    "tier",
                    "shipping_cost",
                    "estimated_delivery_days",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "geometry_info"),
                "classes": ("collapse",),
            },
        ),
    )

    ordering = ["tier", "name"]
    date_hierarchy = "created_at"

    def tier_badge(self, obj):
        """Display tier with color"""
        colors = {
            "tier1": "#28a745",  # green
            "tier2": "#17a2b8",  # blue
            "tier3": "#ffc107",  # yellow
            "tier4": "#dc3545",  # red
        }
        color = colors.get(obj.tier, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_tier_display(),
        )

    tier_badge.short_description = "Tier"

    def user_count(self, obj):
        """Show number of users in this zone"""
        count = obj.user_snapshots.values("user").distinct().count()
        return format_html('<strong style="color: #0066cc;">{}</strong>', count)

    user_count.short_description = "Users in Zone"

    def is_active_badge(self, obj):
        """Display active status with badge"""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #28a745; color: white; '
                'padding: 3px 8px; border-radius: 3px;">Active</span>'
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; ' 'padding: 3px 8px; border-radius: 3px;">Inactive</span>'
        )

    is_active_badge.short_description = "Status"

    def geometry_info(self, obj):
        """Show geometry information"""
        if obj.geometry:
            geom_type = obj.geometry.geom_type
            coords = str(obj.geometry.extent)[:100]
            return format_html("<p><strong>Type:</strong> {}<br><strong>Extent:</strong> {}</p>", geom_type, coords)
        elif obj.center_latitude and obj.center_longitude:
            return format_html(
                "<p><strong>Circle:</strong> Center ({}, {}), Radius {}km</p>",
                obj.center_latitude,
                obj.center_longitude,
                obj.radius_km,
            )
        return "No geometry defined"

    geometry_info.short_description = "Geometry Information"


@admin.register(SaleRegion)
class SaleRegionAdmin(admin.ModelAdmin):
    """Admin for sale regions"""

    list_display = [
        "name",
        "zone",
        "restricted_badge",
        "country_count",
        "city_count",
        "is_active_badge",
        "created_at",
    ]

    list_filter = [
        "is_restricted",
        "is_active",
        "zone__tier",
        "created_at",
    ]

    search_fields = ["name", "zone__name"]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "zone", "is_active")}),
        (
            "Restrictions",
            {
                "fields": (
                    "is_restricted",
                    "allowed_countries",
                    "allowed_cities",
                ),
                "description": "If is_restricted is True, only specified countries/cities can purchase",
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at",),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ["created_at"]

    def restricted_badge(self, obj):
        """Show restriction status"""
        if obj.is_restricted:
            return format_html(
                '<span style="background-color: #dc3545; color: white; '
                'padding: 3px 8px; border-radius: 3px;">Restricted</span>'
            )
        return format_html(
            '<span style="background-color: #28a745; color: white; ' 'padding: 3px 8px; border-radius: 3px;">Open</span>'
        )

    restricted_badge.short_description = "Status"

    def country_count(self, obj):
        """Count allowed countries"""
        return len(obj.allowed_countries) if obj.allowed_countries else 0

    country_count.short_description = "Countries"

    def city_count(self, obj):
        """Count allowed cities"""
        return len(obj.allowed_cities) if obj.allowed_cities else 0

    city_count.short_description = "Cities"

    def is_active_badge(self, obj):
        """Show active status"""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #28a745; color: white; '
                'padding: 3px 8px; border-radius: 3px;">Active</span>'
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; ' 'padding: 3px 8px; border-radius: 3px;">Inactive</span>'
        )

    is_active_badge.short_description = "Status"


@admin.register(UserLocationSnapshot)
class UserLocationSnapshotAdmin(admin.ModelAdmin):
    """Admin for user location snapshots"""

    list_display = [
        "user",
        "zone",
        "accuracy_meters",
        "session_info",
        "created_at",
    ]

    list_filter = [
        "zone",
        "accuracy_meters",
        "created_at",
    ]

    search_fields = [
        "user__username",
        "user__email",
        "session_id",
    ]

    readonly_fields = [
        "user",
        "latitude",
        "longitude",
        "geo_point",
        "zone",
        "created_at",
    ]

    fieldsets = (
        ("User Information", {"fields": ("user", "session_id")}),
        (
            "Location Data",
            {
                "fields": (
                    "latitude",
                    "longitude",
                    "geo_point",
                    "zone",
                    "accuracy_meters",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at",),
                "classes": ("collapse",),
            },
        ),
    )

    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    def session_info(self, obj):
        """Show session info"""
        if obj.session_id:
            return format_html('<code style="background-color: #f0f0f0; padding: 2px 5px;">{}</code>', obj.session_id[:20])
        return "-"

    session_info.short_description = "Session ID"

    def has_add_permission(self, request):
        """Prevent manual creation of snapshots"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only allow staff to delete"""
        return request.user.is_staff
