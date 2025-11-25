import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from market.models import MarketplaceSale
from producer.models import Sale


class TransportStatus(models.TextChoices):
    AVAILABLE = "available", _("Available")
    ASSIGNED = "assigned", _("Assigned to Transporter")
    PICKED_UP = "picked_up", _("Picked Up")
    IN_TRANSIT = "in_transit", _("In Transit")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    RETURNED = "returned", _("Returned")
    FAILED = "failed", _("Failed Delivery")


class VehicleType(models.TextChoices):
    BIKE = "bike", _("Motorcycle/Bike")
    CAR = "car", _("Car")
    VAN = "van", _("Van")
    TRUCK = "truck", _("Truck")
    BICYCLE = "bicycle", _("Bicycle")
    OTHER = "other", _("Other")


class DeliveryPriority(models.TextChoices):
    LOW = "low", _("Low")
    NORMAL = "normal", _("Normal")
    HIGH = "high", _("High")
    URGENT = "urgent", _("Urgent")
    SAME_DAY = "same_day", _("Same Day")


class TransporterStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    SUSPENDED = "suspended", _("Suspended")
    OFFLINE = "offline", _("Offline")


class Transporter(models.Model):
    """
    Profile for transport service providers
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="transporter_profile")

    # Personal Information
    license_number = models.CharField(max_length=50, unique=True, verbose_name=_("License Number"))
    phone = PhoneNumberField(verbose_name=_("Phone Number"))
    emergency_contact = PhoneNumberField(verbose_name=_("Emergency Contact"), null=True, blank=True)

    # Business Information
    business_name = models.CharField(max_length=255, verbose_name=_("Business Name"), null=True, blank=True)
    tax_id = models.CharField(max_length=50, verbose_name=_("Tax ID"), null=True, blank=True)

    # Vehicle Information
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, verbose_name=_("Vehicle Type"))
    vehicle_number = models.CharField(max_length=20, verbose_name=_("Vehicle Number"))
    vehicle_capacity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text=_("Maximum weight capacity in kg"),
        verbose_name=_("Vehicle Capacity (kg)"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    vehicle_image = models.ImageField(upload_to="vehicle_images", verbose_name=_("Vehicle Image"), null=True, blank=True)
    vehicle_documents = models.FileField(
        upload_to="vehicle_documents", verbose_name=_("Vehicle Documents"), null=True, blank=True
    )
    insurance_expiry = models.DateField(verbose_name=_("Insurance Expiry Date"), null=True, blank=True)
    license_expiry = models.DateField(verbose_name=_("License Expiry Date"), null=True, blank=True)

    # Location and Availability
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    service_radius = models.PositiveIntegerField(default=50, verbose_name=_("Service Radius (km)"))
    is_available = models.BooleanField(default=True, verbose_name=_("Available for Deliveries"))
    status = models.CharField(
        max_length=20,
        choices=TransporterStatus.choices,
        default=TransporterStatus.ACTIVE,
        verbose_name=_("Transporter Status"),
    )
    last_location_update = models.DateTimeField(null=True, blank=True)

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
    cancelled_deliveries = models.PositiveIntegerField(default=0, verbose_name=_("Cancelled Deliveries"))

    # Financial Information
    earnings_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_("Total Earnings"))
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Commission Rate (%)"),
    )

    # Account Information
    is_verified = models.BooleanField(default=False, verbose_name=_("Is Verified"))
    verification_documents = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Transporter")
        verbose_name_plural = _("Transporters")
        indexes = [
            models.Index(fields=["is_verified", "is_available", "status"]),
            models.Index(fields=["vehicle_type"]),
            models.Index(fields=["current_latitude", "current_longitude"]),
            models.Index(fields=["status"]),
            models.Index(fields=["service_radius"]),
        ]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_vehicle_type_display()}"

    @property
    def success_rate(self):
        if self.total_deliveries == 0:
            return 0
        return round((self.successful_deliveries / self.total_deliveries) * 100, 2)

    @property
    def cancellation_rate(self):
        if self.total_deliveries == 0:
            return 0
        return round((self.cancelled_deliveries / self.total_deliveries) * 100, 2)

    def update_rating(self):
        """Update the transporter's average rating"""
        ratings = DeliveryRating.objects.filter(transporter=self)
        if ratings.exists():
            avg_rating = ratings.aggregate(avg=models.Avg("rating"))["avg"]
            self.rating = round(avg_rating, 2)
            self.save(update_fields=["rating"])

    def update_location(self, latitude, longitude):
        """Update transporter's current location"""
        self.current_latitude = latitude
        self.current_longitude = longitude
        self.last_location_update = timezone.now()
        self.save(update_fields=["current_latitude", "current_longitude", "last_location_update"])

    def is_documents_expired(self):
        """Check if any critical documents are expired"""
        today = timezone.now().date()
        return (self.insurance_expiry and self.insurance_expiry <= today) or (
            self.license_expiry and self.license_expiry <= today
        )

    def get_current_deliveries(self):
        """Get deliveries currently assigned to this transporter"""
        return self.assigned_deliveries.filter(
            status__in=[TransportStatus.ASSIGNED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
        )


class Delivery(models.Model):
    """
    Enhanced Delivery model for the transport system
    """

    # Basic Information
    delivery_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Source relationships (one of these should be set)
    marketplace_sale = models.OneToOneField(
        MarketplaceSale,
        on_delete=models.CASCADE,
        related_name="delivery_details",
        null=True,
        blank=True,
    )
    sale = models.OneToOneField(
        Sale,
        on_delete=models.CASCADE,
        related_name="transport_delivery",
        null=True,
        blank=True,
    )
    external_delivery = models.OneToOneField(
        "external_delivery.ExternalDelivery",
        on_delete=models.CASCADE,
        related_name="external_transport_delivery",
        null=True,
        blank=True,
    )

    tracking_number = models.CharField(max_length=20, unique=True, blank=True, null=True)

    # Pickup Information
    pickup_address = models.TextField(verbose_name=_("Pickup Address"))
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_contact_name = models.CharField(max_length=255, verbose_name=_("Pickup Contact Name"))
    pickup_contact_phone = PhoneNumberField(verbose_name=_("Pickup Contact Phone"))
    pickup_instructions = models.TextField(blank=True, verbose_name=_("Pickup Instructions"))

    # Delivery Information
    delivery_address = models.TextField(verbose_name=_("Delivery Address"))
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_contact_name = models.CharField(max_length=255, verbose_name=_("Delivery Contact Name"))
    delivery_contact_phone = PhoneNumberField(verbose_name=_("Delivery Contact Phone"))
    delivery_instructions = models.TextField(blank=True, verbose_name=_("Delivery Instructions"))

    # Package Information
    package_weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text=_("Weight in kg"),
        verbose_name=_("Package Weight (kg)"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    package_dimensions = models.CharField(
        max_length=100, blank=True, help_text=_("LxWxH in cm"), verbose_name=_("Package Dimensions")
    )
    package_value = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_("Package Value")
    )
    fragile = models.BooleanField(default=False, verbose_name=_("Fragile Package"))
    requires_signature = models.BooleanField(default=False, verbose_name=_("Requires Signature"))
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
        max_length=15, choices=DeliveryPriority.choices, default=DeliveryPriority.NORMAL, verbose_name=_("Delivery Priority")
    )

    # Important Dates
    requested_pickup_date = models.DateTimeField(verbose_name=_("Requested Pickup Date"))
    requested_delivery_date = models.DateTimeField(verbose_name=_("Requested Delivery Date"))

    assigned_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Assigned At"))
    picked_up_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Picked Up At"))
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Delivered At"))
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Cancelled At"))
    cancellation_reason = models.TextField(blank=True, verbose_name=_("Cancellation Reason"))

    # Pricing
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Delivery Fee"))
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name=_("Distance (km)"))
    fuel_surcharge = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name=_("Fuel Surcharge"))

    # Tracking
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)
    actual_pickup_time = models.DateTimeField(null=True, blank=True)

    # Proof of delivery
    delivery_photo = models.ImageField(upload_to="delivery_proofs", null=True, blank=True, verbose_name=_("Delivery Photo"))
    signature_image = models.ImageField(upload_to="delivery_signatures", null=True, blank=True, verbose_name=_("Signature"))
    delivery_notes = models.TextField(blank=True, verbose_name=_("Delivery Notes"))

    # Attempt tracking
    delivery_attempts = models.PositiveIntegerField(default=0, verbose_name=_("Delivery Attempts"))
    max_delivery_attempts = models.PositiveIntegerField(default=3, verbose_name=_("Max Delivery Attempts"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Validate that exactly one of marketplace_sale, sale, or external_delivery is provided."""
        from django.core.exceptions import ValidationError

        # Count how many source fields are provided
        source_count = sum([bool(self.marketplace_sale), bool(self.sale), bool(self.external_delivery)])

        if source_count == 0:
            raise ValidationError("One of marketplace_sale, sale, or external_delivery must be provided.")
        elif source_count > 1:
            raise ValidationError("Only one of marketplace_sale, sale, or external_delivery can be provided, not both.")

    def save(self, *args, **kwargs):
        """Override save to call clean validation and generate tracking number."""
        self.clean()
        if not self.tracking_number:
            self.tracking_number = self.generate_tracking_number()
        super().save(*args, **kwargs)

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
            models.Index(fields=["tracking_number"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(marketplace_sale__isnull=False, sale__isnull=True, external_delivery__isnull=True)
                    | models.Q(marketplace_sale__isnull=True, sale__isnull=False, external_delivery__isnull=True)
                    | models.Q(marketplace_sale__isnull=True, sale__isnull=True, external_delivery__isnull=False)
                ),
                name="transport_delivery_source_constraint",
            )
        ]

    def generate_tracking_number(self):
        """Generate a unique tracking number"""
        import random
        import string

        while True:
            tracking_number = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
            if not Delivery.objects.filter(tracking_number=tracking_number).exists():
                return tracking_number

    def __str__(self):
        return f"Delivery {self.tracking_number} - {self.get_status_display()}"

    def assign_to_transporter(self, transporter):
        """Assign delivery to a transporter"""
        if self.status != TransportStatus.AVAILABLE:
            raise ValueError("Delivery is not available for assignment")

        self.transporter = transporter
        self.status = TransportStatus.ASSIGNED
        self.assigned_at = timezone.now()
        self.save()

        # Create tracking entry
        DeliveryTracking.objects.create(
            delivery=self, status=TransportStatus.ASSIGNED, notes=f"Assigned to {transporter.user.get_full_name()}"
        )

    def mark_picked_up(self, latitude=None, longitude=None, notes=""):
        """Mark delivery as picked up"""
        self.status = TransportStatus.PICKED_UP
        self.picked_up_at = timezone.now()
        self.actual_pickup_time = self.picked_up_at
        self.save()

        # Create tracking entry
        DeliveryTracking.objects.create(
            delivery=self, status=TransportStatus.PICKED_UP, latitude=latitude, longitude=longitude, notes=notes
        )

    def mark_in_transit(self, latitude=None, longitude=None, notes=""):
        """Mark delivery as in transit"""
        self.status = TransportStatus.IN_TRANSIT
        self.save()

        # Create tracking entry
        DeliveryTracking.objects.create(
            delivery=self, status=TransportStatus.IN_TRANSIT, latitude=latitude, longitude=longitude, notes=notes
        )

    def mark_delivered(self, latitude=None, longitude=None, notes="", photo=None, signature=None):
        """Mark delivery as delivered"""
        self.status = TransportStatus.DELIVERED
        self.delivered_at = timezone.now()
        self.delivery_notes = notes
        if photo:
            self.delivery_photo = photo
        if signature:
            self.signature_image = signature
        self.save()

        # Update transporter statistics
        if self.transporter:
            self.transporter.total_deliveries += 1
            self.transporter.successful_deliveries += 1
            self.transporter.earnings_total += self.delivery_fee * (1 - self.transporter.commission_rate / 100)
            self.transporter.save()

        # Create tracking entry
        DeliveryTracking.objects.create(
            delivery=self, status=TransportStatus.DELIVERED, latitude=latitude, longitude=longitude, notes=notes
        )

    def cancel_delivery(self, reason="", cancelled_by=None):
        """Cancel the delivery"""
        self.status = TransportStatus.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save()

        # Update transporter statistics if assigned
        if self.transporter:
            self.transporter.cancelled_deliveries += 1
            self.transporter.save()

        # Create tracking entry
        DeliveryTracking.objects.create(delivery=self, status=TransportStatus.CANCELLED, notes=f"Cancelled: {reason}")

    def increment_delivery_attempt(self):
        """Increment delivery attempt counter"""
        self.delivery_attempts += 1
        if self.delivery_attempts >= self.max_delivery_attempts:
            self.status = TransportStatus.FAILED
        self.save()

    @property
    def is_overdue(self):
        """Check if delivery is overdue"""
        if self.status == TransportStatus.DELIVERED:
            return False
        return timezone.now() > self.requested_delivery_date

    @property
    def time_since_pickup(self):
        """Get time elapsed since pickup"""
        if self.picked_up_at:
            return timezone.now() - self.picked_up_at
        return None


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
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = _("Delivery Tracking")
        verbose_name_plural = _("Delivery Tracking")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["delivery", "timestamp"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.delivery.tracking_number} - {self.get_status_display()} at {self.timestamp}"


class DeliveryRating(models.Model):
    """
    Rating system for deliveries
    """

    delivery = models.OneToOneField(Delivery, on_delete=models.CASCADE, related_name="rating")
    rated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    transporter = models.ForeignKey(Transporter, on_delete=models.CASCADE, related_name="ratings")

    # Rating categories
    overall_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name=_("Overall Rating (1-5)"),
        null=True,
        blank=True,
    )
    punctuality_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name=_("Punctuality (1-5)"), null=True, blank=True
    )
    communication_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name=_("Communication (1-5)"), null=True, blank=True
    )
    package_handling_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name=_("Package Handling (1-5)"),
        null=True,
        blank=True,
    )

    comment = models.TextField(blank=True, verbose_name=_("Comment"))
    is_anonymous = models.BooleanField(default=False, verbose_name=_("Anonymous Rating"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Delivery Rating")
        verbose_name_plural = _("Delivery Ratings")
        unique_together = ["delivery", "rated_by"]
        indexes = [
            models.Index(fields=["transporter", "overall_rating"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update transporter rating asynchronously in production
        self.transporter.update_rating()

    @property
    def rating(self):
        """Backward compatibility property"""
        return self.overall_rating

    def __str__(self):
        return f"Rating {self.overall_rating}/5 for {self.transporter.user.get_full_name()}"


class DeliveryRoute(models.Model):
    """
    Optimize delivery routes for transporters
    """

    transporter = models.ForeignKey(Transporter, on_delete=models.CASCADE, related_name="routes")
    name = models.CharField(max_length=255, verbose_name=_("Route Name"))
    deliveries = models.ManyToManyField(Delivery, through="RouteDelivery")

    estimated_distance = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    estimated_duration = models.DurationField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Delivery Route")
        verbose_name_plural = _("Delivery Routes")

    def __str__(self):
        return f"{self.name} - {self.transporter.user.get_full_name()}"


class RouteDelivery(models.Model):
    """
    Junction table for route deliveries with order
    """

    route = models.ForeignKey(DeliveryRoute, on_delete=models.CASCADE)
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(verbose_name=_("Delivery Order"))

    class Meta:
        unique_together = ["route", "delivery"]
        ordering = ["order"]

    def __str__(self):
        return f"{self.route.name} - {self.delivery.tracking_number or self.delivery.id} (Order: {self.order})"


class DocumentType(models.TextChoices):
    """Types of documents that can be uploaded for transporters"""

    DRIVING_LICENSE = "driving_license", _("Driving License")
    VEHICLE_REGISTRATION = "vehicle_registration", _("Vehicle Registration")
    VEHICLE_INSURANCE = "vehicle_insurance", _("Vehicle Insurance")
    ID_PROOF = "id_proof", _("ID Proof")
    ADDRESS_PROOF = "address_proof", _("Address Proof")
    OTHER = "other", _("Other")


class TransporterDocument(models.Model):
    """Model to store documents related to transporters"""

    transporter = models.ForeignKey(
        Transporter, on_delete=models.CASCADE, related_name="documents", verbose_name=_("Transporter")
    )
    document_type = models.CharField(max_length=50, choices=DocumentType.choices, verbose_name=_("Document Type"))
    document_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Document Number"))
    document_file = models.FileField(
        upload_to="transporter_documents/%Y/%m/%d/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "jpg", "jpeg", "png"], message=_("Only PDF, JPG, and PNG files are allowed.")
            )
        ],
        verbose_name=_("Document File"),
    )
    issue_date = models.DateField(null=True, blank=True, verbose_name=_("Issue Date"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry Date"))
    is_verified = models.BooleanField(default=False, verbose_name=_("Is Verified"))
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_documents",
        verbose_name=_("Verified By"),
    )
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Verified At"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Verification Notes"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Transporter Document")
        verbose_name_plural = _("Transporter Documents")
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.get_document_type_display()} - {self.transporter.business_name or self.transporter.user.get_full_name()}"
        )

    def is_expired(self):
        """Check if the document is expired"""
        if not self.expiry_date:
            return False
        return timezone.now().date() > self.expiry_date

    @property
    def status(self):
        """Get document status"""
        if not self.is_verified:
            return _("Pending Verification")
        if self.is_expired():
            return _("Expired")
        return _("Valid")

    def clean(self):
        """Validate document data"""
        if self.expiry_date and self.issue_date and self.expiry_date < self.issue_date:
            raise ValidationError({"expiry_date": _("Expiry date cannot be before issue date.")})
