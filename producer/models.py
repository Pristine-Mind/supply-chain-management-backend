import uuid
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from ckeditor.fields import RichTextField
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Producer(models.Model):
    """
    Represents a producer or manufacturer of products in the system.

    Fields:
    - name: The name of the producer, translatable.
    - contact: Contact details for the producer (phone, etc.).
    - email: Email address of the producer.
    - address: Physical address of the producer, translatable.
    - registration_number: A unique identifier for the producer, used for tracking and compliance.
    - created_at: Timestamp indicating when the producer was created in the system.
    - updated_at: Timestamp indicating the last update to the producer's details.
    """

    name = models.CharField(max_length=100, verbose_name=_("Producer Name"))
    contact = models.CharField(max_length=100, verbose_name=_("Contact Information"))
    email = models.EmailField(verbose_name=_("Email Address"), null=True, blank=True)
    address = models.TextField(verbose_name=_("Physical Address"))
    registration_number = models.CharField(max_length=100, unique=True, verbose_name=_("Registration Number"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))
    location = models.PointField(srid=4326, help_text="Local Unit Location", null=True, blank=True)
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Producer")
        verbose_name_plural = _("Producers")


class Customer(models.Model):
    """
    Represents a customer of the producer, which can be a retailer, wholesaler, or distributor.

    Fields:
    - name: The name of the customer, translatable.
    - customer_type: Defines the type of customer (Retailer, Wholesaler, Distributor).
    - contact: Contact details for the customer.
    - email: Email address for the customer.
    - billing_address: The billing address for the customer.
    - shipping_address: The shipping address where products are delivered.
    - credit_limit: The credit limit extended to the customer.
    - current_balance: The current outstanding balance for the customer.
    - created_at: Timestamp indicating when the customer was created.
    - updated_at: Timestamp indicating when the customer was last updated.
    """

    CUSTOMER_TYPE_CHOICES = [("Retailer", _("Retailer")), ("Wholesaler", _("Wholesaler")), ("Distributor", _("Distributor"))]

    name = models.CharField(max_length=100, verbose_name=_("Customer Name"))
    customer_type = models.CharField(max_length=50, choices=CUSTOMER_TYPE_CHOICES, verbose_name=_("Customer Type"))
    contact = models.CharField(max_length=100, verbose_name=_("Contact Information"))
    email = models.EmailField(verbose_name=_("Email Address"))
    billing_address = models.TextField(verbose_name=_("Billing Address"))
    shipping_address = models.TextField(verbose_name=_("Shipping Address"))
    credit_limit = models.FloatField(default=0.00, verbose_name=_("Credit Limit"))
    current_balance = models.FloatField(default=0.00, verbose_name=_("Current Balance"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} ({self.customer_type})"

    class Meta:
        verbose_name = _("Customer")
        verbose_name_plural = _("Customers")


class Product(models.Model):
    """
    Represents a product produced by the producer and sold to customers.

    Fields:
    - producer: The producer of the product.
    - name: The name of the product.
    - description: A brief description of the product.
    - sku: The Stock Keeping Unit (SKU), a unique identifier for the product.
    - price: The selling price of the product.
    - cost_price: The cost to the producer to create the product.
    - stock: The current stock level of the product.
    - reorder_level: The minimum stock level at which the producer will be alerted to reorder the product.
    - is_active: Indicates whether the product is currently available for sale.
    - created_at: Timestamp indicating when the product was added.
    - updated_at: Timestamp indicating the last update to the product's details.
    - rate: Unit price of each product
    """

    class ProductCategory(models.TextChoices):
        FASHION_APPAREL = "FA", "Fashion & Apparel"
        ELECTRONICS_GADGETS = "EG", "Electronics & Gadgets"
        GROCERIES_ESSENTIALS = "GE", "Groceries & Essentials"
        HEALTH_BEAUTY = "HB", "Health & Beauty"
        HOME_LIVING = "HL", "Home & Living"
        TRAVEL_TOURISM = "TT", "Travel & Tourism"
        INDUSTRIAL_SUPPLIES = "IS", "Industrial Supplies"
        OTHER = "OT", "Other"

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, verbose_name=_("Producer"), null=True, blank=True)
    name = models.CharField(max_length=100, verbose_name=_("Product Name"))
    category = models.CharField(
        max_length=2,
        choices=ProductCategory.choices,
        default=ProductCategory.OTHER,
    )
    description = RichTextField(verbose_name=_("Product Description"))
    sku = models.CharField(max_length=100, unique=True, verbose_name=_("Stock Keeping Unit (SKU)"), null=True, blank=True)
    price = models.FloatField(verbose_name=_("Price"))
    cost_price = models.FloatField(verbose_name=_("Cost Price"))
    stock = models.IntegerField(verbose_name=_("Stock Quantity"))
    reorder_level = models.IntegerField(default=10, verbose_name=_("Reorder Level"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active Status"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))
    is_marketplace_created = models.BooleanField(default=False, verbose_name=_("Marketplace Created"))
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)
    location = models.ForeignKey(
        "City", on_delete=models.CASCADE, verbose_name="Location", help_text="Location of the product", null=True, blank=True
    )
    avg_daily_demand = models.FloatField(
        default=0.0, verbose_name=_("Average Daily Demand"), help_text="Auto-computed from sales history"
    )
    stddev_daily_demand = models.FloatField(
        default=0.0, verbose_name=_("Daily Demand Std. Dev."), help_text="Auto-computed from sales history"
    )
    safety_stock = models.IntegerField(
        default=0, verbose_name=_("Safety Stock"), help_text="z-factor × σ(Demand × LeadTime)"
    )
    reorder_point = models.IntegerField(
        default=0, verbose_name=_("Reorder Point"), help_text="avg_daily_demand × lead_time + safety_stock"
    )
    reorder_quantity = models.IntegerField(
        default=0, verbose_name=_("Reorder Quantity (EOQ)"), help_text="Optimal order quantity Q*"
    )
    lead_time_days = models.PositiveIntegerField(
        default=7, verbose_name=_("Lead Time (days)"), help_text="Supplier lead time"
    )
    projected_stockout_date_field = models.DateField(null=True, blank=True, verbose_name=_("Projected Stockout Date"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def actual_sales(self, start: date, end: date):
        return (
            Sale.objects.filter(order__product=self, sale_date__date__range=(start, end))
            .annotate(day=TruncDate("sale_date"))
            .values("day")
            .annotate(units_sold=Sum("quantity"))
            .order_by("day")
        )

    def forecast_vs_actual(self, days: int = 30, window: int = 7):
        today = timezone.localdate()
        start = today - timedelta(days=days)
        sales = list(self.actual_sales(start, today))
        day_map = {r["day"]: r["units_sold"] for r in sales}

        actuals, forecast = [], []
        window_vals = []
        for i in range(days):
            d = start + timedelta(days=i + 1)
            sold = day_map.get(d, 0)
            actuals.append({"day": d, "units_sold": sold})

            window_vals.append(sold)
            if len(window_vals) > window:
                window_vals.pop(0)
            f = sum(window_vals) / len(window_vals) if window_vals else 0
            forecast.append({"day": d, "forecasted": round(f, 2)})

        return actuals, forecast

    @property
    def projected_stockout_date(self):
        today = timezone.localdate()
        burn = (
            self.avg_daily_demand
            or (
                Sale.objects.filter(order__product=self, sale_date__date__gte=today - timedelta(days=14)).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )
            / 14
        )
        if burn <= 0:
            return None
        days_left = self.stock / burn
        return today + timedelta(days=days_left)

    def seasonality_index(self, period_start: date, period_end: date):
        def sum_qty(s, e):
            return (
                Sale.objects.filter(order__product=self, sale_date__date__range=(s, e)).aggregate(total=Sum("quantity"))[
                    "total"
                ]
                or 0
            )

        this = sum_qty(period_start, period_end)
        last_start = period_start.replace(year=period_start.year - 1)
        last_end = period_end.replace(year=period_end.year - 1)
        last = sum_qty(last_start, last_end)
        return round(this / last, 2) if last else None


class Order(models.Model):
    """
    Represents an order placed by a customer for a product.

    Fields:
    - customer: The customer who placed the order.
    - order_number: A unique identifier for the order.
    - product: The product being ordered.
    - quantity: The quantity of the product being ordered.
    - status: The current status of the order (Pending, Approved, Shipped, Delivered, Cancelled).
    - order_date: The date the order was placed.
    - delivery_date: The date the order is expected to be delivered or was delivered.
    - total_price: The total cost of the order (product price multiplied by quantity).
    - payment_status: Indicates whether the order has been paid for (Pending, Paid).
    - payment_due_date: The date when payment is due for the order.
    - notes: Any additional notes related to the order.
    - created_at: Timestamp indicating when the order was created.
    - updated_at: Timestamp indicating the last update to the order.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name=_("Customer"))
    order_number = models.CharField(max_length=100, unique=True, verbose_name=_("Order Number"))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name=_("Product"))
    quantity = models.IntegerField(verbose_name=_("Quantity"))
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING, verbose_name=_("Order Status"))
    order_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Order Date"))
    delivery_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Delivery Date"))
    total_price = models.FloatField(verbose_name=_("Total Price"), null=True, blank=True)
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)

    def __str__(self):
        return f"Order {self.order_number} by {self.customer.name}"

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    def save(self, *args, **kwargs):
        self.order_number = f"{uuid.uuid4().hex} - {self.product.name}"
        self.total_price = self.product.price * self.quantity
        super().save(*args, **kwargs)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", _("Cash")
        ONLINE = "online", _("Online (QR)")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    order = models.ForeignKey("Order", on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CASH)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    gateway_token = models.CharField(max_length=255, blank=True, null=True, help_text="ID/token from gateway")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment #{self.pk} ({self.method}) for Order {self.order.order_number}"


class Sale(models.Model):
    """
    Represents a sale made by a customer (retailer/wholesaler) to an end-user.

    Fields:
    - customer: The customer making the sale.
    - order: The order associated with this sale.
    - product: The product being sold.
    - quantity: The quantity of the product sold.
    - sale_price: The price at which the product was sold to the end-user.
    - sale_date: The date the sale was made.
    - customer_name: The name of the end-user (optional).
    - customer_contact: The contact information for the end-user (optional).
    - created_at: Timestamp indicating when the sale was recorded.
    - updated_at: Timestamp indicating the last update to the sale details.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")

    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name=_("Order"))
    quantity = models.IntegerField(verbose_name=_("Quantity Sold"))
    sale_price = models.FloatField(verbose_name=_("Sale Price"))
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="sales", null=True, blank=True)
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Sale Date"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))
    payment_status = models.CharField(
        max_length=50, choices=Status.choices, default=Status.PENDING, verbose_name=_("Payment Status")
    )
    payment_due_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Payment Due Date"))
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)

    def __str__(self):
        return f"Sale of {self.order.product.name} (Order: {self.order.order_number})"

    class Meta:
        verbose_name = _("Sale")
        verbose_name_plural = _("Sales")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        self.reduce_product_stock()
        # Only create StockHistory on creation
        if is_new:
            from .models import StockHistory  # avoid circular import

            StockHistory.objects.create(
                product=self.order.product,
                date=self.sale_date.date() if hasattr(self.sale_date, "date") else self.sale_date,
                quantity_in=0,
                quantity_out=self.quantity,
                user=self.user,
                notes="Stock out due to sale",
                stock_after=self.order.product.stock,
            )

    def reduce_product_stock(self):
        """
        Reduce the stock of the product after a sale is made.
        """
        self.order.product.stock -= self.quantity
        self.order.product.save()


