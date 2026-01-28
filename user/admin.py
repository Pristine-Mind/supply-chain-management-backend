from typing import Any, Optional, TypeVar, cast

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.models import User as AuthUser
from django.db import models
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.http import quote
from django.utils.translation import gettext_lazy as _

_ModelT = TypeVar("_ModelT", bound=models.Model)
_UserT = TypeVar("_UserT", bound=AuthUser)

from .admin_permissions import (
    RoleBasedModelAdminMixin,
    UserAdminMixin,
)
from .business_export import BusinessDataExporter
from .models import Contact, LoginAttempt, Role, UserProfile

User = get_user_model()

if admin.site.is_registered(AuthUser):
    admin.site.unregister(AuthUser)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "User Profile"
    fk_name = "user"
    readonly_fields = ("shop_id", "credit_used")
    fieldsets = (
        (None, {"fields": ("role", "phone_number", "business_type")}),
        (
            "Business Information",
            {
                "fields": (
                    "shop_id",
                    "has_access_to_marketplace",
                    "location",
                    "latitude",
                    "longitude",
                    "registered_business_name",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "B2B Business Settings",
            {
                "fields": (
                    "b2b_verified",
                    "credit_limit",
                    "credit_used",
                    "payment_terms_days",
                    "tax_id",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Documentation",
            {
                "fields": ("registration_certificate", "pan_certificate", "profile_image"),
                "classes": ("collapse",),
            },
        ),
        (
            "Payment Information",
            {
                "fields": ("payment_qr_payload", "payment_qr_image"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        return request.user.has_perm("user.change_user")

    def has_change_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        return request.user.has_perm("user.change_user")


class CustomUserAdmin(UserAdminMixin, BaseUserAdmin):
    """Admin for all users - Superuser only."""

    inlines = (UserProfileInline,)
    list_display = ("username", "email", "first_name", "last_name", "get_role", "is_staff", "is_active", "date_joined")
    list_select_related = ("user_profile",)
    list_filter = (("user_profile__role", admin.RelatedOnlyFieldListFilter), "is_staff", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (
            _("Permissions"),
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "email", "first_name", "last_name"),
            },
        ),
    )

    def get_role(self, instance: models.Model) -> str:
        """Get the role name for the user."""
        if hasattr(instance, "user_profile") and instance.user_profile.role:
            return instance.user_profile.role.name
        return "No Role"

    get_role.short_description: str = "Role"  # type: ignore

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = cast(QuerySet[Any], super().get_queryset(request))
        # Show all users
        return qs

    def has_view_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        """Only superusers can view this admin page."""
        return request.user.is_superuser


class GeneralUserAdmin(UserAdminMixin, BaseUserAdmin):
    """Admin for General Users only."""

    inlines = (UserProfileInline,)
    list_display = ("username", "email", "first_name", "last_name", "get_role", "is_active", "date_joined")
    list_select_related = ("user_profile",)
    list_filter = (("user_profile__role", admin.RelatedOnlyFieldListFilter), "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "email", "first_name", "last_name"),
            },
        ),
    )

    def get_role(self, instance: models.Model) -> str:
        """Get the role name for the user."""
        if hasattr(instance, "user_profile") and instance.user_profile.role:
            return instance.user_profile.role.name
        return "No Role"

    get_role.short_description: str = "Role"  # type: ignore

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = cast(QuerySet[Any], super().get_queryset(request))
        # Filter to show only general users (exclude business owners and business staff)
        qs = qs.exclude(user_profile__role__code__in=["business_owner", "business_staff"])

        if request.user.is_superuser:
            return qs

        if not hasattr(request.user, "user_profile") or not request.user.user_profile.role:
            return qs.none()

        user_role = request.user.user_profile.role.code

        if user_role in ["admin", "manager"]:
            return qs

        if user_role == "agent":
            return qs.filter(is_staff=False)

        return qs.filter(pk=request.user.pk)

    def has_change_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        """Only superusers can change users."""
        return request.user.is_superuser

    def has_delete_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        """Only superusers can delete users."""
        return request.user.is_superuser


class BusinessUserAdmin(UserAdminMixin, BaseUserAdmin):
    """Admin for Business Users only."""

    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "get_business_type",
        "get_shop_id",
        "get_b2b_status",
        "is_active",
        "date_joined",
    )
    list_select_related = ("user_profile",)
    list_filter = (
        "user_profile__business_type",
        "user_profile__b2b_verified",
        "is_active",
    )
    search_fields = ("username", "first_name", "last_name", "email", "user_profile__shop_id")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "email", "first_name", "last_name"),
            },
        ),
    )

    def get_business_type(self, instance: models.Model) -> str:
        """Get the business type for the user."""
        if hasattr(instance, "user_profile") and instance.user_profile.business_type:
            return instance.user_profile.get_business_type_display()
        return "N/A"

    get_business_type.short_description: str = "Business Type"  # type: ignore

    def get_b2b_status(self, instance: models.Model) -> str:
        """Get the B2B verification status."""
        if hasattr(instance, "user_profile") and instance.user_profile.b2b_verified:
            return "✓ Verified"
        return "✗ Not Verified"

    get_b2b_status.short_description: str = "B2B Status"  # type: ignore

    def get_shop_id(self, instance: models.Model) -> str:
        """Get the shop ID for the user."""
        if hasattr(instance, "user_profile") and instance.user_profile.shop_id:
            return instance.user_profile.shop_id
        return "N/A"

    get_shop_id.short_description: str = "Shop ID"  # type: ignore

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = cast(QuerySet[Any], super().get_queryset(request))
        # Filter to show only business users
        qs = qs.filter(user_profile__role__code__in=["business_owner", "business_staff"])

        if request.user.is_superuser:
            return qs

        if not hasattr(request.user, "user_profile") or not request.user.user_profile.role:
            return qs.none()

        user_role = request.user.user_profile.role.code

        if user_role in ["admin", "manager"]:
            return qs

        if user_role == "business_owner":
            return qs.filter(Q(userprofile__business_owner=request.user) | Q(pk=request.user.pk))

        if user_role == "business_staff":
            return qs.filter(pk=request.user.pk)

        return qs.filter(pk=request.user.pk)

    def has_change_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        """Only superusers can change users."""
        return request.user.is_superuser

    def has_delete_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        """Only superusers can delete users."""
        return request.user.is_superuser

    def export_business_data(self, request: HttpRequest, queryset: QuerySet[Any]) -> HttpResponse:
        """Export business user data to Excel with all associated data."""
        if queryset.count() == 0:
            messages.error(request, "Please select at least one business user to export.")
            return

        if queryset.count() > 1:
            messages.warning(request, "Exporting data for multiple users. Only the first user will be exported.")

        business_user = queryset.first()

        try:
            exporter = BusinessDataExporter(business_user)
            excel_file = exporter.generate_export()

            # Create response
            response = HttpResponse(
                excel_file.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            filename = f"Business_Data_{business_user.username}_{business_user.user_profile.shop_id}.xlsx"
            response["Content-Disposition"] = f'attachment; filename="{quote(filename)}"'

            messages.success(
                request,
                f"Successfully exported business data for {business_user.first_name or business_user.username}",
            )
            return response
        except Exception as e:
            messages.error(request, f"Error exporting data: {str(e)}")
            return None

    export_business_data.short_description = "📊 Export Business Data to Excel"
    actions = ["export_business_data"]


if admin.site.is_registered(User):
    admin.site.unregister(User)

admin.site.register(User, CustomUserAdmin)


class GeneralUserProxy(User):
    """Proxy model for General Users."""

    class Meta:
        proxy = True
        verbose_name = "General User"
        verbose_name_plural = "General Users"


admin.site.register(GeneralUserProxy, GeneralUserAdmin)


class BusinessUserProxy(User):
    """Proxy model for Business Users."""

    class Meta:
        proxy = True
        verbose_name = "Business User"
        verbose_name_plural = "Business Users"


admin.site.register(BusinessUserProxy, BusinessUserAdmin)


@admin.register(Role)
class RoleAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "level", "description")
    list_filter = ("level",)
    search_fields = ("name", "code", "description")
    ordering = ("level",)

    view_roles = ["admin", "manager"]
    add_roles = ["admin"]
    change_roles = ["admin", "manager"]
    delete_roles = ["admin"]


