from typing import Any, Optional, Type, TypeVar, cast

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.models import User as AuthUser
from django.db import models
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

_ModelT = TypeVar("_ModelT", bound=models.Model)
_UserT = TypeVar("_UserT", bound=AuthUser)

from .admin_permissions import (
    RoleBasedModelAdminMixin,
    UserAdminMixin,
)
from .models import Contact, Role, UserProfile

User = get_user_model()

if admin.site.is_registered(AuthUser):
    admin.site.unregister(AuthUser)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "User Profile"
    fk_name = "user"
    readonly_fields = ("shop_id",)
    fieldsets = (
        (None, {"fields": ("role", "phone_number", "business_type")}),
        (
            "Business Information",
            {
                "fields": ("shop_id", "has_access_to_marketplace", "location", "latitude", "longitude"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        return request.user.has_perm("user.change_user")

    def has_change_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        return request.user.has_perm("user.change_user")


@admin.register(User)
class CustomUserAdmin(UserAdminMixin, BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_active", "get_role", "date_joined")
    list_select_related = ("user_profile",)
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
    )
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

        if request.user.is_superuser:
            return qs

        if not hasattr(request.user, "user_profile") or not request.user.user_profile.role:
            return qs.none()

        user_role = request.user.user_profile.role.code

        if user_role in ["admin", "manager"]:
            return qs

        if user_role == "agent":
            return qs.filter(is_staff=False)

        if user_role == "business_owner":
            return qs.filter(Q(userprofile__business_owner=request.user) | Q(pk=request.user.pk))

        if user_role == "business_staff":
            return qs.filter(pk=request.user.pk)

        return qs.filter(pk=request.user.pk)


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


admin.site.site_header = "Supply Chain Management Admin"
admin.site.site_title = "Supply Chain Management"
admin.site.index_title = "Dashboard"

admin.site.unregister(Group)
