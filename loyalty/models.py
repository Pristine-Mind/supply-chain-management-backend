from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LoyaltyTier(models.Model):
    """
    Defines loyalty tiers with point requirements and benefits.
    """

    name = models.CharField(max_length=50, unique=True, verbose_name=_("Tier Name"))
    min_points = models.PositiveIntegerField(
        default=0, verbose_name=_("Minimum Points Required"), help_text=_("Lifetime points required to reach this tier")
    )
    point_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("99.99"))],
        help_text=_("Multiplier for points earned at this tier (e.g., 1.50 for 50% bonus)"),
        verbose_name=_("Point Multiplier"),
    )
    description = models.TextField(blank=True, verbose_name=_("Description"))
    is_active = models.BooleanField(
        default=True, verbose_name=_("Is Active"), help_text=_("Inactive tiers cannot be assigned to users")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["min_points"]
        verbose_name = _("Loyalty Tier")
        verbose_name_plural = _("Loyalty Tiers")
        indexes = [
            models.Index(fields=["min_points", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """Validate that min_points values don't overlap."""
        super().clean()

        # Check for duplicate min_points
        overlapping = LoyaltyTier.objects.filter(min_points=self.min_points, is_active=True).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError({"min_points": _("A tier with this minimum points requirement already exists.")})

        # Validate point_multiplier is positive
        if self.point_multiplier <= 0:
            raise ValidationError({"point_multiplier": _("Point multiplier must be greater than 0.")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class LoyaltyPerk(models.Model):
    """
    Perks available to users at specific loyalty tiers.
    """

    tier = models.ForeignKey(LoyaltyTier, on_delete=models.CASCADE, related_name="perks", verbose_name=_("Tier"))
    name = models.CharField(max_length=100, verbose_name=_("Perk Name"))
    description = models.TextField(verbose_name=_("Description"))
    code = models.SlugField(
        max_length=50, unique=True, blank=True, null=True, help_text=_("Unique code for programmatic access to perks")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Loyalty Perk")
        verbose_name_plural = _("Loyalty Perks")
        indexes = [
            models.Index(fields=["code", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.tier.name})"

    def clean(self):
        """Validate perk code uniqueness if provided."""
        super().clean()
        if self.code:
            duplicate = LoyaltyPerk.objects.filter(code=self.code).exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError({"code": _("A perk with this code already exists.")})


class UserLoyalty(models.Model):
    """
    User loyalty profile tracking points and tier status.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="loyalty_profile", verbose_name=_("User"))
    points = models.PositiveIntegerField(
        default=0, verbose_name=_("Current Points"), help_text=_("Available points for redemption")
    )
    lifetime_points = models.PositiveIntegerField(
        default=0, verbose_name=_("Lifetime Points"), help_text=_("Total points earned over all time (determines tier)")
    )
    tier = models.ForeignKey(LoyaltyTier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Current Tier"))
    is_active = models.BooleanField(
        default=True, verbose_name=_("Is Active"), help_text=_("Inactive profiles cannot earn or redeem points")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tier_updated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Tier Last Updated"))

    class Meta:
        verbose_name = _("User Loyalty Profile")
        verbose_name_plural = _("User Loyalty Profiles")
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["tier", "lifetime_points"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.points} points"

    def update_tier(self):
        """
        Update user tier based on lifetime points.
        Returns True if tier changed, False otherwise.
        """
        new_tier = (
            LoyaltyTier.objects.filter(min_points__lte=self.lifetime_points, is_active=True).order_by("-min_points").first()
        )

        if new_tier != self.tier:
            self.tier = new_tier
            self.tier_updated_at = timezone.now()
            self.save(update_fields=["tier", "tier_updated_at", "updated_at"])
            return True
        return False

    def get_points_to_next_tier(self):
        """
        Calculate points needed to reach the next tier.
        Returns None if already at highest tier.
        """
        if not self.tier:
            # Get the first tier
            next_tier = LoyaltyTier.objects.filter(is_active=True).order_by("min_points").first()
            if next_tier:
                return max(0, next_tier.min_points - self.lifetime_points)
            return None

        next_tier = (
            LoyaltyTier.objects.filter(min_points__gt=self.tier.min_points, is_active=True).order_by("min_points").first()
        )

        if next_tier:
            return max(0, next_tier.min_points - self.lifetime_points)
        return None

    def clean(self):
        """Validate that points don't exceed lifetime points."""
        super().clean()
        if self.points > self.lifetime_points:
            raise ValidationError({"points": _("Current points cannot exceed lifetime points.")})


class LoyaltyTransaction(models.Model):
    """
    Records all point transactions for audit and history.
    """

    TRANSACTION_TYPES = [
        ("earn", _("Earned")),
        ("redeem", _("Redeemed")),
        ("expire", _("Expired")),
        ("refund", _("Refund")),
        ("admin_add", _("Admin Addition")),
        ("admin_deduct", _("Admin Deduction")),
        ("bonus", _("Bonus")),
    ]

    user_loyalty = models.ForeignKey(
        UserLoyalty, on_delete=models.CASCADE, related_name="transactions", verbose_name=_("User Loyalty")
    )
    points = models.IntegerField(verbose_name=_("Points"), help_text=_("Positive for earned, negative for redeemed/expired"))
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES, verbose_name=_("Type"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    # Optional link to a purchase - use CharField to support UUID or other formats
    purchase_id = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Purchase ID"), db_index=True)

    # Additional metadata
    reference_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("Reference ID"),
        help_text=_("Unique identifier to prevent duplicate transactions"),
    )

    metadata = models.JSONField(
        default=dict, blank=True, verbose_name=_("Metadata"), help_text=_("Additional transaction data")
    )

    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_transactions_created",
        verbose_name=_("Created By"),
        help_text=_("User who created this transaction (for admin adjustments)"),
    )

    # Balance snapshot at time of transaction
    balance_after = models.PositiveIntegerField(
        verbose_name=_("Balance After"), help_text=_("Point balance after this transaction")
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Loyalty Transaction")
        verbose_name_plural = _("Loyalty Transactions")
        indexes = [
            models.Index(fields=["-created_at", "user_loyalty"]),
            models.Index(fields=["purchase_id", "transaction_type"]),
            models.Index(fields=["reference_id"]),
            models.Index(fields=["transaction_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user_loyalty.user.username}: {self.points} ({self.transaction_type})"


class LoyaltyTransactionArchive(models.Model):
    """
    Archived loyalty transactions for long-term storage.
    """

    user_id = models.IntegerField(db_index=True)
    username = models.CharField(max_length=150)
    points = models.IntegerField()
    transaction_type = models.CharField(max_length=15)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)
    purchase_id = models.CharField(max_length=100, null=True, blank=True)
    reference_id = models.CharField(max_length=100, null=True, blank=True)
    metadata = models.JSONField(default=dict)
    balance_after = models.PositiveIntegerField()

    class Meta:
        verbose_name = _("Loyalty Transaction Archive")
        verbose_name_plural = _("Loyalty Transaction Archives")
        ordering = ["-created_at"]

    def clean(self):
        """Validate transaction data."""
        super().clean()

        # Validate points sign matches transaction type
        if self.transaction_type in ["earn", "admin_add", "bonus", "refund"]:
            if self.points < 0:
                raise ValidationError({"points": _("Points must be positive for this transaction type.")})
        elif self.transaction_type in ["redeem", "expire", "admin_deduct"]:
            if self.points > 0:
                raise ValidationError({"points": _("Points must be negative for this transaction type.")})


class LoyaltyConfiguration(models.Model):
    """
    Global configuration for the loyalty system.
    Singleton model - only one record should exist.
    """

    points_per_unit = models.PositiveIntegerField(
        default=1, verbose_name=_("Points Per Unit"), help_text=_("Number of points earned per unit amount")
    )
    unit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name=_("Unit Amount"),
        help_text=_("Currency amount that equals one unit (e.g., 100 NPR)"),
    )
    points_expiry_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Points Expiry Days"),
        help_text=_("Days until earned points expire (null = never expire)"),
    )
    min_redemption_points = models.PositiveIntegerField(
        default=100, verbose_name=_("Minimum Redemption Points"), help_text=_("Minimum points required for redemption")
    )
    max_redemption_points = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Maximum Redemption Points"),
        help_text=_("Maximum points that can be redeemed in one transaction"),
    )
    allow_negative_balance = models.BooleanField(
        default=False, verbose_name=_("Allow Negative Balance"), help_text=_("Allow users to have negative point balance")
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Updated By"))

    class Meta:
        verbose_name = _("Loyalty Configuration")
        verbose_name_plural = _("Loyalty Configurations")

    def __str__(self):
        return f"Loyalty Config: {self.points_per_unit} pts per {self.unit_amount}"

    def save(self, *args, **kwargs):
        """Ensure only one configuration exists."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of configuration."""
        pass

    @classmethod
    def get_config(cls):
        """Get or create the singleton configuration."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config
