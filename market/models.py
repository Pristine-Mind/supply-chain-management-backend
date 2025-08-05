import re
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, validate_email
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from reversion.models import Version

try:
    from babel.numbers import format_currency
except ImportError:
    format_currency = None

from producer.models import City, MarketplaceProduct


class Purchase(models.Model):
    """
    Represents a purchase made by a customer from the marketplace.

    Fields:
    - buyer: The customer who bought the product.
    - product: The product that was purchased.
    - quantity: The number of items purchased.
    - purchase_price: The price at which the product was purchased.
    - purchase_date: The date of the purchase.
    """

    buyer = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Buyer"))
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, verbose_name=_("Product"))
    quantity = models.PositiveIntegerField(verbose_name=_("Quantity"))
    purchase_price = models.FloatField(verbose_name=_("Purchase Price"))
    purchase_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Purchase Date"))

    def __str__(self):
        return f"{self.buyer.username} bought {self.quantity} of {self.product.product.name}"

    class Meta:
        verbose_name = _("Purchase")
        verbose_name_plural = _("Purchases")


class Payment(models.Model):
    """
    Represents a payment made by a customer for a purchase through eSewa.

    Fields:
    - purchase: The associated purchase for which payment is being made.
    - transaction_id: A unique transaction ID for the payment (generated when payment is initiated).
    - amount: The total amount paid.
    - payment_date: The date and time when the payment was made.
    - status: The status of the payment (e.g., pending, completed, failed).
    """

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("esewa", "eSewa"),
        ("khalti", "Khalti"),
    ]

    purchase = models.OneToOneField("Purchase", on_delete=models.CASCADE, verbose_name=_("Purchase"))
    transaction_id = models.CharField(max_length=100, unique=True, verbose_name=_("Transaction ID"))
    amount = models.FloatField(verbose_name=_("Amount"))
    payment_date = models.DateTimeField(default=timezone.now, verbose_name=_("Payment Date"))
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending", verbose_name=_("Status"))
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name=_("Payment Method"), default="esewa"
    )

    def __str__(self):
        return f"eSewa Payment for {self.purchase} ({self.status})"

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")


class Bid(models.Model):
    """
    Represents a bid placed on a marketplace product by a customer.

    Fields:
    - bidder: The customer placing the bid.
    - product: The product being bid on.
    - bid_amount: The amount offered for the product.
    - max_bid_amount: The maximum amount the bidder is willing to pay.
    - bid_date: The date the bid was placed.
    """

    bidder = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Bidder"))
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, verbose_name=_("Product"))
    bid_amount = models.FloatField(verbose_name=_("Bid Amount"))
    max_bid_amount = models.FloatField(verbose_name=_("Maximum Bid Amount"))
    bid_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Bid Date"))

    def __str__(self):
        return f"{self.bidder.username} bid {self.bid_amount} on {self.product.product.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Notify the seller about the new bid
        Notification.objects.create(
            user=self.product.product.user,
            message=f"New bid of NPR {self.bid_amount} by {self.bidder.username} on your product {self.product.product.name}",
        )

    class Meta:
        verbose_name = _("Bid")
        verbose_name_plural = _("Bids")


