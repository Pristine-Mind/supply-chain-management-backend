import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MinValueValidator,
    validate_email,
)
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

from producer.models import City, MarketplaceProduct, Sale


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
        _ = Notification.objects.create(
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
        FASHION_APPAREL = "FA", "Fashion & Apparel"
        ELECTRONICS_GADGETS = "EG", "Electronics & Gadgets"
        GROCERIES_ESSENTIALS = "GE", "Groceries & Essentials"
        HEALTH_BEAUTY = "HB", "Health & Beauty"
        HOME_LIVING = "HL", "Home & Living"
        TRAVEL_TOURISM = "TT", "Travel & Tourism"
        INDUSTRIAL_SUPPLIES = "IS", "Industrial Supplies"
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
        default=ProductCategory.OTHER,
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
    # Cart relationship (nullable for deliveries created from sales)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="delivery", null=True, blank=True)

    # Sale relationship (for deliveries created directly from producer sales)
    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="deliveries", null=True, blank=True, verbose_name=_("Sale")
    )

    # MarketplaceSale relationship (for deliveries created from marketplace sales)
    marketplace_sale = models.ForeignKey(
        "MarketplaceSale",
        on_delete=models.CASCADE,
        related_name="direct_deliveries",
        null=True,
        blank=True,
        verbose_name=_("Marketplace Sale"),
    )

    # Order relationship (for deliveries created from marketplace orders)
    marketplace_order = models.ForeignKey(
        "MarketplaceOrder",
        on_delete=models.CASCADE,
        related_name="order_deliveries",
        null=True,
        blank=True,
        verbose_name=_("Marketplace Order"),
    )

    # Customer information
    customer_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.CharField(max_length=255)

    # Delivery address
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Additional information
    additional_instructions = models.TextField(blank=True, null=True)
    shop_id = models.CharField(max_length=100, blank=True, null=True)

    # Delivery tracking
    delivery_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", _("Pending")),
            ("assigned", _("Assigned")),
            ("picked_up", _("Picked Up")),
            ("in_transit", _("In Transit")),
            ("delivered", _("Delivered")),
            ("failed", _("Failed")),
            ("cancelled", _("Cancelled")),
        ],
        default="pending",
        verbose_name=_("Delivery Status"),
    )

    # Delivery person/service information
    delivery_person_name = models.CharField(max_length=255, blank=True, null=True)
    delivery_person_phone = models.CharField(max_length=20, blank=True, null=True)
    delivery_service = models.CharField(max_length=100, blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True, unique=True)

    # Estimated and actual delivery times
    estimated_delivery_date = models.DateTimeField(null=True, blank=True)
    actual_delivery_date = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Delivery")
        verbose_name_plural = _("Deliveries")
        indexes = [
            models.Index(fields=["delivery_status"]),
            models.Index(fields=["tracking_number"]),
            models.Index(fields=["created_at"]),
        ]

    def clean(self):
        """Validate that at least one of cart, sale, marketplace_sale, or marketplace_order is provided."""
        if not any([self.cart, self.sale, self.marketplace_sale, self.marketplace_order]):
            raise ValidationError("At least one of cart, sale, marketplace_sale, or marketplace_order must be provided.")

    def __str__(self):
        return f"Delivery for {self.customer_name} - {self.city} ({self.get_delivery_status_display()})"

    @property
    def delivery_source(self):
        """Return the source of this delivery (cart, sale, marketplace_sale, or order)."""
        if self.cart:
            return f"Cart #{self.cart.id}"
        elif self.sale:
            return f"Sale #{self.sale.id} (Order: {self.sale.order.order_number})"
        elif self.marketplace_sale:
            return f"Marketplace Sale #{self.marketplace_sale.order_number}"
        elif self.marketplace_order:
            return f"Order #{self.marketplace_order.order_number}"
        return "Unknown source"

    @property
    def total_items(self):
        """Calculate total number of items in this delivery."""
        if self.cart:
            return sum(item.quantity for item in self.cart.items.all())
        elif self.sale:
            return self.sale.quantity
        elif self.marketplace_sale:
            return self.marketplace_sale.quantity
        elif self.marketplace_order:
            return sum(item.quantity for item in self.marketplace_order.items.all())
        return 0

    @property
    def total_value(self):
        """Calculate total value of items in this delivery."""
        if self.cart:
            return sum(item.product.price * item.quantity for item in self.cart.items.all())
        elif self.sale:
            return self.sale.sale_price * self.sale.quantity
        elif self.marketplace_sale:
            return self.marketplace_sale.total_amount
        elif self.marketplace_order:
            return self.marketplace_order.total_amount
        return 0

    @property
    def product_details(self):
        """Get details about the products in this delivery."""
        if self.cart:
            return [{"name": item.product.product.name, "quantity": item.quantity} for item in self.cart.items.all()]
        elif self.sale:
            return [{"name": self.sale.order.product.name, "quantity": self.sale.quantity}]
        elif self.marketplace_sale:
            return [{"name": self.marketplace_sale.product.product.name, "quantity": self.marketplace_sale.quantity}]
        elif self.marketplace_order:
            return [
                {"name": item.product.product.name, "quantity": item.quantity} for item in self.marketplace_order.items.all()
            ]
        return []


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
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name=_("Tax Amount"))
    shipping_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name=_("Shipping Cost")
    )
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
        Delivery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_sale_delivery",
        verbose_name=_("Delivery Details"),
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

        # Track status change for creating tracking events post-save
        old_status = None
        is_create = self.pk is None
        if not is_create:
            try:
                old_status = MarketplaceSale.objects.only("status").get(pk=self.pk).status
            except MarketplaceSale.DoesNotExist:
                old_status = None

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
                self.product.product.stock += old_instance.quantity - self.quantity
                self.product.product.save()

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
                self.product.product.stock += self.quantity
                self.product.product.save()

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


