from django.contrib import admin, messages
from django.db.models import Count
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    LoyaltyConfiguration,
    LoyaltyPerk,
    LoyaltyTier,
    LoyaltyTransaction,
    LoyaltyTransactionArchive,
    UserLoyalty,
)


@admin.register(LoyaltyConfiguration)
class LoyaltyConfigurationAdmin(admin.ModelAdmin):
    """Admin for loyalty system configuration."""

    list_display = [
        "points_per_unit",
        "unit_amount",
        "min_redemption_points",
        "max_redemption_points",
        "points_expiry_days",
        "updated_at",
    ]

    fieldsets = (
        (_("Points Earning"), {"fields": ("points_per_unit", "unit_amount")}),
        (_("Points Redemption"), {"fields": ("min_redemption_points", "max_redemption_points", "allow_negative_balance")}),
        (_("Points Expiry"), {"fields": ("points_expiry_days",)}),
    )

    def has_add_permission(self, request):
        # Only allow one configuration
        return not LoyaltyConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False


class LoyaltyPerkInline(admin.TabularInline):
    """Inline admin for perks within tiers."""

    model = LoyaltyPerk
    extra = 1
    fields = ["name", "description", "code", "is_active"]


@admin.register(LoyaltyTier)
class LoyaltyTierAdmin(admin.ModelAdmin):
    """Admin for loyalty tiers."""

    list_display = ["name", "min_points", "point_multiplier", "is_active", "perk_count", "user_count", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "description"]
    ordering = ["min_points"]
    inlines = [LoyaltyPerkInline]

    fieldsets = (
        (None, {"fields": ("name", "min_points", "point_multiplier", "description")}),
        (_("Status"), {"fields": ("is_active",)}),
    )

    def perk_count(self, obj):
        """Display number of perks in tier."""
        count = obj.perks.filter(is_active=True).count()
        return format_html("<strong>{}</strong>", count)

    perk_count.short_description = _("Active Perks")

    def user_count(self, obj):
        """Display number of users in tier."""
        count = obj.userloyalty_set.filter(is_active=True).count()
        return format_html("<strong>{}</strong>", count)

    user_count.short_description = _("Users")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_perk_count=Count("perks"), _user_count=Count("userloyalty"))


@admin.register(LoyaltyPerk)
class LoyaltyPerkAdmin(admin.ModelAdmin):
    """Admin for loyalty perks."""

    list_display = ["name", "tier", "code", "is_active", "created_at"]
    list_filter = ["tier", "is_active", "created_at"]
    search_fields = ["name", "description", "code"]
    prepopulated_fields = {"code": ("name",)}

    fieldsets = (
        (None, {"fields": ("tier", "name", "description", "code")}),
        (_("Status"), {"fields": ("is_active",)}),
    )