class ChatMessage(models.Model):
    """
    Represents a chat message related to a marketplace product.
    Fields:
    - sender: The user who sent the message.
    - product: The product being discussed.
    - message: The content of the message.
    - timestamp: The time the message was sent.
    """

    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Sender"))
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, verbose_name=_("Product"))
    message = models.TextField(verbose_name=_("Message"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Timestamp"))

    def __str__(self):
        return f"Message from {self.sender.username} about {self.product.product.name}"

    class Meta:
        verbose_name = _("Chat Message")
        verbose_name_plural = _("Chat Messages")


class ShippingAddress(models.Model):
    """
    Represents the shipping address for a purchase.
    Fields:
    - payment: The payment associated with the shipping address.
    - address_line_1: The first line of the shipping address.
    - address_line_2: The second line of the shipping address (optional).
    - city: The city of the shipping address.
    - state: The state of the shipping address.
    - postal_code: The postal code of the shipping address.
    """

    payment = models.OneToOneField(Payment, on_delete=models.CASCADE)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.address_line_1}, {self.city}, {self.state}, {self.country}"

    class Meta:
        verbose_name = _("Shipping Address")
        verbose_name_plural = _("Shipping Addresses")


class MarketplaceUserProduct(models.Model):
    class ProductCategory(models.TextChoices):
        FRUITS = "FR", "Fruits"
        VEGETABLES = "VG", "Vegetables"
        GRAINS_AND_CEREALS = "GR", "Grains & Cereals"
        PULSES_AND_LEGUMES = "PL", "Pulses & Legumes"
        SPICES_AND_HERBS = "SP", "Spices & Herbs"
        NUTS_AND_SEEDS = "NT", "Nuts & Seeds"
        DAIRY_AND_ANIMAL_PRODUCTS = "DF", "Dairy & Animal Products"
        FODDER_AND_FORAGE = "FM", "Fodder & Forage"
        FLOWERS_AND_ORNAMENTAL_PLANTS = "FL", "Flowers & Ornamental Plants"
        HERBS_AND_MEDICINAL_PLANTS = "HR", "Herbs & Medicinal Plants"
        OTHER = "OT", "Other"

    class ProductUnit(models.TextChoices):
        KILOGRAM = "KG", "Kilogram"
        LITER = "LT", "Liter"

    name = models.CharField(_("Name"), max_length=255)
    description = models.TextField(_("Description"))
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(_("Stock"))
    category = models.CharField(
        verbose_name=_("Category"),
        max_length=2,
        choices=ProductCategory.choices,
        default=ProductCategory.VEGETABLES,
    )
    unit = models.CharField(
        verbose_name=_("Unit"),
        max_length=2,
        choices=ProductUnit.choices,
        default=ProductUnit.KILOGRAM,
    )
    is_verified = models.BooleanField(_("Is Verified"), default=False)
    is_sold = models.BooleanField(_("Is Sold"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Seller"))
    location = models.ForeignKey(
        City,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Location"),
        help_text="Location of the product",
    )

    class Meta:
        verbose_name = _("Marketplace User Product")
        verbose_name_plural = _("Marketplace User Products")

    def __str__(self):
        return self.name


class UserProductImage(models.Model):
    product = models.ForeignKey(
        MarketplaceUserProduct, on_delete=models.CASCADE, related_name="images", verbose_name=_("Product")
    )
    image = models.ImageField(_("Image"), upload_to="marketplace/products/%Y/%m/%d/")
    alt_text = models.CharField(_("Alt Text"), max_length=255, blank=True, help_text="Alternative text for accessibility")
    order = models.PositiveSmallIntegerField(_("Display Order"), default=0, help_text="Order of images for carousel display")

    class Meta:
        ordering = ["order"]
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")

    def __str__(self):
        return f"{self.product.name} - Image {self.order}"


class Notification(models.Model):
    class Type(models.TextChoices):
        ORDER = "order", _("Order")
        SALE = "sale", _("Sale")
        PURCHASE_ORDER = "po", _("Purchase Order")
        STOCK = "stock", _("Stock")
        MARKETPLACE = "marketplace", _("Marketplace")
        ALERT = "alert", _("Alert")

    class Channel(models.TextChoices):
        IN_APP = "in_app", _("In-App")
        EMAIL = "email", _("Email")
        SMS = "sms", _("SMS")

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notification_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.ALERT,
        verbose_name=_("Notification Type"),
    )
    channel = models.CharField(
        max_length=10,
        choices=Channel.choices,
        verbose_name=_("Channel"),
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.notification_type}] ({self.channel}) {self.message[:30]}"


class Feedback(models.Model):
    """
    This model collects user feedback (e.g., rating or comment) on recommended products.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedbacks")
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, related_name="feedbacks")
    rating = models.IntegerField(default=1)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback by {self.user.username} on {self.product.product.name}"


class UserInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    event_type = models.CharField(max_length=100, help_text="Type of event (e.g., 'click', 'page_view')")
    data = models.JSONField(blank=True, null=True, help_text="Additional event details (e.g., element info, coordinates)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="carts")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart {self.id} for {self.user.username if self.user else 'Guest'}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.product} in Cart {self.cart.id}"


class Delivery(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="delivery")
    customer_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"Delivery for {self.customer_name} - {self.city}"


class SaleStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    SHIPPED = "shipped", _("Shipped")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    REFUNDED = "refunded", _("Refunded")

    @classmethod
    def get_next_allowed_statuses(cls, current_status):
        """Returns a list of statuses that can be transitioned to from the current status."""
        status_flow = {
            cls.PENDING: [cls.PROCESSING, cls.CANCELLED],
            cls.PROCESSING: [cls.SHIPPED, cls.CANCELLED],
            cls.SHIPPED: [cls.DELIVERED, cls.REFUNDED],
            cls.DELIVERED: [cls.REFUNDED],
            cls.CANCELLED: [],
            cls.REFUNDED: [],
        }
        return status_flow.get(current_status, [])


class PaymentStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PAID = "paid", _("Paid")
    FAILED = "failed", _("Failed")
    REFUNDED = "refunded", _("Refunded")
    PARTIALLY_REFUNDED = "partially_refunded", _("Partially Refunded")


class Currency(models.TextChoices):
    USD = "USD", _("US Dollar")
    EUR = "EUR", _("Euro")
    GBP = "GBP", _("British Pound")
    JPY = "JPY", _("Japanese Yen")
    AUD = "AUD", _("Australian Dollar")
    CAD = "CAD", _("Canadian Dollar")
    CHF = "CHF", _("Swiss Franc")
    CNY = "CNY", _("Chinese Yuan")
    INR = "INR", _("Indian Rupee")
    NPR = "NPR", _("Nepalese Rupee")


class MarketplaceSaleQuerySet(models.QuerySet):
    """Custom QuerySet for MarketplaceSale with common queries."""

    def with_related(self):
        """Optimize related object fetching."""
        return self.select_related("buyer", "seller", "product", "product__category").prefetch_related("delivery_set")

    def active(self):
        """Return only non-deleted sales."""
        return self.filter(is_deleted=False)

    def for_buyer(self, user):
        """Filter sales for a specific buyer."""
        return self.filter(Q(buyer=user) | Q(buyer_email=user.email))

    def for_seller(self, user):
        """Filter sales for a specific seller."""
        return self.filter(seller=user)


class MarketplaceSaleManager(models.Manager):
    """Custom manager for MarketplaceSale model."""

    def get_queryset(self):
        return MarketplaceSaleQuerySet(self.model, using=self._db)

    def with_related(self):
        return self.get_queryset().with_related()

    def active(self):
        return self.get_queryset().active()

    def for_buyer(self, user):
        return self.get_queryset().for_buyer(user)

    def for_seller(self, user):
        return self.get_queryset().for_seller(user)

    @transaction.atomic
    def create_sale(self, **kwargs):
        """Create a new sale with transaction handling."""
        return self.create(**kwargs)


class MarketplaceSale(models.Model):
    """
    Tracks sales transactions in the marketplace.
    Supports both authenticated and anonymous buyers.
    """

    # Custom manager
    objects = MarketplaceSaleManager()
    # Basic Information
    order_number = models.CharField(max_length=50, unique=True, editable=False, verbose_name=_("Order Number"))
    sale_date = models.DateTimeField(default=timezone.now, verbose_name=_("Sale Date"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated"))
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD, verbose_name=_("Currency"))

    # Buyer and Seller Information
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketplace_purchases",
        verbose_name=_("Buyer"),
        null=True,
        blank=True,
        help_text=_("Leave empty for anonymous buyers"),
    )
    buyer_name = models.CharField(
        max_length=255, verbose_name=_("Buyer's Name"), blank=True, help_text=_("Required for anonymous buyers")
    )
    buyer_email = models.EmailField(verbose_name=_("Buyer's Email"), blank=True, help_text=_("Required for order updates"))
    buyer_phone = PhoneNumberField(
        verbose_name=_("Buyer's Phone"), blank=True, help_text=_("Required for delivery coordination")
    )

    # Soft delete fields
    is_deleted = models.BooleanField(default=False, verbose_name=_("Is Deleted"))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Deleted At"))
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="marketplace_sales", verbose_name=_("Seller"))

    # Product Information
    product = models.ForeignKey(
        MarketplaceProduct, on_delete=models.PROTECT, related_name="sales", verbose_name=_("Product")
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name=_("Quantity"))
    unit_price_at_purchase = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Unit Price at Purchase"))

    # Pricing
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Unit Price"))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Subtotal"))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Tax Amount"))
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Shipping Cost"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total Amount"))

    # Status
    status = models.CharField(
        max_length=20, choices=SaleStatus.choices, default=SaleStatus.PENDING, verbose_name=_("Sale Status")
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, verbose_name=_("Payment Status")
    )

    class Meta:
        verbose_name = _("Marketplace Sale")
        verbose_name_plural = _("Marketplace Sales")
        ordering = ["-sale_date"]
        indexes = [
            models.Index(fields=["order_number"]),
            models.Index(fields=["buyer"]),
            models.Index(fields=["seller"]),
            models.Index(fields=["status", "payment_status"]),
            models.Index(fields=["is_deleted", "deleted_at"]),
            models.Index(fields=["sale_date"]),
        ]
        permissions = [
            ("view_history", "Can view sale history"),
        ]

    # Reversion configuration
    @property
    def versions(self):
        """Proxy to get versions for this instance."""
        return Version.objects.get_for_object(self)

    def get_previous_version(self):
        """Get the previous version of this instance."""
        versions = self.versions
        if versions.count() > 1:
            return versions[1].field_dict
        return None

    # Payment Information
    payment_method = models.CharField(max_length=50, verbose_name=_("Payment Method"), blank=True, null=True)
    transaction_id = models.CharField(max_length=100, verbose_name=_("Transaction ID"), blank=True, null=True)

    # Delivery Information
    delivery = models.OneToOneField(
        Delivery, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale", verbose_name=_("Delivery Details")
    )

    # Additional Information
    notes = models.TextField(blank=True, null=True, verbose_name=_("Order Notes"))

    class Meta:
        verbose_name = _("Marketplace Sale")
        verbose_name_plural = _("Marketplace Sales")
        ordering = ["-sale_date"]

    def __str__(self):
        return f"Sale #{self.order_number} - {self.buyer.username} - {self.product.name}"

    def clean(self):
        """Validate model fields before saving."""
        super().clean()

        # Validate buyer information
        if not self.buyer and not (self.buyer_name and self.buyer_email and self.buyer_phone):
            raise ValidationError(
                {
                    "buyer_name": "Required for anonymous buyers",
                    "buyer_email": "Required for order updates",
                    "buyer_phone": "Required for delivery coordination",
                }
            )

        # Validate email format
        if self.buyer_email:
            try:
                validate_email(self.buyer_email)
            except ValidationError:
                raise ValidationError({"buyer_email": "Enter a valid email address."})

        # Validate prices
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})

        if self.unit_price_at_purchase < 0 or self.tax_amount < 0 or self.shipping_cost < 0:
            raise ValidationError("Prices cannot be negative.")

        # Validate status transitions if this is an existing instance
        if self.pk:
            old_instance = MarketplaceSale.objects.get(pk=self.pk)
            self._validate_status_transition(old_instance.status, self.status)
            self._validate_payment_status(old_instance.payment_status, self.payment_status)

    def _validate_status_transition(self, old_status, new_status):
        """Validate if the status transition is allowed."""
        if old_status == new_status:
            return

        if new_status not in SaleStatus.get_next_allowed_statuses(old_status):
            raise ValidationError(f"Cannot change status from {old_status} to {new_status}.")

    def _validate_payment_status(self, old_status, new_status):
        """Validate payment status changes."""
        if old_status == new_status:
            return

        if self.status == SaleStatus.DELIVERED and new_status != PaymentStatus.PAID:
            raise ValidationError("Cannot mark as delivered with unpaid order.")

    def save(self, *args, **kwargs):
        """Save the model with additional validations and auto-fields."""
        self.full_clean()

        # Generate order number if not set
        if not self.order_number:
            self.order_number = f"ORD-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Set unit price at purchase
        if not self.pk and not hasattr(self, "unit_price_at_purchase"):
            self.unit_price_at_purchase = self.product.price

        # Calculate subtotal
        if not hasattr(self, "subtotal") or not self.subtotal:
            self.subtotal = self.unit_price_at_purchase * self.quantity

        # Calculate total amount
        if not hasattr(self, "total_amount") or not self.total_amount:
            self.total_amount = self.subtotal + (self.tax_amount or 0) + (self.shipping_cost or 0)

        # Sync user information
        if self.buyer:
            if not self.buyer_name and self.buyer.get_full_name():
                self.buyer_name = self.buyer.get_full_name()
            if not self.buyer_email and self.buyer.email:
                self.buyer_email = self.buyer.email

        # Update stock if quantity changes
        if self.pk:
            old_instance = MarketplaceSale.objects.get(pk=self.pk)
            if old_instance.quantity != self.quantity:
                self.product.stock += old_instance.quantity - self.quantity
                self.product.save()

        super().save(*args, **kwargs)

    # Soft delete implementation
    def delete(self, using=None, keep_parents=False, **kwargs):
        """Soft delete the sale."""
        if not self.is_deleted:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=["is_deleted", "deleted_at"])

            # Return stock if not already delivered
            if self.status != SaleStatus.DELIVERED:
                self.product.stock += self.quantity
                self.product.save()

    def hard_delete(self, *args, **kwargs):
        """Permanently delete the sale."""
        super().delete(*args, **kwargs)

    # Status check properties
    @property
    def is_paid(self):
        """Check if the sale is paid."""
        return self.payment_status == PaymentStatus.PAID

    @property
    def is_delivered(self):
        """Check if the sale is delivered."""
        return self.status == SaleStatus.DELIVERED

    @property
    def can_cancel(self):
        """Check if the sale can be cancelled."""
        return self.status in [SaleStatus.PENDING, SaleStatus.PROCESSING]

    @property
    def can_refund(self):
        """Check if the sale can be refunded."""
        return self.payment_status == PaymentStatus.PAID and self.status != SaleStatus.REFUNDED

    # Buyer information properties
    @property
    def buyer_display_name(self):
        """Returns the buyer's display name."""
        if self.buyer:
            return self.buyer.get_full_name() or self.buyer.username or "Anonymous Buyer"
        return self.buyer_name or "Anonymous Buyer"

    @property
    def buyer_contact_email(self):
        """Returns the buyer's contact email."""
        if self.buyer and self.buyer.email:
            return self.buyer.email
        return self.buyer_email

    @property
    def masked_email(self):
        """Returns a masked version of the email for display."""
        if not self.buyer_email:
            return "-"
        name, domain = self.buyer_email.split("@")
        return f"{name[0]}***{name[-1]}@{domain}"

    # Price formatting
    def format_price(self, amount):
        """Format price according to the currency."""
        if format_currency:
            return format_currency(amount, self.currency, locale=settings.LANGUAGE_CODE)
        return f"{self.currency} {amount:.2f}"

    @property
    def formatted_subtotal(self):
        """Returns formatted subtotal."""
        return self.format_price(self.subtotal)

    @property
    def formatted_tax(self):
        """Returns formatted tax amount."""
        return self.format_price(self.tax_amount or 0)

    @property
    def formatted_shipping(self):
        """Returns formatted shipping cost."""
        return self.format_price(self.shipping_cost or 0)

    @property
    def formatted_total(self):
        """Returns formatted total amount."""
        return self.format_price(self.total_amount)

    # Actions
    @transaction.atomic
    def mark_as_paid(self, payment_id=None, payment_method=None):
        """Mark the sale as paid."""
        if self.payment_status == PaymentStatus.PAID:
            return  # Already paid

        self.payment_status = PaymentStatus.PAID
        if payment_id:
            self.transaction_id = payment_id
        if payment_method:
            self.payment_method = payment_method
        self.save()

    @transaction.atomic
    def mark_as_delivered(self):
        """Mark the sale as delivered."""
        if self.status == SaleStatus.DELIVERED:
            return  # Already delivered

        if self.payment_status != PaymentStatus.PAID:
            raise ValidationError("Cannot mark as delivered with unpaid order.")

        self.status = SaleStatus.DELIVERED
        self.save()

    @transaction.atomic
    def process_refund(self, amount=None, reason=None):
        """Process a refund for the sale."""
        if not self.can_refund:
            raise ValidationError("This sale cannot be refunded.")

        if amount is None or amount == self.total_amount:
            # Full refund
            self.payment_status = PaymentStatus.REFUNDED
            self.status = SaleStatus.REFUNDED
        else:
            # Partial refund
            self.payment_status = PaymentStatus.PARTIALLY_REFUNDED

        if reason:
            self.notes = f"{self.notes or ''}\nRefund reason: {reason}"

        self.save()

    # Model constraints
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(buyer__isnull=False)
                    | (models.Q(buyer_name__gt="") & models.Q(buyer_email__contains="@") & models.Q(buyer_phone__gt=""))
                ),
                name="valid_buyer_info",
                violation_error_message="Either provide a registered buyer or complete buyer information.",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name="positive_quantity",
                violation_error_message="Quantity must be greater than zero.",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(unit_price_at_purchase__gte=0) & models.Q(tax_amount__gte=0) & models.Q(shipping_cost__gte=0)
                ),
                name="non_negative_prices",
                violation_error_message="Prices cannot be negative.",
            ),
        ]

    def __str__(self):
        return f"Order #{self.order_number}"

    def get_absolute_url(self):
        """Get the URL for the order detail view."""
        return reverse("market:sale-detail", kwargs={"order_number": self.order_number})


class ProductView(models.Model):
    """
    Logs a view of a marketplace product for analytics and ranking.
    We dedupe by (product, session) within a short window to avoid spam.
    """

    product = models.ForeignKey(
        MarketplaceProduct, on_delete=models.CASCADE, related_name="views", verbose_name="Viewed Product"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Viewing User"
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, verbose_name="Session Key")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Address")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="User Agent")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Viewed At")

    class Meta:
        indexes = [
            models.Index(fields=["product", "timestamp"]),
            models.Index(fields=["session_key", "timestamp"]),
        ]
        verbose_name = "Product View"
        verbose_name_plural = "Product Views"

    def __str__(self):
        who = self.user.username if self.user else self.session_key or "anon"
        return f"{who} viewed {self.product} at {self.timestamp}"