# Extended marketplace order status choices for better granularity
class OrderStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    CONFIRMED = "confirmed", _("Confirmed")
    PROCESSING = "processing", _("Processing")
    SHIPPED = "shipped", _("Shipped")
    IN_TRANSIT = "in_transit", _("In Transit")
    DELIVERED = "delivered", _("Delivered")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    FAILED = "failed", _("Failed")

    @classmethod
    def get_next_allowed_statuses(cls, current_status):
        """Returns a list of statuses that can be transitioned to from the current status."""
        status_flow = {
            cls.PENDING: [cls.CONFIRMED, cls.CANCELLED],
            cls.CONFIRMED: [cls.PROCESSING, cls.CANCELLED],
            cls.PROCESSING: [cls.SHIPPED, cls.CANCELLED],
            cls.SHIPPED: [cls.IN_TRANSIT, cls.DELIVERED],
            cls.IN_TRANSIT: [cls.DELIVERED],
            cls.DELIVERED: [cls.COMPLETED],
            cls.COMPLETED: [],
            cls.CANCELLED: [],
            cls.FAILED: [],
        }
        return status_flow.get(current_status, [])


class MarketplaceOrderQuerySet(models.QuerySet):
    """Custom QuerySet for MarketplaceOrder with common queries."""

    def with_related(self):
        """Optimize related object fetching."""
        return self.select_related("customer", "delivery").prefetch_related(
            "items__product__product_details", "items__product__product_details__images", "tracking_events"
        )

    def active(self):
        """Return only non-deleted orders."""
        return self.filter(is_deleted=False)

    def for_customer(self, user):
        """Filter orders for a specific customer."""
        return self.filter(customer=user)

    def by_status(self, status):
        """Filter orders by status."""
        return self.filter(order_status=status)

    def by_payment_status(self, status):
        """Filter orders by payment status."""
        return self.filter(payment_status=status)


