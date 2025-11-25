import hashlib
import hmac
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from main.enums import ChoicesMixin


class ExternalBusinessPlan(ChoicesMixin, models.TextChoices):
    """Subscription plans for external businesses"""

    FREE = "free", "Free (100 deliveries/month)"
    STARTER = "starter", "Starter (500 deliveries/month)"
    BUSINESS = "business", "Business (2000 deliveries/month)"
    ENTERPRISE = "enterprise", "Enterprise (Unlimited)"


class ExternalBusinessStatus(ChoicesMixin, models.TextChoices):
    """Status of external business registration"""

    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    SUSPENDED = "suspended", "Suspended"
    REJECTED = "rejected", "Rejected"


class ExternalDeliveryStatus(ChoicesMixin, models.TextChoices):
    """Status of external deliveries"""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted by Transporter"
    PICKED_UP = "picked_up", "Picked Up"
    IN_TRANSIT = "in_transit", "In Transit"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed Delivery"


class WebhookEventType(ChoicesMixin, models.TextChoices):
    """Types of webhook events"""

    DELIVERY_CREATED = "delivery.created", "Delivery Created"
    DELIVERY_UPDATED = "delivery.updated", "Delivery Updated"
    DELIVERY_CANCELLED = "delivery.cancelled", "Delivery Cancelled"
    DELIVERY_DELIVERED = "delivery.delivered", "Delivery Delivered"
    DELIVERY_FAILED = "delivery.failed", "Delivery Failed"


class ExternalBusiness(models.Model):
    """External business entities that integrate with our platform"""

    # Basic Information
    business_name = models.CharField(max_length=255)
    business_email = models.EmailField(unique=True)
    contact_person = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=20)
    business_address = models.TextField()

    # Technical Integration
    api_key = models.CharField(max_length=64, unique=True, blank=True)
    webhook_secret = models.CharField(max_length=64, blank=True)
    webhook_url = models.URLField(blank=True, null=True)

    # Business Details
    registration_number = models.CharField(max_length=50, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    # Subscription & Status
    plan = models.CharField(max_length=20, choices=ExternalBusinessPlan.choices, default=ExternalBusinessPlan.FREE)
    status = models.CharField(max_length=20, choices=ExternalBusinessStatus.choices, default=ExternalBusinessStatus.PENDING)

    # Rate Limiting
    rate_limit_per_minute = models.PositiveIntegerField(default=60)
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)

    # Billing
    monthly_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    per_delivery_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_external_businesses"
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_external_businesses"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Settings
    max_delivery_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("10000.00"), help_text="Maximum value of delivery allowed"
    )
    allowed_pickup_cities = models.JSONField(default=list, help_text="List of cities where pickup is allowed")
    allowed_delivery_cities = models.JSONField(default=list, help_text="List of cities where delivery is allowed")

    class Meta:
        verbose_name = "External Business"
        verbose_name_plural = "External Businesses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.get_plan_display()})"

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = self.generate_api_key()
        if not self.webhook_secret:
            self.webhook_secret = self.generate_webhook_secret()
        super().save(*args, **kwargs)

    def generate_api_key(self):
        """Generate unique API key"""
        return f"ext_{uuid.uuid4().hex[:48]}"

    def generate_webhook_secret(self):
        """Generate webhook secret for HMAC verification"""
        return uuid.uuid4().hex

    def is_active(self):
        """Check if business is active and can make API calls"""
        return self.status == ExternalBusinessStatus.APPROVED

    def can_create_delivery(self):
        """Check if business can create new deliveries based on limits"""
        if not self.is_active():
            return False, "Business not approved"

        # Check monthly delivery limit
        current_month_deliveries = self.external_deliveries.filter(
            created_at__month=timezone.now().month, created_at__year=timezone.now().year
        ).count()

        monthly_limits = {
            ExternalBusinessPlan.FREE: 100,
            ExternalBusinessPlan.STARTER: 500,
            ExternalBusinessPlan.BUSINESS: 2000,
            ExternalBusinessPlan.ENTERPRISE: float("inf"),
        }

        if current_month_deliveries >= monthly_limits.get(self.plan, 0):
            return False, f"Monthly delivery limit exceeded ({monthly_limits.get(self.plan)} deliveries)"

        return True, "OK"

    def get_usage_stats(self):
        """Get usage statistics for the current month"""
        now = timezone.now()
        current_month_deliveries = self.external_deliveries.filter(created_at__month=now.month, created_at__year=now.year)

        return {
            "current_month_deliveries": current_month_deliveries.count(),
            "current_month_revenue": sum(delivery.delivery_fee for delivery in current_month_deliveries),
            "total_deliveries": self.external_deliveries.count(),
            "successful_deliveries": self.external_deliveries.filter(status=ExternalDeliveryStatus.DELIVERED).count(),
        }


