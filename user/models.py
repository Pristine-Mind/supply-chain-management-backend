import uuid

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.db import models
from django.utils.translation import gettext_lazy as _

from producer.models import City


class Role(models.Model):
    """
    Role model to define different user roles and their permissions.
    """

    name = models.CharField(max_length=50, unique=True, verbose_name=_("Role Name"))
    code = models.SlugField(max_length=20, unique=True, verbose_name=_("Role Code"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    level = models.PositiveIntegerField(default=0, help_text=_("Hierarchy level (higher number means higher privileges)"))
    permissions = models.ManyToManyField(
        Permission, blank=True, verbose_name=_("Permissions"), help_text=_("Specific permissions for this role")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["level"]
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")

    def __str__(self):
        return self.name

    @classmethod
    def get_default_role(cls):
        """Get or create the default business staff role"""
        return cls.get_or_create_role(
            code="business_staff",
            name="Business Staff",
            level=1,
            description="Basic access level for business employees with limited permissions.",
        )

    @classmethod
    def get_or_create_role(cls, code, name, level, description):
        """Helper method to get or create a role"""
        return cls.objects.get_or_create(code=code, defaults={"name": name, "level": level, "description": description})[0]

    @classmethod
    def setup_default_roles(cls):
        """
        Create default roles if they don't exist.
        Roles are ordered by permission level (higher number = more permissions).
        """
        # General User (lowest level, basic access)
        general_user = cls.get_or_create_role(
            code="general_user", name="General User", level=1, description="End users with basic access to the platform."
        )

        # Business Roles
        business_staff = cls.get_or_create_role(
            code="business_staff",
            name="Business Staff",
            level=2,
            description="Business employees with standard access to business features.",
        )

        business_owner = cls.get_or_create_role(
            code="business_owner",
            name="Business Owner",
            level=3,
            description="Owners of distributor/retailer businesses with full business access.",
        )

        # Platform Roles
        agent = cls.get_or_create_role(
            code="agent",
            name="Platform Agent",
            level=4,
            description="Platform representatives who manage users and operations.",
        )

        manager = cls.get_or_create_role(
            code="manager", name="Manager", level=5, description="System managers with elevated permissions and oversight."
        )

        admin = cls.get_or_create_role(
            code="admin", name="Administrator", level=6, description="Full system administrators with all permissions."
        )

        return {
            "general_user": general_user,
            "business_staff": business_staff,
            "business_owner": business_owner,
            "agent": agent,
            "manager": manager,
            "admin": admin,
        }


class UserProfile(models.Model):
    """
    UserProfile model to store additional user information.

    Fields:
    - user: One-to-one relationship with the User model.
    - role: ForeignKey to Role model.
    - phone_number: Phone number of the user.
    - shop_id: Unique UUID for the shop.
    - has_access_to_marketplace: Flag for marketplace access.
    - location: ForeignKey to City.
    - latitude, longitude: Geolocation of the shop.
    - business_type: Whether the shop is a distributor or retailer.
    """

    class BusinessType(models.TextChoices):
        DISTRIBUTOR = "distributor", _("Distributor")
        RETAILER = "retailer", _("Retailer")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_profile", verbose_name=_("User"))
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="user_profiles", default=Role.get_default_role, verbose_name=_("Role")
    )
    phone_number = models.CharField(max_length=15, null=True, blank=True, verbose_name=_("Phone Number"))
    shop_id = models.UUIDField(null=True, blank=True, editable=False, unique=True, verbose_name=_("Shop ID"))
    has_access_to_marketplace = models.BooleanField(default=False, verbose_name=_("Has Access to Marketplace"))
    location = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        verbose_name=_("Location"),
        help_text=_("Location of the shop"),
        null=True,
        blank=True,
    )
    latitude = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Latitude"),
        help_text=_("Geo-coordinate: latitude"),
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Longitude"),
        help_text=_("Geo-coordinate: longitude"),
    )
    business_type = models.CharField(
        max_length=12,
        choices=BusinessType.choices,
        default=BusinessType.RETAILER,
        verbose_name=_("Business Type"),
    )

    def save(self, *args, **kwargs):
        # Only set shop_id for business owners
        if self.role and self.role.code == "business_owner" and not self.shop_id:
            self.shop_id = uuid.uuid4()
        elif self.role and self.role.code != "business_owner" and self.shop_id:
            self.shop_id = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} ({self.get_business_type_display()})"

    def has_perm(self, perm_codename):
        """
        Check if user has a specific permission.

        Args:
            perm_codename (str): The codename of the permission to check

        Returns:
            bool: True if user has the permission, False otherwise
        """
        if not self.user.is_active:
            return False
        return self.user.is_superuser or self.role.permissions.filter(codename=perm_codename).exists()

    def has_role_or_above(self, role_code):
        """
        Check if user has the specified role or a higher role.

        Args:
            role_code (str): The role code to check against

        Returns:
            bool: True if user has the role or higher, False otherwise
        """
        if not self.role:
            return False

        try:
            required_role = Role.objects.get(code=role_code)
            return self.role.level >= required_role.level
        except Role.DoesNotExist:
            return False

    # Role-based permission methods
    def is_general_user(self):
        """Check if user has general user role or higher"""
        return self.has_role_or_above("general_user")

    def is_business_staff_or_above(self):
        """Check if user has business staff role or higher"""
        return self.has_role_or_above("business_staff")

    def is_business_owner_or_above(self):
        """Check if user has business owner role or higher"""
        return self.has_role_or_above("business_owner")

    def is_agent_or_above(self):
        """Check if user has platform agent role or higher"""
        return self.has_role_or_above("agent")

    def is_manager_or_above(self):
        """Check if user has manager role or higher"""
        return self.has_role_or_above("manager")

    def is_admin(self):
        """Check if user has admin role"""
        return self.has_role_or_above("admin")

    # Business type checks (complementary to role checks)
    def is_business_user(self):
        """Check if user is associated with a business (staff or owner)"""
        return self.is_business_staff_or_above()

    def is_distributor(self):
        """Check if user is a distributor"""
        return self.is_business_user() and self.business_type == self.BusinessType.DISTRIBUTOR

    def is_retailer(self):
        """Check if user is a retailer"""
        return self.is_business_user() and self.business_type == self.BusinessType.RETAILER

    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")


class Contact(models.Model):
    name = models.CharField(max_length=255, verbose_name="Full Name")
    email = models.EmailField(verbose_name="Email Address")
    subject = models.CharField(max_length=255, verbose_name="Subject")
    message = models.TextField(verbose_name="Message")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    def __str__(self):
        return self.name
