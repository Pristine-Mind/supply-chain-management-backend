import uuid

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from market.models import MarketplaceSale


class TransportStatus(models.TextChoices):
    AVAILABLE = "available", _("Available")
    ASSIGNED = "assigned", _("Assigned to Transporter")
    PICKED_UP = "picked_up", _("Picked Up")
    IN_TRANSIT = "in_transit", _("In Transit")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    RETURNED = "returned", _("Returned")


class VehicleType(models.TextChoices):
    BIKE = "bike", _("Motorcycle/Bike")
    CAR = "car", _("Car")
    VAN = "van", _("Van")
    TRUCK = "truck", _("Truck")
    OTHER = "other", _("Other")


class DeliveryPriority(models.TextChoices):
    LOW = "low", _("Low")
    NORMAL = "normal", _("Normal")
    HIGH = "high", _("High")
    URGENT = "urgent", _("Urgent")


class Transporter(models.Model):
    """
    Profile for transport service providers
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="transporter_profile")

    # Personal Information
    license_number = models.CharField(max_length=50, unique=True, verbose_name=_("License Number"))
    phone = PhoneNumberField(verbose_name=_("Phone Number"))

    # Vehicle Information
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, verbose_name=_("Vehicle Type"))
    vehicle_number = models.CharField(max_length=20, verbose_name=_("Vehicle Number"))
    vehicle_capacity = models.DecimalField(
        max_digits=8, decimal_places=2, help_text=_("Maximum weight capacity in kg"), verbose_name=_("Vehicle Capacity (kg)")
    )
    vehicle_image = models.ImageField(upload_to="vehicle_images", verbose_name=_("Vehicle Image"), null=True, blank=True)
    vehicle_documents = models.FileField(
        upload_to="vehicle_documents", verbose_name=_("Vehicle Documents"), null=True, blank=True
    )

    # Location and Availability
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_available = models.BooleanField(default=True, verbose_name=_("Available for Deliveries"))

    # Ratings and Performance
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name=_("Average Rating"),
    )
    total_deliveries = models.PositiveIntegerField(default=0, verbose_name=_("Total Deliveries"))
    successful_deliveries = models.PositiveIntegerField(default=0, verbose_name=_("Successful Deliveries"))

    # Account Information
    is_verified = models.BooleanField(default=False, verbose_name=_("Is Verified"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Transporter")
        verbose_name_plural = _("Transporters")
        indexes = [
            models.Index(fields=["is_verified", "is_available"]),
            models.Index(fields=["vehicle_type"]),
            models.Index(fields=["current_latitude", "current_longitude"]),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.vehicle_type}"

    @property
    def success_rate(self):
        if self.total_deliveries == 0:
            return 0
        return (self.successful_deliveries / self.total_deliveries) * 100

    def update_rating(self):
        """Update the transporter's average rating"""
        ratings = DeliveryRating.objects.filter(transporter=self)
        if ratings.exists():
            avg_rating = ratings.aggregate(avg=models.Avg("rating"))["avg"]
            self.rating = round(avg_rating, 2)
        self.save()


class Delivery(models.Model):
    """
    Enhanced Delivery model for the transport system
    """

    # Basic Information
    delivery_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    marketplace_sale = models.OneToOneField(
        MarketplaceSale,
        on_delete=models.CASCADE,
        related_name="delivery_details",
    )

    # Pickup Information
    pickup_address = models.TextField(verbose_name=_("Pickup Address"))
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_contact_name = models.CharField(max_length=255, verbose_name=_("Pickup Contact Name"))
    pickup_contact_phone = PhoneNumberField(verbose_name=_("Pickup Contact Phone"))

    # Delivery Information
    delivery_address = models.TextField(verbose_name=_("Delivery Address"))
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_contact_name = models.CharField(max_length=255, verbose_name=_("Delivery Contact Name"))
    delivery_contact_phone = PhoneNumberField(verbose_name=_("Delivery Contact Phone"))

    # Package Information
    package_weight = models.DecimalField(
        max_digits=8, decimal_places=2, help_text=_("Weight in kg"), verbose_name=_("Package Weight (kg)")
    )
    package_dimensions = models.CharField(
        max_length=100, blank=True, help_text=_("LxWxH in cm"), verbose_name=_("Package Dimensions")
    )
    special_instructions = models.TextField(blank=True, verbose_name=_("Special Instructions"))

    # Transport Assignment
    transporter = models.ForeignKey(
        Transporter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_deliveries",
        verbose_name=_("Assigned Transporter"),
    )

    # Status and Timing
    status = models.CharField(
        max_length=20, choices=TransportStatus.choices, default=TransportStatus.AVAILABLE, verbose_name=_("Delivery Status")
    )
    priority = models.CharField(
        max_length=10, choices=DeliveryPriority.choices, default=DeliveryPriority.NORMAL, verbose_name=_("Delivery Priority")
    )

    # Important Dates
    requested_pickup_date = models.DateTimeField(verbose_name=_("Requested Pickup Date"))
    requested_delivery_date = models.DateTimeField(verbose_name=_("Requested Delivery Date"))

    assigned_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Assigned At"))
    picked_up_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Picked Up At"))
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Delivered At"))

    # Pricing
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Delivery Fee"))
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name=_("Distance (km)"))

    # Tracking
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Delivery")
        verbose_name_plural = _("Deliveries")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["transporter", "status"]),
            models.Index(fields=["requested_pickup_date"]),
            models.Index(fields=["priority", "status"]),
            models.Index(fields=["pickup_latitude", "pickup_longitude"]),
            models.Index(fields=["delivery_latitude", "delivery_longitude"]),
        ]

    def __str__(self):
        return f"Delivery {self.delivery_id} - {self.status}"

    def assign_to_transporter(self, transporter):
        """Assign delivery to a transporter"""
        self.transporter = transporter
        self.status = TransportStatus.ASSIGNED
        self.assigned_at = timezone.now()
        self.save()

    def mark_picked_up(self):
        """Mark delivery as picked up"""
        self.status = TransportStatus.PICKED_UP
        self.picked_up_at = timezone.now()
        self.save()

    def mark_in_transit(self):
        """Mark delivery as in transit"""
        self.status = TransportStatus.IN_TRANSIT
        self.save()

    def mark_delivered(self):
        """Mark delivery as delivered"""
        self.status = TransportStatus.DELIVERED
        self.delivered_at = timezone.now()
        self.save()

        # Update transporter statistics
        if self.transporter:
            self.transporter.total_deliveries += 1
            self.transporter.successful_deliveries += 1
            self.transporter.save()


class DeliveryTracking(models.Model):
    """
    Track delivery progress with timestamps and locations
    """

    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name="tracking_updates")
    status = models.CharField(max_length=20, choices=TransportStatus.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Delivery Tracking")
        verbose_name_plural = _("Delivery Tracking")
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.delivery.delivery_id} - {self.status} at {self.timestamp}"


class DeliveryRating(models.Model):
    """
    Rating system for deliveries
    """

    delivery = models.OneToOneField(Delivery, on_delete=models.CASCADE, related_name="rating")
    rated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    transporter = models.ForeignKey(Transporter, on_delete=models.CASCADE)

    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name=_("Rating (1-5)")
    )
    comment = models.TextField(blank=True, verbose_name=_("Comment"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Delivery Rating")
        verbose_name_plural = _("Delivery Ratings")
        unique_together = ["delivery", "rated_by"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.transporter.update_rating()

    def __str__(self):
        return f"Rating {self.rating}/5 for {self.transporter.user.get_full_name()}"