class MarketplaceOrderManager(models.Manager):
    """Custom manager for MarketplaceOrder model."""

    def get_queryset(self):
        return MarketplaceOrderQuerySet(self.model, using=self._db)

    def with_related(self):
        return self.get_queryset().with_related()

    def active(self):
        return self.get_queryset().active()

    def for_customer(self, user):
        return self.get_queryset().for_customer(user)

    @transaction.atomic
    def create_order(self, **kwargs):
        """Create a new order with transaction handling."""
        return self.create(**kwargs)

    @transaction.atomic
    def create_order_from_cart(self, cart, delivery_info, payment_method=None):
        """
        Create a new order from cart items.

        Args:
            cart: Cart instance with items
            delivery_info: DeliveryInfo instance
            payment_method: Optional payment method

        Returns:
            MarketplaceOrder instance
        """
        if not cart.items.exists():
            raise ValidationError("Cannot create order from empty cart.")

        # Calculate total amount
        total_amount = sum(
            (item.product.discounted_price or item.product.listed_price) * item.quantity for item in cart.items.all()
        )

        # Create the order
        order = self.create(
            customer=cart.user,
            delivery=delivery_info,
            total_amount=total_amount,
            payment_method=payment_method,
        )

        # Create order items from cart items
        for cart_item in cart.items.all():
            _ = MarketplaceOrderItem.objects.create(
                order=order,
                product=cart_item.product,
                quantity=cart_item.quantity,
                unit_price=cart_item.product.discounted_price or cart_item.product.listed_price,
            )

            # Update product stock (access the underlying Product model)
            cart_item.product.product.stock -= cart_item.quantity
            cart_item.product.product.save()

        # Create initial tracking event
        _ = OrderTrackingEvent.objects.create(
            marketplace_order=order, status=OrderStatus.PENDING, message="Order created successfully"
        )

        return order


