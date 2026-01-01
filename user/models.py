import random
import string
import uuid
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.db import models
from django.utils import timezone
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
        general_user = cls.get_or_create_role(
            code="general_user", name="General User", level=1, description="End users with basic access to the platform."
        )
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

        transporter = cls.get_or_create_role(
            code="transporter", name="Transporter", level=7, description="Transporters with access to transport features."
        )

        return {
            "general_user": general_user,
            "business_staff": business_staff,
            "business_owner": business_owner,
            "agent": agent,
            "manager": manager,
            "admin": admin,
            "transporter": transporter,
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
        null=True,
        blank=True,
        verbose_name=_("Business Type"),
    )
    registration_certificate = models.FileField(
        upload_to="user_documents/registration_certificates/",
        null=True,
        blank=True,
        verbose_name=_("Registration Certificate"),
        help_text=_("Upload your business registration certificate (PDF, DOC, DOCX, JPG, PNG)"),
    )
    pan_certificate = models.FileField(
        upload_to="user_documents/pan_certificates/",
        null=True,
        blank=True,
        verbose_name=_("PAN Certificate"),
        help_text=_("Upload your PAN certificate (PDF, JPG, PNG)"),
    )
    profile_image = models.ImageField(
        upload_to="user_profile_images/",
        null=True,
        blank=True,
        verbose_name=_("Profile Image"),
        help_text=_("Upload a profile picture (JPG, PNG)"),
    )
    registered_business_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Registered Business Name"),
    )

    # B2B Business Fields
    b2b_verified = models.BooleanField(
        default=False,
        verbose_name=_("B2B Verified"),
        help_text=_("Business is verified for B2B purchases with special pricing"),
    )
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name=_("Credit Limit"),
        help_text=_("Maximum credit limit allowed for this business"),
    )
    payment_terms_days = models.PositiveIntegerField(
        default=30, verbose_name=_("Payment Terms (Days)"), help_text=_("Number of days allowed for payment (Net terms)")
    )
    tax_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Tax ID/VAT Number"),
        help_text=_("Business tax identification number"),
    )
    credit_used = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name=_("Credit Used"),
        help_text=_("Current amount of credit being used"),
    )

    payment_qr_payload = models.TextField(blank=True)
    payment_qr_image = models.ImageField(upload_to="user_qr_codes/", blank=True, null=True)

    # Additional profile fields
    bio = models.TextField(null=True, blank=True, verbose_name=_("Bio"))
    date_of_birth = models.DateField(null=True, blank=True, verbose_name=_("Date of Birth"))
    gender = models.CharField(
        max_length=20,
        choices=[
            ("male", _("Male")),
            ("female", _("Female")),
            ("other", _("Other")),
            ("prefer_not_to_say", _("Prefer not to say")),
        ],
        null=True,
        blank=True,
        verbose_name=_("Gender"),
    )
    address = models.TextField(null=True, blank=True, verbose_name=_("Address"))
    city = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("City"))
    state = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("State"))
    zip_code = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("ZIP Code"))
    country = models.CharField(max_length=100, default="Nepal", verbose_name=_("Country"))

    # Notification preferences
    email_notifications = models.BooleanField(default=True, verbose_name=_("Email Notifications"))
    sms_notifications = models.BooleanField(default=True, verbose_name=_("SMS Notifications"))
    marketing_emails = models.BooleanField(default=False, verbose_name=_("Marketing Emails"))
    order_updates = models.BooleanField(default=True, verbose_name=_("Order Updates"))

    def save(self, *args, **kwargs):
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

    def is_business_user(self):
        """Check if user is associated with a business (staff or owner)"""
        return self.is_business_staff_or_above()

    def is_distributor(self):
        """Check if user is a distributor"""
        return self.is_business_user() and self.business_type == self.BusinessType.DISTRIBUTOR

    def is_retailer(self):
        """Check if user is a retailer"""
        return self.is_business_user() and self.business_type == self.BusinessType.RETAILER

    def get_available_credit(self):
        """Get available credit amount"""
        return self.credit_limit - self.credit_used

    def has_sufficient_credit(self, amount):
        """Check if user has sufficient credit for a given amount"""
        return self.get_available_credit() >= amount

    def is_b2b_eligible(self):
        """Check if user is eligible for B2B pricing"""
        return self.b2b_verified

    def can_use_credit(self, amount):
        """Check if user can use credit for purchase"""
        return self.is_b2b_eligible() and self.has_sufficient_credit(amount) and self.credit_limit > 0

    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")
        indexes = [
            models.Index(fields=["business_type", "location"]),
            models.Index(fields=["b2b_verified"]),
        ]