class LoyaltyTransactionInline(admin.TabularInline):
    """Inline admin for transactions."""

    model = LoyaltyTransaction
    extra = 0
    can_delete = False
    fields = ["created_at", "transaction_type", "points", "description", "balance_after"]
    readonly_fields = fields
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(UserLoyalty)
class UserLoyaltyAdmin(admin.ModelAdmin):
    """Admin for user loyalty profiles."""

    list_display = [
        "user",
        "current_points",
        "lifetime_points_display",
        "tier_display",
        "is_active",
        "transaction_count",
        "member_since",
    ]
    list_filter = ["tier", "is_active", "created_at", "tier_updated_at"]
    search_fields = ["user__username", "user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["points", "lifetime_points", "created_at", "updated_at", "tier_updated_at", "next_tier_info"]
    inlines = [LoyaltyTransactionInline]

    fieldsets = (
        (_("User Information"), {"fields": ("user",)}),
        (_("Points"), {"fields": ("points", "lifetime_points", "next_tier_info")}),
        (_("Tier"), {"fields": ("tier", "tier_updated_at")}),
        (_("Status"), {"fields": ("is_active",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = ["recalculate_tiers", "activate_profiles", "deactivate_profiles"]

    def current_points(self, obj):
        """Display current points with color."""
        color = "green" if obj.points > 0 else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.points)

    current_points.short_description = _("Current Points")
    current_points.admin_order_field = "points"

    def lifetime_points_display(self, obj):
        """Display lifetime points."""
        return format_html("<strong>{}</strong>", obj.lifetime_points)

    lifetime_points_display.short_description = _("Lifetime Points")
    lifetime_points_display.admin_order_field = "lifetime_points"

    def tier_display(self, obj):
        """Display tier with badge."""
        if obj.tier:
            return format_html(
                '<span style="background: #4CAF50; color: white; ' 'padding: 3px 8px; border-radius: 3px;">{}</span>',
                obj.tier.name,
            )
        return format_html(
            '<span style="background: #999; color: white; ' 'padding: 3px 8px; border-radius: 3px;">No Tier</span>'
        )

    tier_display.short_description = _("Tier")
    tier_display.admin_order_field = "tier"

    def transaction_count(self, obj):
        """Display transaction count."""
        count = obj.transactions.count()
        return format_html("<strong>{}</strong>", count)

    transaction_count.short_description = _("Transactions")

    def member_since(self, obj):
        """Display member since date."""
        return obj.created_at.strftime("%Y-%m-%d")

    member_since.short_description = _("Member Since")
    member_since.admin_order_field = "created_at"

    def next_tier_info(self, obj):
        """Display info about next tier."""
        points_needed = obj.get_points_to_next_tier()
        if points_needed is None:
            return _("Already at highest tier")
        elif points_needed == 0:
            return _("Eligible for tier upgrade!")
        else:
            return _(f"{points_needed} points needed for next tier")

    next_tier_info.short_description = _("Next Tier")

    def recalculate_tiers(self, request, queryset):
        """Action to recalculate tiers for selected users."""
        updated = 0
        for profile in queryset:
            if profile.update_tier():
                updated += 1

        self.message_user(request, _(f"Updated {updated} user tiers"), messages.SUCCESS)

    recalculate_tiers.short_description = _("Recalculate tiers")

    def activate_profiles(self, request, queryset):
        """Activate selected profiles."""
        count = queryset.update(is_active=True)
        self.message_user(request, _(f"Activated {count} profiles"), messages.SUCCESS)

    activate_profiles.short_description = _("Activate selected profiles")

    def deactivate_profiles(self, request, queryset):
        """Deactivate selected profiles."""
        count = queryset.update(is_active=False)
        self.message_user(request, _(f"Deactivated {count} profiles"), messages.SUCCESS)

    deactivate_profiles.short_description = _("Deactivate selected profiles")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "tier").annotate(_transaction_count=Count("transactions"))


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    """Admin for loyalty transactions."""

    list_display = [
        "id",
        "user_display",
        "points_display",
        "transaction_type",
        "description_short",
        "balance_after",
        "created_at",
    ]
    list_filter = ["transaction_type", "created_at"]
    search_fields = [
        "user_loyalty__user__username",
        "user_loyalty__user__email",
        "description",
        "purchase_id",
        "reference_id",
    ]
    readonly_fields = [
        "user_loyalty",
        "points",
        "transaction_type",
        "description",
        "created_at",
        "purchase_id",
        "reference_id",
        "metadata",
        "created_by",
        "balance_after",
    ]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = (
        (
            _("Transaction Details"),
            {"fields": ("user_loyalty", "points", "transaction_type", "description", "balance_after")},
        ),
        (_("References"), {"fields": ("purchase_id", "reference_id")}),
        (_("Metadata"), {"fields": ("metadata", "created_by", "created_at"), "classes": ("collapse",)}),
    )

    def user_display(self, obj):
        """Display username."""
        return obj.user_loyalty.user.username

    user_display.short_description = _("User")
    user_display.admin_order_field = "user_loyalty__user__username"

    def points_display(self, obj):
        """Display points with color coding."""
        color = "green" if obj.points > 0 else "red"
        return format_html('<span style="color: {}; font-weight: bold;">{:+d}</span>', color, obj.points)

    points_display.short_description = _("Points")
    points_display.admin_order_field = "points"

    def description_short(self, obj):
        """Truncate long descriptions."""
        if len(obj.description) > 50:
            return obj.description[:50] + "..."
        return obj.description

    description_short.short_description = _("Description")

    def has_add_permission(self, request):
        # Transactions should only be created via service layer
        return False

    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion for audit trail
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user_loyalty__user", "created_by")


@admin.register(LoyaltyTransactionArchive)
class LoyaltyTransactionArchiveAdmin(admin.ModelAdmin):
    """Admin for archived loyalty transactions."""

    list_display = ["username", "points", "transaction_type", "description", "created_at", "archived_at"]
    list_filter = ["transaction_type", "archived_at"]
    search_fields = ["username", "description", "reference_id"]
    readonly_fields = [
        "user_id",
        "username",
        "points",
        "transaction_type",
        "description",
        "created_at",
        "archived_at",
        "purchase_id",
        "reference_id",
        "metadata",
        "balance_after",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