class DeliveryInfo(models.Model):
    """
    Delivery information for marketplace orders.
    Separated from the order to allow for multiple delivery addresses in the future.
    """

    customer_name = models.CharField(max_length=255, verbose_name=_("Customer Name"))
    phone_number = models.CharField(max_length=20, verbose_name=_("Phone Number"))
    address = models.TextField(verbose_name=_("Address"))
    city = models.CharField(max_length=100, verbose_name=_("City"))
    state = models.CharField(max_length=100, verbose_name=_("State"))
    zip_code = models.CharField(max_length=20, verbose_name=_("ZIP Code"))
    latitude = models.FloatField(verbose_name=_("Latitude"))
    longitude = models.FloatField(verbose_name=_("Longitude"))
    delivery_instructions = models.TextField(blank=True, null=True, verbose_name=_("Delivery Instructions"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Delivery Information")
        verbose_name_plural = _("Delivery Information")
        indexes = [
            models.Index(fields=["city", "state"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self):
        return f"Delivery for {self.customer_name} - {self.city}, {self.state}"

    @property
    def full_address(self):
        """Returns the complete formatted address."""
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}"


class MarketplaceOrder(models.Model):
    """
    Main order model for marketplace purchases supporting multiple items per order.
    This replaces the single-item MarketplaceSale for multi-item shopping cart orders.
    """

    # Custom manager
    objects = MarketplaceOrderManager()

    # Basic Information
    order_number = models.CharField(max_length=50, unique=True, editable=False, verbose_name=_("Order Number"))
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketplace_orders",
        verbose_name=_("Customer"),
    )

    # Order Status and Payment
    order_status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING, verbose_name=_("Order Status")
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, verbose_name=_("Payment Status")
    )

    # Financial Information
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total Amount"))
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.NPR, verbose_name=_("Currency"))

    # Payment Information
    payment_method = models.CharField(max_length=50, verbose_name=_("Payment Method"), blank=True, null=True)
    transaction_id = models.CharField(max_length=100, verbose_name=_("Transaction ID"), blank=True, null=True)

    # Delivery Information
    delivery = models.ForeignKey(
        DeliveryInfo, on_delete=models.PROTECT, related_name="orders", verbose_name=_("Delivery Information")
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Delivered At"))
    estimated_delivery_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Estimated Delivery Date"))

    # Additional Information
    tracking_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Tracking Number"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Order Notes"))

    # B2B Order Fields
    is_b2b_order = models.BooleanField(
        default=False,
        verbose_name=_("Is B2B Order"),
        help_text=_("Indicates if this is a business-to-business order with special pricing"),
    )
    payment_terms_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Payment Terms (Days)"),
        help_text=_("Number of days allowed for payment for B2B orders"),
    )
    credit_applied = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name=_("Credit Applied"),
        help_text=_("Amount of business credit applied to this order"),
    )
    requires_invoice = models.BooleanField(
        default=False, verbose_name=_("Requires Invoice"), help_text=_("B2B order that requires formal invoice generation")
    )
    net_payment_due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Net Payment Due Date"),
        help_text=_("Due date for payment based on payment terms"),
    )

    # Soft delete functionality
    is_deleted = models.BooleanField(default=False, verbose_name=_("Is Deleted"))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Deleted At"))

    class Meta:
        verbose_name = _("Marketplace Order")
        verbose_name_plural = _("Marketplace Orders")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order_number"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["order_status", "payment_status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_deleted", "deleted_at"]),
        ]

    def __str__(self):
        return f"Order #{self.order_number} - {self.customer.username}"

    def clean(self):
        """Validate model fields before saving."""
        super().clean()

        # Validate status transitions if this is an existing instance
        if self.pk:
            old_instance = MarketplaceOrder.objects.get(pk=self.pk)
            self._validate_status_transition(old_instance.order_status, self.order_status)
            self._validate_payment_status_transition(old_instance.payment_status, self.payment_status)

    def _validate_status_transition(self, old_status, new_status):
        """Validate if the status transition is allowed."""
        if old_status == new_status:
            return

        allowed_statuses = OrderStatus.get_next_allowed_statuses(old_status)
        if new_status not in allowed_statuses:
            raise ValidationError(f"Cannot change status from {old_status} to {new_status}.")

    def _validate_payment_status_transition(self, old_status, new_status):
        """Validate payment status changes."""
        if old_status == new_status:
            return

        # Can't mark as delivered without payment
        if self.order_status in [OrderStatus.DELIVERED, OrderStatus.COMPLETED] and new_status != PaymentStatus.PAID:
            raise ValidationError("Cannot mark as delivered/completed with unpaid order.")

    def save(self, *args, **kwargs):
        """Save the model with additional validations and auto-fields."""
        self.full_clean()

        # Generate order number if not set
        if not self.order_number:
            self.order_number = f"MP-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Set delivered_at when status changes to delivered
        if self.order_status == OrderStatus.DELIVERED and not self.delivered_at:
            self.delivered_at = timezone.now()

        # Set payment due date for B2B orders with payment terms
        if self.is_b2b_order and self.payment_terms_days and not self.net_payment_due_date:
            self.net_payment_due_date = timezone.now() + timedelta(days=self.payment_terms_days)

        super().save(*args, **kwargs)

    # Status Properties
    @property
    def is_paid(self):
        """Check if the order is paid."""
        return self.payment_status == PaymentStatus.PAID

    @property
    def is_delivered(self):
        """Check if the order is delivered."""
        return self.order_status in [OrderStatus.DELIVERED, OrderStatus.COMPLETED]

    @property
    def can_cancel(self):
        """Check if the order can be cancelled."""
        return self.order_status in [OrderStatus.PENDING, OrderStatus.CONFIRMED]

    @property
    def can_refund(self):
        """Check if the order can be refunded."""
        return self.payment_status == PaymentStatus.PAID and self.order_status != OrderStatus.CANCELLED

    # B2B Properties
    @property
    def is_payment_overdue(self):
        """Check if B2B payment is overdue."""
        if not self.is_b2b_order or not self.net_payment_due_date:
            return False
        return timezone.now() > self.net_payment_due_date and not self.is_paid

    @property
    def days_until_payment_due(self):
        """Calculate days until payment is due for B2B orders."""
        if not self.is_b2b_order or not self.net_payment_due_date or self.is_paid:
            return None
        delta = self.net_payment_due_date - timezone.now()
        return delta.days if delta.days >= 0 else 0

    @property
    def available_credit_amount(self):
        """Get remaining available credit amount."""
        try:
            profile = self.customer.user_profile
            return profile.get_available_credit()
        except AttributeError:
            return Decimal("0")

    # Display Properties
    @property
    def order_status_display(self):
        """Get human-readable order status."""
        for choice_value, choice_label in OrderStatus.choices:
            if choice_value == self.order_status:
                return choice_label
        return self.order_status

    @property
    def payment_status_display(self):
        """Get human-readable payment status."""
        for choice_value, choice_label in PaymentStatus.choices:
            if choice_value == self.payment_status:
                return choice_label
        return self.payment_status

    # Price formatting
    def format_price(self, amount):
        """Format price according to the currency."""
        if format_currency:
            return format_currency(amount, self.currency, locale=settings.LANGUAGE_CODE)
        return f"{self.currency} {amount:.2f}"

    @property
    def formatted_total(self):
        """Returns formatted total amount."""
        return self.format_price(self.total_amount)

    # Order Actions
    @transaction.atomic
    def mark_as_paid(self, payment_id=None, payment_method=None):
        """Mark the order as paid."""
        if self.payment_status == PaymentStatus.PAID:
            return  # Already paid

        self.payment_status = PaymentStatus.PAID
        if payment_id:
            self.transaction_id = payment_id
        if payment_method:
            self.payment_method = payment_method
        self.save()

        # Create tracking event
        _ = OrderTrackingEvent.objects.create(
            marketplace_order=self,
            status=self.order_status,
            message="Payment confirmed",
            metadata={"payment_method": payment_method, "transaction_id": payment_id},
        )

    @transaction.atomic
    def mark_as_delivered(self):
        """Mark the order as delivered."""
        if self.order_status == OrderStatus.DELIVERED:
            return  # Already delivered

        if self.payment_status != PaymentStatus.PAID:
            raise ValidationError("Cannot mark as delivered with unpaid order.")

        self.order_status = OrderStatus.DELIVERED
        self.delivered_at = timezone.now()
        self.save()

        # Create tracking event
        _ = OrderTrackingEvent.objects.create(
            marketplace_order=self, status=OrderStatus.DELIVERED, message="Order delivered successfully"
        )

    @transaction.atomic
    def cancel_order(self, reason=None):
        """Cancel the order."""
        if not self.can_cancel:
            raise ValidationError("This order cannot be cancelled.")

        self.order_status = OrderStatus.CANCELLED
        if reason:
            self.notes = f"{self.notes or ''}\nCancellation reason: {reason}"
        self.save()

        # Return stock for all items
        for item in self.items.all():
            item.product.product.stock += item.quantity
            item.product.product.save()

        # Create tracking event
        _ = OrderTrackingEvent.objects.create(
            marketplace_order=self, status=OrderStatus.CANCELLED, message=f"Order cancelled{': ' + reason if reason else ''}"
        )

    # Soft delete implementation
    def delete(self, using=None, keep_parents=False, **kwargs):
        """Soft delete the order."""
        if not self.is_deleted:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=["is_deleted", "deleted_at"])

            # Return stock if not already delivered
            if not self.is_delivered:
                for item in self.items.all():
                    item.product.product.stock += item.quantity
                    item.product.product.save()

    def hard_delete(self, *args, **kwargs):
        """Permanently delete the order."""
        _ = super().delete(*args, **kwargs)

    def get_absolute_url(self):
        """Get the URL for the order detail view."""
        return reverse("market:order-detail", kwargs={"order_number": self.order_number})