class ExternalDelivery(models.Model):
    """External delivery requests from third-party businesses"""

    # External Business Reference
    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE, related_name="external_deliveries")

    # External Reference
    external_delivery_id = models.CharField(max_length=255, help_text="External business's internal delivery ID")

    # Pickup Information
    pickup_name = models.CharField(max_length=255)
    pickup_phone = models.CharField(max_length=20)
    pickup_address = models.TextField()
    pickup_city = models.CharField(max_length=100)
    pickup_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    pickup_instructions = models.TextField(blank=True)

    # Delivery Information
    delivery_name = models.CharField(max_length=255)
    delivery_phone = models.CharField(max_length=20)
    delivery_address = models.TextField()
    delivery_city = models.CharField(max_length=100)
    delivery_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    delivery_instructions = models.TextField(blank=True)

    # Package Information
    package_description = models.TextField()
    package_weight = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))], help_text="Weight in KG"
    )
    package_value = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))], help_text="Declared value in NPR"
    )
    fragile = models.BooleanField(default=False)

    # Timing
    scheduled_pickup_time = models.DateTimeField(null=True, blank=True, help_text="Preferred pickup time")
    scheduled_delivery_time = models.DateTimeField(null=True, blank=True, help_text="Preferred delivery time")

    # Status & Tracking
    status = models.CharField(max_length=20, choices=ExternalDeliveryStatus.choices, default=ExternalDeliveryStatus.PENDING)
    tracking_number = models.CharField(max_length=50, unique=True, blank=True)

    # Internal References (after acceptance)
    assigned_transporter = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_external_deliveries"
    )

    # Pricing
    delivery_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated delivery fee"
    )
    platform_commission = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Our platform commission"
    )
    transporter_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Transporter earnings"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Additional Information
    cancellation_reason = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Validation & Quality
    is_cod = models.BooleanField(default=False, help_text="Cash on Delivery")
    cod_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.00"))]
    )

    class Meta:
        verbose_name = "External Delivery"
        verbose_name_plural = "External Deliveries"
        ordering = ["-created_at"]
        unique_together = ["external_business", "external_delivery_id"]
        indexes = [
            models.Index(fields=["tracking_number"]),
            models.Index(fields=["external_business", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"EXT-{self.tracking_number} ({self.external_business.business_name})"

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            self.tracking_number = self.generate_tracking_number()
        super().save(*args, **kwargs)

    def generate_tracking_number(self):
        """Generate unique tracking number"""
        timestamp = int(timezone.now().timestamp())
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"EXT{timestamp}{unique_id}"

    def clean(self):
        """Validate the delivery data"""
        super().clean()

        # Validate COD
        if self.is_cod and not self.cod_amount:
            raise ValidationError("COD amount is required for Cash on Delivery")
        if not self.is_cod and self.cod_amount:
            self.cod_amount = None

        # Validate cities
        if hasattr(self, "external_business"):
            allowed_pickup = self.external_business.allowed_pickup_cities
            allowed_delivery = self.external_business.allowed_delivery_cities

            if allowed_pickup and self.pickup_city not in allowed_pickup:
                raise ValidationError(f"Pickup city '{self.pickup_city}' not allowed")

            if allowed_delivery and self.delivery_city not in allowed_delivery:
                raise ValidationError(f"Delivery city '{self.delivery_city}' not allowed")

            # Validate package value
            if self.package_value > self.external_business.max_delivery_value:
                raise ValidationError(
                    f"Package value exceeds maximum allowed value of " f"{self.external_business.max_delivery_value}"
                )

    def calculate_delivery_fee(self):
        """Calculate delivery fee based on distance, weight, and value"""
        # Basic calculation logic - can be enhanced
        base_fee = Decimal("100.00")  # Base fee in NPR

        # Weight-based calculation
        weight_fee = self.package_weight * Decimal("10.00")  # 10 NPR per kg

        # Value-based calculation (0.5% of package value, min 50 NPR)
        value_fee = max(self.package_value * Decimal("0.005"), Decimal("50.00"))

        # City-based calculation (simplified)
        city_multiplier = Decimal("1.0")
        if self.pickup_city != self.delivery_city:
            city_multiplier = Decimal("1.5")  # Inter-city delivery

        total_fee = (base_fee + weight_fee + value_fee) * city_multiplier

        # Platform commission (20%)
        platform_commission = total_fee * Decimal("0.20")
        transporter_earnings = total_fee - platform_commission

        return {
            "delivery_fee": total_fee,
            "platform_commission": platform_commission,
            "transporter_earnings": transporter_earnings,
        }

    def can_cancel(self):
        """Check if delivery can be cancelled"""
        non_cancellable_statuses = [
            ExternalDeliveryStatus.PICKED_UP,
            ExternalDeliveryStatus.IN_TRANSIT,
            ExternalDeliveryStatus.DELIVERED,
            ExternalDeliveryStatus.CANCELLED,
            ExternalDeliveryStatus.FAILED,
        ]
        return self.status not in non_cancellable_statuses

    def update_status(self, new_status, reason=None, user=None):
        """Update delivery status with validation"""
        old_status = self.status

        # Validate status transition
        valid_transitions = {
            ExternalDeliveryStatus.PENDING: [ExternalDeliveryStatus.ACCEPTED, ExternalDeliveryStatus.CANCELLED],
            ExternalDeliveryStatus.ACCEPTED: [ExternalDeliveryStatus.PICKED_UP, ExternalDeliveryStatus.CANCELLED],
            ExternalDeliveryStatus.PICKED_UP: [
                ExternalDeliveryStatus.IN_TRANSIT,
                ExternalDeliveryStatus.DELIVERED,
                ExternalDeliveryStatus.FAILED,
            ],
            ExternalDeliveryStatus.IN_TRANSIT: [ExternalDeliveryStatus.DELIVERED, ExternalDeliveryStatus.FAILED],
        }

        if old_status in valid_transitions and new_status not in valid_transitions[old_status]:
            raise ValidationError(f"Invalid status transition from {old_status} to {new_status}")

        self.status = new_status
        now = timezone.now()

        # Update timestamps
        if new_status == ExternalDeliveryStatus.ACCEPTED:
            self.accepted_at = now
        elif new_status == ExternalDeliveryStatus.PICKED_UP:
            self.picked_up_at = now
        elif new_status == ExternalDeliveryStatus.DELIVERED:
            self.delivered_at = now
        elif new_status == ExternalDeliveryStatus.CANCELLED:
            self.cancelled_at = now
            if reason:
                self.cancellation_reason = reason
        elif new_status == ExternalDeliveryStatus.FAILED:
            if reason:
                self.failure_reason = reason

        self.save()

        # Create status history
        ExternalDeliveryStatusHistory.objects.create(
            delivery=self, old_status=old_status, new_status=new_status, reason=reason, changed_by=user
        )


class ExternalDeliveryStatusHistory(models.Model):
    """Track status changes for external deliveries"""

    delivery = models.ForeignKey(ExternalDelivery, on_delete=models.CASCADE, related_name="status_history")
    old_status = models.CharField(max_length=20, choices=ExternalDeliveryStatus.choices)
    new_status = models.CharField(max_length=20, choices=ExternalDeliveryStatus.choices)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Delivery Status History"
        verbose_name_plural = "Delivery Status Histories"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.delivery.tracking_number}: {self.old_status} → {self.new_status}"


class APIUsageLog(models.Model):
    """Log API usage for billing and monitoring"""

    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE, related_name="api_usage_logs")
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    request_ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    request_size = models.PositiveIntegerField(default=0)
    response_status = models.PositiveIntegerField()
    response_size = models.PositiveIntegerField(default=0)
    response_time = models.DecimalField(max_digits=10, decimal_places=3, help_text="Response time in seconds")
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional request/response data for debugging
    request_data = models.JSONField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "API Usage Log"
        verbose_name_plural = "API Usage Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_business", "created_at"]),
            models.Index(fields=["endpoint", "created_at"]),
        ]

    def __str__(self):
        return f"{self.external_business.business_name} - {self.method} {self.endpoint}"