class Contact(models.Model):
    name = models.CharField(max_length=255, verbose_name="Full Name")
    email = models.EmailField(verbose_name="Email Address")
    subject = models.CharField(max_length=255, verbose_name="Subject")
    message = models.TextField(verbose_name="Message")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    def __str__(self):
        return self.name


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


class PhoneOTP(models.Model):
    phone_number = models.CharField(max_length=15, unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Phone OTP"
        verbose_name_plural = "Phone OTPs"

    def __str__(self):
        return f"{self.phone_number} - {self.otp}"

    def is_expired(self):
        return (timezone.now() - self.created_at).total_seconds() > 300

    @classmethod
    def generate_otp_for_phone(cls, phone_number):
        cls.objects.filter(phone_number=phone_number).delete()
        otp = generate_otp()
        return cls.objects.create(phone_number=phone_number, otp=otp)

    @classmethod
    def verify_otp(cls, phone_number, otp):
        try:
            phone_otp = cls.objects.get(phone_number=phone_number, otp=otp, is_verified=False)
            if phone_otp.is_expired():
                return False, "OTP has expired"

            phone_otp.is_verified = True
            phone_otp.save()
            return True, "OTP verified successfully"
        except cls.DoesNotExist:
            return False, "Invalid OTP"


class LoginAttempt(models.Model):
    """
    Model to track login attempts for security purposes.
    Supports sliding window rate limiting and account lockout.
    """

    ATTEMPT_TYPE_CHOICES = [
        ("login_failed", "Login Failed"),
        ("account_locked", "Account Locked"),
        ("ip_blocked", "IP Blocked"),
    ]

    ip_address = models.GenericIPAddressField(verbose_name=_("IP Address"))
    username = models.CharField(max_length=150, blank=True, null=True, verbose_name=_("Username"))
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, verbose_name=_("User"))
    attempt_type = models.CharField(max_length=20, choices=ATTEMPT_TYPE_CHOICES, default="login_failed")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Timestamp"))
    user_agent = models.TextField(blank=True, null=True, verbose_name=_("User Agent"))

    class Meta:
        verbose_name = _("Login Attempt")
        verbose_name_plural = _("Login Attempts")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["ip_address", "timestamp"]),
            models.Index(fields=["username", "timestamp"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.ip_address} - {self.username or 'Unknown'} - {self.timestamp}"

    @classmethod
    def get_failed_attempts_for_ip(cls, ip_address, minutes=15):
        """Get failed login attempts for an IP within specified time window"""
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        return cls.objects.filter(ip_address=ip_address, timestamp__gte=time_threshold, attempt_type="login_failed").count()

    @classmethod
    def get_failed_attempts_for_user(cls, username, minutes=15):
        """Get failed login attempts for a username within specified time window"""
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        return cls.objects.filter(username=username, timestamp__gte=time_threshold, attempt_type="login_failed").count()

    @classmethod
    def is_ip_blocked(cls, ip_address, max_attempts=10, minutes=15):
        """Check if an IP should be blocked based on sliding window"""
        failed_attempts = cls.get_failed_attempts_for_ip(ip_address, minutes)
        return failed_attempts >= max_attempts

    @classmethod
    def is_user_locked(cls, username, max_attempts=3, minutes=15):
        """Check if a user account should be locked based on sliding window"""
        failed_attempts = cls.get_failed_attempts_for_user(username, minutes)
        return failed_attempts >= max_attempts

    @classmethod
    def record_failed_attempt(cls, ip_address, username=None, user=None, user_agent=None):
        """Record a failed login attempt"""
        return cls.objects.create(
            ip_address=ip_address, username=username, user=user, attempt_type="login_failed", user_agent=user_agent
        )

    @classmethod
    def clear_expired_attempts(cls, minutes=15):
        """Clear login attempts older than specified minutes"""
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        deleted_count = cls.objects.filter(timestamp__lt=time_threshold).delete()[0]
        return deleted_count

    @classmethod
    def get_lockout_time_remaining(cls, username, minutes=15):
        """Get remaining lockout time for a user in seconds"""
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        latest_attempt = cls.objects.filter(username=username, attempt_type="login_failed").first()

        if latest_attempt:
            lockout_expires = latest_attempt.timestamp + timezone.timedelta(minutes=minutes)
            if lockout_expires > timezone.now():
                return int((lockout_expires - timezone.now()).total_seconds())
        return 0