class StockList(models.Model):
    """
    Represents a list of products that have been moved to the stock list due to threshold conditions.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name=_("Product"))
    moved_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Moved Date"))
    is_pushed_to_marketplace = models.BooleanField(verbose_name=_("Is Stock moved to marketplace"), default=False)
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.product.name} moved to StockList on {self.moved_date}"


class StockHistory(models.Model):
    """
    Tracks daily stock entry and exit for each product.
    Automatically updates Product.stock on create, update, and delete.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_histories")
    date = models.DateField(default=timezone.now, verbose_name=_("Date"))
    quantity_in = models.PositiveIntegerField(default=0, verbose_name=_("Stock In"))
    quantity_out = models.PositiveIntegerField(default=0, verbose_name=_("Stock Out"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, blank=False, verbose_name=_("User"))
    stock_after = models.IntegerField(verbose_name=_("Stock After Movement"), null=True, blank=True)
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    class Meta:
        verbose_name = _("Stock History")
        verbose_name_plural = _("Stock Histories")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.product.name} on {self.date}: +{self.quantity_in}/-{self.quantity_out}"

    def save(self, *args, **kwargs):
        # Prevent update after creation except by superuser
        if self.pk:
            # If this is an update, block unless user is superuser
            request = getattr(self, "_request", None)
            if request is None or not getattr(request.user, "is_superuser", False):
                raise PermissionDenied("StockHistory entries cannot be updated after creation.")

        # Ensure user is set
        if not self.user_id:
            raise ValueError("StockHistory entries must have a user.")

        # Concurrency protection
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product.pk)

            # Determine if this is an update or a new entry
            if self.pk:
                old = StockHistory.objects.get(pk=self.pk)
                delta_in = self.quantity_in - old.quantity_in
                delta_out = self.quantity_out - old.quantity_out
            else:
                delta_in = self.quantity_in
                delta_out = self.quantity_out

            # Prevent negative stock
            new_stock = product.stock + delta_in - delta_out
            if new_stock < 0:
                raise ValueError(
                    f"Stock cannot go negative for product {product.name}. Current: {product.stock}, Attempted: {new_stock}"
                )

            super().save(*args, **kwargs)
            # Update product stock
            product.stock = new_stock
            product.save()
            # Set stock_after and save again if changed
            self.stock_after = product.stock
            super().save(update_fields=["stock_after"])

    def delete(self, *args, **kwargs):
        request = getattr(self, "_request", None)
        if request is None or not getattr(request.user, "is_superuser", False):
            raise PermissionDenied("StockHistory entries cannot be deleted except by superuser.")
        self.is_active = False
        self.save(update_fields=["is_active"])


