import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.db import transaction


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

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, verbose_name=_("Producer"), null=True, blank=True)
    name = models.CharField(max_length=100, verbose_name=_("Product Name"))
    category = models.CharField(
        max_length=2,
        choices=ProductCategory.choices,
        default=ProductCategory.FRUITS,
    )
    description = models.TextField(verbose_name=_("Product Description"))
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

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")


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
            from .models import StockHistory  # avoid circular import if any
            StockHistory.objects.create(
                product=self.order.product,
                date=self.sale_date.date() if hasattr(self.sale_date, 'date') else self.sale_date,
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
            request = getattr(self, '_request', None)
            if request is None or not getattr(request.user, 'is_superuser', False):
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
                raise ValueError(f"Stock cannot go negative for product {product.name}. Current: {product.stock}, Attempted: {new_stock}")

            super().save(*args, **kwargs)
            # Update product stock
            product.stock = new_stock
            product.save()
            # Set stock_after and save again if changed
            self.stock_after = product.stock
            super().save(update_fields=["stock_after"])

    def delete(self, *args, **kwargs):
        request = getattr(self, '_request', None)
        if request is None or not getattr(request.user, 'is_superuser', False):
            raise PermissionDenied("StockHistory entries cannot be deleted except by superuser.")
        self.is_active = False
        self.save(update_fields=["is_active"])


class MarketplaceProduct(models.Model):
    """
    Represents a product listed in the marketplace.

    Fields:
    - product: The reference to the product in the stock list.
    - listed_price: The price at which the product is listed in the marketplace.
    - listed_date: The date when the product was listed in the marketplace.
    - is_available: Indicates whether the product is still available for sale.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name=_("Product"))
    listed_price = models.FloatField(verbose_name=_("Listed Price"))
    listed_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Listed Date"))
    is_available = models.BooleanField(default=True, verbose_name=_("Is Available"))
    bid_end_date = models.DateTimeField(verbose_name=_("Bid End Date"))

    def __str__(self):
        return f"{self.product.name} listed for {self.listed_price}"

    class Meta:
        verbose_name = _("Marketplace Product")
        verbose_name_plural = _("Marketplace Products")

    def update_bid_end_date(self, bids_last_hour: int, bids_last_day: int) -> None:
        """
        Dynamically updates the bid_end_date based on heuristic rules.
        """
        if self.bid_end_date is None:
            self.bid_end_date = timezone.now() + timedelta(days=1)

        time_left = self.bid_end_date - timezone.now()
        if bids_last_day == 0 and time_left <= timedelta(hours=6):
            self.bid_end_date += timedelta(hours=12)
        elif bids_last_day < 5 and bids_last_hour == 0:
            self.bid_end_date += timedelta(hours=6)
        elif bids_last_hour > 3:
            self.bid_end_date -= timedelta(hours=2)
        self.save()


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
                date=self.created_at.date() if hasattr(self.created_at, 'date') else self.created_at,
                quantity_in=self.quantity,
                quantity_out=0,
                user=self.user,
                notes="Stock in due to purchase order approval",
                stock_after=self.product.stock,
            )
