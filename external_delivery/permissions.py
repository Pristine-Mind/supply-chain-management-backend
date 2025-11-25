from rest_framework.permissions import BasePermission

from .models import ExternalBusinessStatus


class IsExternalBusinessOwner(BasePermission):
    """
    Permission to check if the request is from the owner of external business
    """

    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        # Check if request has external_business attribute (set by middleware)
        if not hasattr(request, "external_business"):
            return False

        # Check if external business is approved and active
        return request.external_business.status == ExternalBusinessStatus.APPROVED and request.external_business.is_active()

    def has_object_permission(self, request, view, obj):
        # Check if the object belongs to the external business
        if hasattr(obj, "external_business"):
            return obj.external_business == request.external_business

        # For objects that don't have external_business field
        return True


class IsInternalStaff(BasePermission):
    """
    Permission for internal staff members only
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class CanManageExternalDeliveries(BasePermission):
    """
    Permission for users who can manage external deliveries
    (Internal staff or transport users)
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Staff users can always manage
        if request.user.is_staff:
            return True

        # Check if user is a transporter
        # This would depend on your user model structure
        # Assuming you have a way to identify transporters
        return hasattr(request.user, "is_transporter") and request.user.is_transporter


class CanAccessBusinessData(BasePermission):
    """
    Permission for accessing business-specific data
    """

    def has_permission(self, request, view):
        # Internal staff can access all business data
        if request.user and request.user.is_staff:
            return True

        # External business can only access their own data
        return hasattr(request, "external_business")

    def has_object_permission(self, request, view, obj):
        # Staff can access any object
        if request.user and request.user.is_staff:
            return True

        # External business can only access their own objects
        if hasattr(request, "external_business") and hasattr(obj, "external_business"):
            return obj.external_business == request.external_business

        return False
