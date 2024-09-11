from django.db import models
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
    email = models.EmailField(verbose_name=_("Email Address"))
    address = models.TextField(verbose_name=_("Physical Address"))
    registration_number = models.CharField(max_length=100, unique=True, verbose_name=_("Registration Number"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))

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
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name=_("Credit Limit"))
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name=_("Current Balance"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))

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

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, verbose_name=_("Producer"))
    name = models.CharField(max_length=100, verbose_name=_("Product Name"))
    description = models.TextField(verbose_name=_("Product Description"))
    sku = models.CharField(max_length=100, unique=True, verbose_name=_("Stock Keeping Unit (SKU)"))
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Price"))
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Cost Price"))
    stock = models.IntegerField(verbose_name=_("Stock Quantity"))
    reorder_level = models.IntegerField(default=10, verbose_name=_("Reorder Level"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active Status"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))

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
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Total Price"), null=True, blank=True)
    payment_status = models.CharField(
        max_length=50, choices=Status.choices, default=Status.PENDING, verbose_name=_("Payment Status")
    )
    payment_due_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Payment Due Date"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))

    def __str__(self):
        return f"Order {self.order_number} by {self.customer.name}"

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    def save(self, *args, **kwargs):
        self.total_price = self.product.price * self.quantity
        super().save(*args, **kwargs)


class Sale(models.Model):
    """
    Represents a sale made by a customer (retailer/wholesaler) to an end-user.

    Fields:
    - customer: The customer making the sale.
    - product: The product being sold.
    - quantity: The quantity of the product sold.
    - sale_price: The price at which the product was sold to the end-user.
    - sale_date: The date the sale was made.
    - customer_name: The name of the end-user (optional).
    - customer_contact: The contact information for the end-user (optional).
    - created_at: Timestamp indicating when the sale was recorded.
    - updated_at: Timestamp indicating the last update to the sale details.
    """

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name=_("Customer"))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name=_("Product"))
    quantity = models.IntegerField(verbose_name=_("Quantity Sold"))
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Sale Price"))
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Sale Date"))
    customer_name = models.CharField(max_length=100, blank=True, verbose_name=_("End-User Name"))
    customer_contact = models.CharField(max_length=100, blank=True, verbose_name=_("End-User Contact Information"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation Time"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Update Time"))

    def __str__(self):
        return f"Sale of {self.product.name} by {self.customer.name}"

    class Meta:
        verbose_name = _("Sale")
        verbose_name_plural = _("Sales")


class StockList(models.Model):
    """
    Represents a list of products that have been moved to the stock list due to threshold conditions.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name=_("Product"))
    moved_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Moved Date"))

    def __str__(self):
        return f"{self.product.name} moved to StockList on {self.moved_date}"


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
    listed_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Listed Price"))
    listed_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Listed Date"))
    is_available = models.BooleanField(default=True, verbose_name=_("Is Available"))
    bid_end_date = models.DateTimeField(verbose_name=_("Bid End Date"))

    def __str__(self):
        return f"{self.product.name} listed for {self.listed_price}"

    class Meta:
        verbose_name = _("Marketplace Product")
        verbose_name_plural = _("Marketplace Products")


class ProductImage(models.Model):
    """
    Represents multiple images for a product.
    """
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='product_images/')
    alt_text = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Alternative Text"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.alt_text or f"Image for {self.product.name}"