class WebhookLog(models.Model):
    """Log webhook delivery attempts"""

    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE, related_name="webhook_logs")
    delivery = models.ForeignKey(
        ExternalDelivery, on_delete=models.CASCADE, related_name="webhook_logs", null=True, blank=True
    )
    event_type = models.CharField(max_length=50, choices=WebhookEventType.choices)
    webhook_url = models.URLField()
    payload = models.JSONField()

    # Response Information
    response_status = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    response_time = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True, help_text="Response time in seconds"
    )

    # Delivery Status
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Webhook Log"
        verbose_name_plural = "Webhook Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_business", "success"]),
            models.Index(fields=["next_retry_at"]),
        ]

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.external_business.business_name} - {self.event_type}"


class RateLimitLog(models.Model):
    """Track rate limiting for external businesses"""

    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE, related_name="rate_limit_logs")
    request_ip = models.GenericIPAddressField()
    endpoint = models.CharField(max_length=255)
    request_count = models.PositiveIntegerField(default=1)
    time_window = models.CharField(max_length=10, choices=[("minute", "Minute"), ("hour", "Hour")], default="minute")
    blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rate Limit Log"
        verbose_name_plural = "Rate Limit Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_business", "time_window", "created_at"]),
        ]

    def __str__(self):
        return f"{self.external_business.business_name} - {self.request_count} requests"
