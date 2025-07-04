import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from producer.models import City


class UserProfile(models.Model):
    """
    UserProfile model to store additional user information.

    Fields:
    - user: One-to-one relationship with the User model.
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

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name=_("User"))
    phone_number = models.CharField(max_length=15, null=True, blank=True, verbose_name=_("Phone Number"))
    shop_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name=_("Shop ID"))
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

    def __str__(self):
        return f"Shop profile for {self.user.username} ({self.get_business_type_display()})"

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
