from functools import wraps

from django.contrib import admin
from django.core.exceptions import PermissionDenied


class RoleBasedAdminMixin:
    """
    Base mixin for role-based admin access.
    Requires the following attributes in child classes:
    - required_role: The role code required to access this admin
    - permission_required: Optional specific permission required
    """

    required_role = None
    permission_required = None

    ROLE_LEVELS = {"general_user": 1, "business_staff": 2, "business_owner": 3, "agent": 4, "manager": 5, "admin": 6}

    def _get_role_level(self, role_code):
        """Get the hierarchy level of a role"""
        return self.ROLE_LEVELS.get(role_code, 0)

    def _check_permission(self, request):
        """Check if user has the required role or permission"""
        # Grant full access to superusers and staff users
        if request.user.is_staff or request.user.is_superuser:
            return True

        if not hasattr(request.user, "user_profile"):
            return False

        user_profile = request.user.user_profile

        if self.required_role:
            required_level = self._get_role_level(self.required_role)
            user_level = self._get_role_level(user_profile.role.code if user_profile.role else "")
            if user_level < required_level:
                return False

        if self.permission_required and not user_profile.has_perm(self.permission_required):
            return False

        return True

    def has_module_permission(self, request):
        """Check if user has permission to view the module"""
        return self._check_permission(request)

    def has_view_permission(self, request, obj=None):
        has_perm = self._check_permission(request)
        if not has_perm:
            return False
        parent_has_perm = getattr(super(), "has_view_permission", lambda r, o: True)
        return parent_has_perm(request, obj)

    def has_add_permission(self, request):
        has_perm = self._check_permission(request)
        if not has_perm:
            return False
        parent_has_perm = getattr(super(), "has_add_permission", lambda r: True)
        return parent_has_perm(request)

    def has_change_permission(self, request, obj=None):
        has_perm = self._check_permission(request)
        if not has_perm:
            return False
        parent_has_perm = getattr(super(), "has_change_permission", lambda r, o: True)
        return parent_has_perm(request, obj)

    def has_delete_permission(self, request, obj=None):
        has_perm = self._check_permission(request)
        if not has_perm:
            return False
        parent_has_perm = getattr(super(), "has_delete_permission", lambda r, o: True)
        return parent_has_perm(request, obj)

    def get_queryset(self, request):
        """
        Filter queryset based on user's access level:
        - Superusers and staff: see all records
        - Users with profile and role: filter based on their role and shop
        - Others: see nothing
        """
        qs = super().get_queryset(request)

        # Staff and superusers can see everything
        if request.user.is_staff or request.user.is_superuser:
            return qs

        # If user has no profile or role, they can't see anything
        if not hasattr(request.user, "user_profile") or not request.user.user_profile.role:
            return qs.none()

        user_role = request.user.user_profile.role.code
        user_shop_id = getattr(request.user.user_profile, "shop_id", None)

        # Agents and admins can see all records
        if user_role in ["agent", "admin"]:
            return qs

        # For business owners and staff, filter by shop_id if model has it
        if user_role in ["business_owner", "business_staff"] and hasattr(qs.model, "shop_id"):
            if user_shop_id:
                return qs.filter(shop_id=user_shop_id)
            return qs.none()  # No shop_id means they shouldn't see any shop data

        # For general users, only show their own records
        if hasattr(qs.model, "user"):
            qs = qs.filter(user=request.user)

        return qs

    def save_model(self, request, obj, form, change):
        """
        Set the user and shop_id when creating a new object.
        """
        if not change and hasattr(obj, "user"):
            obj.user = request.user

        # Set shop_id from user's profile if the model has a shop_id field
        if hasattr(obj, "shop_id") and not obj.shop_id:
            user_shop_id = getattr(request.user.user_profile, "shop_id", None)
            if user_shop_id:
                obj.shop_id = user_shop_id

        # Only call parent's save_model if it exists
        parent_save = getattr(super(), "save_model", None)
        if parent_save and callable(parent_save):
            parent_save(request, obj, form, change)
        else:
            # Fallback to default save behavior
            _ = obj.save()  # Assign to _ to indicate we're intentionally ignoring the return value


class GeneralUserAdminMixin(RoleBasedAdminMixin):
    """Mixin for General User level access"""

    required_role = "general_user"


class BusinessStaffAdminMixin(RoleBasedAdminMixin):
    """Mixin for Business Staff level access"""

    required_role = "business_staff"


class BusinessOwnerAdminMixin(BusinessStaffAdminMixin):
    """Mixin for Business Owner level access (inherits from Business Staff)"""

    required_role = "business_owner"


class AgentAdminMixin(BusinessOwnerAdminMixin):
    """Mixin for Platform Agent level access (inherits from Business Owner)"""

    required_role = "agent"


class ManagerAdminMixin(AgentAdminMixin):
    """Mixin for Manager level access (inherits from Agent)"""

    required_role = "manager"


class AdminAdminMixin(ManagerAdminMixin):
    """Mixin for Admin level access (inherits from Manager)"""

    required_role = "admin"


class TransporterAdminMixin(AgentAdminMixin):
    """Mixin for Transporter level access (inherits from Agent)"""

    required_role = "transporter"


def role_required(role_codes, raise_exception=False):
    """
    Decorator for function-based views to check user role.

    Args:
        role_codes (str|list): Single role code or list of role codes
        raise_exception (bool): If True, raises PermissionDenied instead of returning False
    """
    if isinstance(role_codes, str):
        role_codes = [role_codes]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not hasattr(request.user, "userprofile"):
                if raise_exception:
                    raise PermissionDenied
                return False

            user_profile = request.user.userprofile

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            has_access = any(user_profile.has_role_or_above(role) for role in role_codes)

            if not has_access and raise_exception:
                raise PermissionDenied("You don't have permission to access this page.")

            if has_access:
                return view_func(request, *args, **kwargs)

            return False

        return _wrapped_view

    return decorator