class MarketplaceOrderItem(models.Model):
    """
    Individual items within a marketplace order.
    Each item represents a product and quantity purchased.
    """

    order = models.ForeignKey(MarketplaceOrder, on_delete=models.CASCADE, related_name="items", verbose_name=_("Order"))
    product = models.ForeignKey(
        MarketplaceProduct, on_delete=models.PROTECT, related_name="order_items", verbose_name=_("Product")
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name=_("Quantity"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Unit Price"))
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total Price"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Marketplace Order Item")
        verbose_name_plural = _("Marketplace Order Items")
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["product"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name="positive_quantity_orderitem",
                violation_error_message="Quantity must be greater than zero.",
            ),
            models.CheckConstraint(
                check=models.Q(unit_price__gte=0) & models.Q(total_price__gte=0),
                name="non_negative_prices_orderitem",
                violation_error_message="Prices cannot be negative.",
            ),
        ]

    def __str__(self):
        try:
            product_name = (
                self.product.product.name if self.product and hasattr(self.product, "product") else str(self.product)
            )
            order_number = self.order.order_number if self.order and hasattr(self.order, "order_number") else str(self.order)
            return f"{self.quantity} x {product_name} in Order #{order_number}"
        except AttributeError:
            return f"OrderItem {self.pk or 'New'}"

    def clean(self):
        """Validate model fields before saving."""
        super().clean()

        # Validate prices
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})

        if self.unit_price < 0 or self.total_price < 0:
            raise ValidationError("Prices cannot be negative.")

        # Validate that total_price = unit_price * quantity
        from decimal import Decimal

        expected_total = Decimal(str(self.unit_price)) * self.quantity
        if abs(Decimal(str(self.total_price)) - expected_total) > Decimal("0.01"):  # Allow for small rounding differences
            raise ValidationError("Total price must equal unit price multiplied by quantity.")

    def save(self, *args, **kwargs):
        """Save the model with additional validations."""
        # Set unit price from product if not provided
        if not self.unit_price:
            # Use discounted price if available, otherwise listed price
            try:
                self.unit_price = self.product.discounted_price or self.product.listed_price
            except AttributeError as e:
                raise ValueError(f"Cannot access product pricing: {e}. Product: {self.product}")

        # Calculate total price
        self.total_price = self.unit_price * self.quantity

        self.full_clean()
        super().save(*args, **kwargs)

    # Price formatting
    @property
    def formatted_unit_price(self):
        """Returns formatted unit price."""
        return self.order.format_price(self.unit_price)

    @property
    def formatted_total_price(self):
        """Returns formatted total price."""
        return self.order.format_price(self.total_price)


