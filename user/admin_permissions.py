from typing import Any, Optional, Type, TypeVar, Union, cast

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User as AuthUser
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

_ModelT = TypeVar("_ModelT", bound=Model)
_User = get_user_model()


class _UserProfileMixin:
    userprofile: Any


class RoleBasedModelAdminMixin(admin.ModelAdmin):
    """Base mixin for role-based model admin permissions"""

    view_roles: list[str] = ["admin", "manager", "agent", "business_owner", "business_staff"]
    add_roles: list[str] = ["admin", "manager", "agent", "business_owner"]
    change_roles: list[str] = ["admin", "manager", "agent", "business_owner", "business_staff"]
    delete_roles: list[str] = ["admin", "manager", "business_owner"]

    model: Type[Model] = Model

    def has_module_permission(self, request: HttpRequest) -> bool:
        """Check if user has permission to view the module"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        if not hasattr(request.user, "userprofile") or not request.user.userprofile.role:
            return False

        return request.user.userprofile.role.code in self.view_roles

    def has_view_permission(self, request: HttpRequest, obj: Optional[Model] = None) -> bool:
        """Check if user has permission to view the model"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        if not hasattr(request.user, "userprofile") or not request.user.userprofile.role:
            return False

        return request.user.userprofile.role.code in self.view_roles

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Check if user has permission to add a new instance"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        if not hasattr(request.user, "userprofile") or not request.user.userprofile.role:
            return False

        return request.user.userprofile.role.code in self.add_roles

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = None) -> bool:
        """Check if user has permission to change an instance"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        if not hasattr(request.user, "userprofile") or not request.user.userprofile.role:
            return False

        return request.user.userprofile.role.code in self.change_roles

    def has_delete_permission(self, request: HttpRequest, obj: Optional[Model] = None) -> bool:
        """Check if user has permission to delete an instance"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        if not hasattr(request.user, "userprofile") or not request.user.userprofile.role:
            return False

        return request.user.userprofile.role.code in self.delete_roles

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        """Filter queryset based on user's role"""
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        if not hasattr(request.user, "userprofile") or not request.user.userprofile.role:
            return qs.none()

        role_code = request.user.userprofile.role.code

        if role_code == "business_owner":
            if hasattr(self.model, "user"):
                return qs.filter(user=request.user)  # type: ignore

        elif role_code == "business_staff":
            if hasattr(self.model, "user"):
                return qs.filter(user=request.user)  # type: ignore

        return qs


class PurchaseAdminMixin(RoleBasedModelAdminMixin):
    """Permissions for Purchase model"""

    view_roles: list[str] = ["admin", "manager", "agent", "business_owner", "business_staff"]
    add_roles: list[str] = ["admin", "manager", "agent"]
    change_roles: list[str] = ["admin", "manager", "agent"]
    delete_roles: list[str] = ["admin", "manager"]


class PaymentAdminMixin(RoleBasedModelAdminMixin):
    """Permissions for Payment model"""

    view_roles: list[str] = ["admin", "manager", "agent", "business_owner"]
    add_roles: list[str] = ["admin", "manager", "agent"]
    change_roles: list[str] = ["admin", "manager", "agent"]
    delete_roles: list[str] = ["admin", "manager"]


class MarketplaceProductAdminMixin(RoleBasedModelAdminMixin):
    """Permissions for MarketplaceProduct model"""

    view_roles: list[str] = ["admin", "manager", "agent", "business_owner", "business_staff"]
    add_roles: list[str] = ["admin", "manager", "agent", "business_owner"]
    change_roles: list[str] = ["admin", "manager", "agent", "business_owner", "business_staff"]
    delete_roles: list[str] = ["admin", "manager", "business_owner"]


class UserAdminMixin(RoleBasedModelAdminMixin):
    """Permissions for User model"""

    view_roles: list[str] = ["admin", "manager", "agent"]
    add_roles: list[str] = ["admin", "manager"]
    change_roles: list[str] = ["admin", "manager", "agent"]
    delete_roles: list[str] = ["admin"]


class SettingsAdminMixin(RoleBasedModelAdminMixin):
    """Permissions for system settings"""

    view_roles: list[str] = ["admin", "manager"]
    add_roles: list[str] = ["admin"]
    change_roles: list[str] = ["admin", "manager"]
    delete_roles: list[str] = ["admin"]