class MarketplaceProduct(models.Model):
    """
    Represents a product listed in the marketplace with advanced pricing, offers, shipping, variants, engagement, and ratings features.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name=_("Product"))
    listed_price = models.FloatField(verbose_name=_("Listed Price"), help_text="Original price before discount.")
    discounted_price = models.FloatField(
        null=True, blank=True, verbose_name=_("Discounted Price"), help_text="Discounted price if applicable."
    )
    listed_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Listed Date"))
    is_available = models.BooleanField(default=True, verbose_name=_("Is Available"))
    min_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Minimum Order"),
        help_text="Minimum order quantity (required for distributors)",
    )
    offer_start = models.DateTimeField(null=True, blank=True, verbose_name=_("Offer Start"))
    offer_end = models.DateTimeField(null=True, blank=True, verbose_name=_("Offer End"))
    estimated_delivery_days = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Estimated Delivery Days"))
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name=_("Shipping Cost"))
    recent_purchases_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Recent Purchases (24h)"),
        help_text=_("Number of times this product was purchased in the last 24 hours. Used for popularity ranking."),
    )
    view_count = models.PositiveIntegerField(default=0, verbose_name=_("View Count"))
    rank_score = models.FloatField(default=0, verbose_name=_("Rank Score"))

    def save(self, *args, **kwargs):
        user_profile = None
        try:
            user_profile = self.product.user.userprofile
        except Exception:
            pass
        if user_profile and getattr(user_profile, "business_type", None) == "distributor":
            if self.min_order is None:
                raise ValidationError({"min_order": "This field is required for distributors."})
            if self.min_order <= 0:
                raise ValidationError({"min_order": "Minimum order must be greater than zero."})
        if self.discounted_price is not None:
            if self.listed_price is None:
                raise ValidationError({"listed_price": "Listed price required if discounted price is set."})
            if self.discounted_price >= self.listed_price:
                raise ValidationError({"discounted_price": "Discounted price must be less than listed price."})
            if self.discounted_price <= 0:
                raise ValidationError({"discounted_price": "Discounted price must be greater than zero."})
        if self.offer_start and self.offer_end and self.offer_start >= self.offer_end:
            raise ValidationError({"offer_end": "Offer end must be after offer start."})
        super().save(*args, **kwargs)

    @property
    def percent_off(self):
        if self.discounted_price and self.listed_price:
            return round(100 * (self.listed_price - self.discounted_price) / self.listed_price, 2)
        return 0

    @property
    def price(self):
        """Return the effective price (discounted price if available, otherwise listed price)"""
        effective_price = self.discounted_price if self.discounted_price else self.listed_price
        return Decimal(str(effective_price)) if effective_price is not None else Decimal('0')

    @property
    def savings_amount(self):
        if self.discounted_price and self.listed_price:
            return round(self.listed_price - self.discounted_price, 2)
        return 0

    @property
    def is_offer_active(self):
        now = timezone.now()
        return self.offer_start and self.offer_end and self.offer_start <= now <= self.offer_end

    @property
    def offer_countdown(self):
        if self.is_offer_active:
            return (self.offer_end - timezone.now()).total_seconds()
        return None

    @property
    def is_free_shipping(self):
        return self.shipping_cost == 0

    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if not reviews:
            return 0
        return round(sum(r.rating for r in reviews) / reviews.count(), 2)

    @property
    def ratings_breakdown(self):
        reviews = self.reviews.all()
        breakdown = Counter(r.rating for r in reviews)
        total = reviews.count()
        return {str(star): round(100 * breakdown.get(star, 0) / total, 2) if total else 0 for star in range(1, 6)}

    @property
    def total_reviews(self):
        return self.reviews.count()

    def __str__(self):
        return f"{self.product.name} listed for {self.listed_price}"

    class Meta:
        verbose_name = _("Marketplace Product")
        verbose_name_plural = _("Marketplace Products")


class MarketplaceBulkPriceTier(models.Model):
    """
    Represents a bulk pricing tier for a marketplace product.
    Each tier defines a minimum quantity for a discount or special price per unit.
    Fields:
    - product: The related MarketplaceProduct.
    - min_quantity: Minimum quantity required to qualify for this tier.
    - discount_percent: Discount percent (optional, mutually exclusive with price_per_unit).
    - price_per_unit: Special price per unit for this tier (optional).
    """

    product = models.ForeignKey(MarketplaceProduct, related_name="bulk_price_tiers", on_delete=models.CASCADE)
    min_quantity = models.PositiveIntegerField(verbose_name=_("Min Quantity"))
    discount_percent = models.FloatField(verbose_name=_("Discount Percent"), null=True, blank=True)
    price_per_unit = models.FloatField(verbose_name=_("Price Per Unit"), null=True, blank=True)

    class Meta:
        unique_together = ("product", "min_quantity")
        ordering = ["min_quantity"]
        verbose_name = _("Bulk Price Tier")
        verbose_name_plural = _("Bulk Price Tiers")

    def clean(self):
        if self.discount_percent is not None and (self.discount_percent < 0 or self.discount_percent > 100):
            raise ValidationError({"discount_percent": "Discount percent must be between 0 and 100."})
        if self.price_per_unit is not None and self.price_per_unit <= 0:
            raise ValidationError({"price_per_unit": "Price per unit must be greater than zero."})

    def __str__(self):
        return f"{self.min_quantity}+ units: {self.discount_percent or ''}% off, {self.price_per_unit or ''} per unit"


class MarketplaceProductVariant(models.Model):
    """
    Represents a specific variant of a marketplace product (e.g., size, color).
    Fields:
    - product: The related MarketplaceProduct.
    - name: The name of the variant attribute (e.g., 'Size', 'Color').
    - value: The value of the variant (e.g., 'XL', 'Red').
    - additional_price: Additional price for this variant (added to base/original price).
    - stock: Stock available for this variant.
    """

    product = models.ForeignKey(MarketplaceProduct, related_name="variants", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, verbose_name=_("Variant Name"))
    value = models.CharField(max_length=100, verbose_name=_("Variant Value"))
    additional_price = models.FloatField(default=0, verbose_name=_("Additional Price"))
    stock = models.PositiveIntegerField(default=0, verbose_name=_("Stock"))

    class Meta:
        unique_together = ("product", "name", "value")
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")

    def __str__(self):
        return f"{self.product} - {self.name}: {self.value}"


class MarketplaceProductReview(models.Model):
    """
    Represents a review and rating for a marketplace product by a user.
    Fields:
    - product: The related MarketplaceProduct.
    - user: The user who submitted the review.
    - rating: Integer rating (1-5 stars).
    - review_text: Optional review text.
    - created_at: Timestamp when the review was created.
    """

    product = models.ForeignKey(MarketplaceProduct, related_name="reviews", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    rating = models.PositiveIntegerField(choices=[(i, str(i)) for i in range(1, 6)], verbose_name=_("Rating"))
    review_text = models.TextField(blank=True, null=True, verbose_name=_("Review"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product", "user")
        ordering = ["-created_at"]
        verbose_name = _("Product Review")
        verbose_name_plural = _("Product Reviews")

    def clean(self):
        if self.rating < 1 or self.rating > 5:
            raise ValidationError({"rating": "Rating must be between 1 and 5."})

    def __str__(self):
        return f"{self.product} - {self.user} ({self.rating})"


class ProductImage(models.Model):
    """
    Represents multiple images for a product.
    """

    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="product_images/")
    alt_text = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Alternative Text"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.alt_text or f"Image for {self.product.name}"


class City(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class LedgerEntry(models.Model):
    class AccountType(models.TextChoices):
        INVENTORY = "INV", _("Inventory")
        ACCOUNTS_PAYABLE = "AP", _("Accounts Payable")
        ACCOUNTS_RECEIVABLE = "AR", _("Accounts Receivable")
        SALES_REVENUE = "SR", _("Sales Revenue")
        COST_OF_GOODS_SOLD = "COGS", _("Cost of Goods Sold")
        VAT_RECEIVABLE = "VAT_R", _("VAT Receivable")
        VAT_PAYABLE = "VAT_P", _("VAT Payable")
        TDS_PAYABLE = "TDS", _("TDS Payable")
        CASH = "CASH", _("Cash/Bank")

    account_type = models.CharField(max_length=5, choices=AccountType.choices, verbose_name=_("Account Type"))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Amount"))
    debit = models.BooleanField(default=True, verbose_name=_("Debit Entry"))
    reference_id = models.CharField(max_length=100, verbose_name=_("Reference ID"))
    date = models.DateField(default=timezone.now, verbose_name=_("Transaction Date"))
    related_entity = models.IntegerField(verbose_name=_("Related Entity ID"))
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("User"))

    class Meta:
        verbose_name = _("Ledger Entry")
        verbose_name_plural = _("Ledger Entries")

    def __str__(self):
        return f"{self.account_type} - {self.amount} ({'Debit' if self.debit else 'Credit'})"


class AuditLog(models.Model):
    class TransactionType(models.TextChoices):
        PROCUREMENT = "Procurement", _("Procurement")
        INVENTORY = "Inventory", _("Inventory")
        SALES = "Sales", _("Sales")
        RECONCILIATION = "Reconciliation", _("Reconciliation")

    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices, verbose_name=_("Transaction Type"))
    reference_id = models.CharField(max_length=100, verbose_name=_("Reference ID"))
    date = models.DateField(default=timezone.now, verbose_name=_("Date"))
    entity_id = models.IntegerField(verbose_name=_("Entity ID"))
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name=_("Amount"))
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("User"))

    class Meta:
        verbose_name = _("Audit Log")
        verbose_name_plural = _("Audit Logs")

    def __str__(self):
        return f"{self.transaction_type} - {self.reference_id}"


class PurchaseOrder(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    sent_to_vendor = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("User"))

    def __str__(self):
        return f"PO #{self.id} – {self.product.sku} x{self.quantity}"

    class Meta:
        verbose_name = _("Purchase Order")
        verbose_name_plural = _("Purchase Orders")

    def save(self, *args, **kwargs):
        # Check if approval status changes from False to True
        is_new = self.pk is None
        prev_approved = False
        if not is_new:
            orig = type(self).objects.get(pk=self.pk)
            prev_approved = orig.approved
        super().save(*args, **kwargs)
        if (is_new and self.approved) or (not is_new and not prev_approved and self.approved):
            # Stock is received only on approval
            self.product.stock += self.quantity
            self.product.save()
            from .models import StockHistory

            StockHistory.objects.create(
                product=self.product,
                date=self.created_at.date() if hasattr(self.created_at, "date") else self.created_at,
                quantity_in=self.quantity,
                quantity_out=0,
                user=self.user,
                notes="Stock in due to purchase order approval",
                stock_after=self.product.stock,
            )


class DirectSale(models.Model):
    """
    Tracks direct sales of products without requiring a customer.
    Automatically calculates total price and updates inventory.
    """

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="direct_sales", verbose_name=_("Product"))
    quantity = models.PositiveIntegerField(default=1, verbose_name=_("Quantity"), help_text=_("Number of units sold"))
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_("Unit Price"), help_text=_("Price per unit at the time of sale")
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False, verbose_name=_("Total Amount"))
    sale_date = models.DateTimeField(default=timezone.now, verbose_name=_("Sale Date"))
    reference = models.CharField(
        max_length=100, blank=True, null=True, verbose_name=_("Reference"), help_text=_("Optional reference number or code")
    )
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="direct_sales", null=True, blank=True)
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name=_("User"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        ordering = ["-sale_date"]
        verbose_name = _("Direct Sale")
        verbose_name_plural = _("Direct Sales")

    def __str__(self):
        return f"{self.quantity}x {self.product.name} - {self.total_amount} ({self.sale_date.strftime('%Y-%m-%d')})"

    def clean(self):
        if not self.pk:
            if self.quantity > self.product.stock:
                raise ValidationError({"quantity": f"Not enough stock. Only {self.product.stock} available."})

    def save(self, *args, **kwargs):
        self.total_amount = self.unit_price * self.quantity

        if not self.pk:
            self.unit_price = self.product.price

            with transaction.atomic():
                # Refresh the product to get the latest stock value
                self.product.refresh_from_db()
                # Calculate new stock value
                new_stock = self.product.stock - self.quantity
                # Update stock directly with the calculated value
                self.product.stock = new_stock
                self.product.save(update_fields=["stock"])

                StockHistory.objects.create(
                    product=self.product,
                    date=timezone.now().date(),
                    quantity_out=self.quantity,
                    notes=f"Direct sale - {self.quantity} units" + (f" (Ref: {self.reference})" if self.reference else ""),
                    user=self.user,
                    stock_after=self.product.stock - self.quantity,
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            # Refresh the product to get the latest stock value
            self.product.refresh_from_db()
            # Calculate new stock value
            new_stock = self.product.stock + self.quantity
            # Update stock directly with the calculated value
            self.product.stock = new_stock
            self.product.save(update_fields=["stock"])

            StockHistory.objects.create(
                product=self.product,
                date=timezone.now().date(),
                quantity_in=self.quantity,
                quantity_out=0,
                notes=f"Stock returned from deleted direct sale #{self.id}",
                user=getattr(self, "user", None),
                stock_after=new_stock,
            )

            super().delete(*args, **kwargs)