@admin.register(Contact)
class ContactAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("name", "email", "subject", "created_at")
    search_fields = ("name", "email", "subject", "message")
    list_filter = ("created_at",)
    readonly_fields = ("name", "email", "subject", "message", "created_at")

    view_roles = ["admin", "manager", "agent"]
    add_roles = []
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin", "manager"]

    def has_add_permission(self, request):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """
    Admin interface for monitoring login attempts and security.
    """

    list_display = ["timestamp", "ip_address", "username", "user", "attempt_type", "user_agent_short"]
    list_filter = [
        "attempt_type",
        "timestamp",
        ("timestamp", admin.DateFieldListFilter),
    ]
    search_fields = ["ip_address", "username", "user__username", "user_agent"]
    readonly_fields = ["timestamp", "ip_address", "username", "user", "attempt_type", "user_agent"]
    ordering = ["-timestamp"]
    list_per_page = 50

    def user_agent_short(self, obj):
        """Display shortened user agent string"""
        if obj.user_agent:
            return obj.user_agent[:100] + "..." if len(obj.user_agent) > 100 else obj.user_agent
        return "N/A"

    user_agent_short.short_description = "User Agent"

    def has_add_permission(self, request):
        """Prevent manual addition of login attempts"""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent editing of login attempts"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup purposes"""
        return request.user.is_superuser

    def get_queryset(self, request):
        """Optimize queryset with select_related for user"""
        return super().get_queryset(request).select_related("user")

    actions = ["delete_selected"]

    def delete_selected(self, request, queryset):
        """Custom delete action with confirmation"""
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Successfully deleted {count} login attempts.")

    delete_selected.short_description = "Delete selected login attempts"


admin.site.site_header = "Mulya Bazzar Admin"
admin.site.site_title = "Mulya Bazzar"
admin.site.index_title = "Dashboard"

admin.site.unregister(Group)
