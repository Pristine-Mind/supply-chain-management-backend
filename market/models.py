from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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
        return f"Delivery for {self.customer_name} ({self.city})"