class OrderTrackingEvent(models.Model):
    """
    Discrete tracking event for marketplace orders.
    Updated to work with both MarketplaceSale (legacy) and MarketplaceOrder (new).

    Stores the timeline of an order for buyers/sellers to track progress.
    """

    # Support both old and new order models
    marketplace_sale = models.ForeignKey(
        "MarketplaceSale",
        on_delete=models.CASCADE,
        related_name="tracking_events",
        verbose_name=_("Marketplace Sale"),
        null=True,
        blank=True,
    )
    marketplace_order = models.ForeignKey(
        "MarketplaceOrder",
        on_delete=models.CASCADE,
        related_name="tracking_events",
        verbose_name=_("Marketplace Order"),
        null=True,
        blank=True,
    )

    # Status can be from either SaleStatus or OrderStatus
    status = models.CharField(max_length=20, verbose_name=_("Status"))
    message = models.CharField(max_length=255, blank=True, verbose_name=_("Message"))
    location = models.CharField(max_length=255, blank=True, verbose_name=_("Location"))
    latitude = models.FloatField(null=True, blank=True, verbose_name=_("Latitude"))
    longitude = models.FloatField(null=True, blank=True, verbose_name=_("Longitude"))
    metadata = models.JSONField(null=True, blank=True, verbose_name=_("Metadata"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Order Tracking Event")
        verbose_name_plural = _("Order Tracking Events")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["marketplace_sale", "created_at"]),
            models.Index(fields=["marketplace_order", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(marketplace_sale__isnull=False, marketplace_order__isnull=True)
                    | models.Q(marketplace_sale__isnull=True, marketplace_order__isnull=False)
                ),
                name="tracking_event_single_order_reference",
                violation_error_message="Tracking event must reference either a marketplace sale or marketplace order, but not both.",
            ),
        ]

    def clean(self):
        """Validate that exactly one order reference is provided."""
        super().clean()

        if not self.marketplace_sale and not self.marketplace_order:
            raise ValidationError("Tracking event must reference either a marketplace sale or marketplace order.")

        if self.marketplace_sale and self.marketplace_order:
            raise ValidationError("Tracking event cannot reference both marketplace sale and marketplace order.")

    @property
    def order(self):
        """Get the associated order (either MarketplaceSale or MarketplaceOrder)."""
        return self.marketplace_order or self.marketplace_sale

    @property
    def order_number(self):
        """Get the order number from the associated order."""
        order = self.order
        return order.order_number if order else None

    def __str__(self):
        order_number = self.order_number or "Unknown"
        return f"Order {order_number} → {self.status} at {self.created_at}"


class Invoice(models.Model):
    """
    Invoice model for marketplace sales and orders.
    Can be generated automatically when payments are completed or manually from admin.
    """

    INVOICE_STATUS_CHOICES = [
        ("draft", _("Draft")),
        ("sent", _("Sent")),
        ("paid", _("Paid")),
        ("overdue", _("Overdue")),
        ("cancelled", _("Cancelled")),
    ]

    # Invoice identification
    invoice_number = models.CharField(max_length=50, unique=True, editable=False, verbose_name=_("Invoice Number"))
    invoice_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Invoice Date"))
    due_date = models.DateTimeField(verbose_name=_("Due Date"))

    # Relationships
    marketplace_sale = models.OneToOneField(
        "MarketplaceSale",
        on_delete=models.CASCADE,
        related_name="invoice",
        null=True,
        blank=True,
        verbose_name=_("Marketplace Sale"),
    )
    marketplace_order = models.OneToOneField(
        "MarketplaceOrder",
        on_delete=models.CASCADE,
        related_name="invoice",
        null=True,
        blank=True,
        verbose_name=_("Marketplace Order"),
    )
    # Reference to payment transaction for new system
    payment_transaction = models.ForeignKey(
        "payment.PaymentTransaction",
        on_delete=models.CASCADE,
        related_name="invoices",
        null=True,
        blank=True,
        verbose_name=_("Payment Transaction"),
    )

    # Customer information
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="invoices", verbose_name=_("Customer"))
    customer_name = models.CharField(max_length=255, verbose_name=_("Customer Name"))
    customer_email = models.EmailField(verbose_name=_("Customer Email"))
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name=_("Customer Phone"))
    billing_address = models.TextField(verbose_name=_("Billing Address"))

    # Financial information
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Subtotal"))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name=_("Tax Amount"))
    shipping_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name=_("Shipping Cost")
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total Amount"))
    currency = models.CharField(max_length=3, default="NPR", verbose_name=_("Currency"))

    # Status and tracking
    status = models.CharField(max_length=20, choices=INVOICE_STATUS_CHOICES, default="draft", verbose_name=_("Status"))

    # File storage
    pdf_file = models.FileField(upload_to="invoices/pdf/", null=True, blank=True, verbose_name=_("PDF File"))

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent At"))

    # Additional metadata
    notes = models.TextField(blank=True, verbose_name=_("Notes"))

    class Meta:
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["status"]),
            models.Index(fields=["invoice_date"]),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        if not self.due_date:
            self.due_date = self.invoice_date + timedelta(days=30)  # 30 days default
        super().save(*args, **kwargs)

    def generate_invoice_number(self):
        """Generate unique invoice number"""
        today = timezone.now()
        prefix = f"INV-{today.strftime('%Y%m%d')}"

        # Get last invoice number for today
        last_invoice = Invoice.objects.filter(invoice_number__startswith=prefix).order_by("-invoice_number").first()

        if last_invoice:
            last_number = int(last_invoice.invoice_number.split("-")[-1])
            new_number = last_number + 1
        else:
            new_number = 1

        return f"{prefix}-{new_number:04d}"

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.due_date is None:
            return False
        return self.due_date < timezone.now() and self.status not in ["paid", "cancelled"]

    @property
    def source_order_number(self):
        """Get the source order number"""
        if self.marketplace_sale:
            return self.marketplace_sale.order_number
        elif self.marketplace_order:
            return self.marketplace_order.order_number
        elif self.payment_transaction:
            return self.payment_transaction.order_number
        return None

    def get_line_items(self):
        """Get all line items for this invoice"""
        return self.line_items.all()


class InvoiceLineItem(models.Model):
    """
    Individual line items for invoices
    """

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items", verbose_name=_("Invoice"))
    product_name = models.CharField(max_length=255, verbose_name=_("Product Name"))
    product_sku = models.CharField(max_length=100, blank=True, verbose_name=_("Product SKU"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    quantity = models.PositiveIntegerField(verbose_name=_("Quantity"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Unit Price"))
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total Price"))

    # Optional: Link to actual product
    marketplace_product = models.ForeignKey(
        "producer.MarketplaceProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Marketplace Product"),
    )

    class Meta:
        verbose_name = _("Invoice Line Item")
        verbose_name_plural = _("Invoice Line Items")

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} x {self.quantity} = {self.total_price}"


class ShoppableVideo(models.Model):
    """
    Represents a short, shoppable video (TikTok-style) uploaded by sellers or influencers.
    Allows tagging products for instant purchase.
    """

    uploader = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shoppable_videos", verbose_name=_("Uploader"))
    video_file = models.FileField(
        upload_to="shoppable_videos/",
        verbose_name=_("Video File"),
        validators=[FileExtensionValidator(allowed_extensions=["mp4", "avi", "mov"])],
    )
    thumbnail = models.ImageField(
        upload_to="shoppable_videos/thumbnails/", null=True, blank=True, verbose_name=_("Thumbnail")
    )
    title = models.CharField(max_length=255, verbose_name=_("Video Title"), default="")
    description = models.TextField(blank=True, verbose_name=_("Description"))

    # Product featured in the video
    product = models.ForeignKey(
        MarketplaceProduct, on_delete=models.CASCADE, related_name="shoppable_videos", verbose_name=_("Primary Product")
    )
    additional_products = models.ManyToManyField(
        MarketplaceProduct, related_name="featured_in_videos", blank=True, verbose_name=_("Additional Products")
    )

    # Engagement metrics
    views_count = models.PositiveIntegerField(default=0, verbose_name=_("Views"))
    likes_count = models.PositiveIntegerField(default=0, verbose_name=_("Likes"))
    shares_count = models.PositiveIntegerField(default=0, verbose_name=_("Shares"))

    # Recommendation fields
    tags = models.JSONField(default=list, blank=True, verbose_name=_("Tags"))
    trend_score = models.FloatField(default=0.0, verbose_name=_("Trend Score"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    def __str__(self):
        return f"Video {self.id} by {self.uploader.username}"

    class Meta:
        verbose_name = _("Shoppable Video")
        verbose_name_plural = _("Shoppable Videos")
        ordering = ["-created_at"]


class VideoLike(models.Model):
    """
    Represents a user 'liking' a shoppable video.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="liked_videos")
    video = models.ForeignKey(ShoppableVideo, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "video")
        verbose_name = _("Video Like")
        verbose_name_plural = _("Video Likes")

    def __str__(self):
        return f"{self.user.username} liked Video {self.video.id}"


class VideoSave(models.Model):
    """
    Represents a user 'saving' a shoppable video.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_videos")
    video = models.ForeignKey(ShoppableVideo, on_delete=models.CASCADE, related_name="saves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "video")
        verbose_name = _("Video Save")
        verbose_name_plural = _("Video Saves")

    def __str__(self):
        return f"{self.user.username} saved Video {self.video.id}"


class VideoComment(models.Model):
    """
    Represents a comment on a shoppable video.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="video_comments")
    video = models.ForeignKey(ShoppableVideo, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField(verbose_name=_("Comment Text"))
    created_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies", verbose_name=_("Parent Comment")
    )

    class Meta:
        verbose_name = _("Video Comment")
        verbose_name_plural = _("Video Comments")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Comment by {self.user.username} on Video {self.video.id}"


class VideoReport(models.Model):
    """
    Represents a report filed against a shoppable video for moderation.
    """

    REPORT_REASONS = [
        ("spam", _("Spam")),
        ("inappropriate", _("Inappropriate Content")),
        ("harassment", _("Harassment")),
        ("misleading", _("Misleading Information")),
        ("other", _("Other")),
    ]

    STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("reviewed", _("Reviewed")),
        ("resolved", _("Resolved")),
        ("dismissed", _("Dismissed")),
    ]

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="filed_reports")
    video = models.ForeignKey(ShoppableVideo, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=50, choices=REPORT_REASONS, verbose_name=_("Reason"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name=_("Status"))
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Video Report")
        verbose_name_plural = _("Video Reports")

    def __str__(self):
        return f"Report {self.id} on Video {self.video.id} ({self.status})"


class UserFollow(models.Model):
    """
    Represents a user following another user (e.g., a buyer following a seller/creator).
    """

    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name="following")
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="followers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("follower", "following")
        verbose_name = _("User Follow")
        verbose_name_plural = _("User Follows")

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"
