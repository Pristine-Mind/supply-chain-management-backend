import uuid
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from market.models import Cart, MarketplaceSale, PaymentStatus, SaleStatus
from producer.models import MarketplaceProduct


class PaymentGateway(models.TextChoices):
    KHALTI = "KHALTI", _("Khalti Wallet")
    SCT = "SCT", _("SCT Card")
    CONNECT_IPS = "CONNECT_IPS", _("Connect IPS")
    MOBILE_BANKING = "MOBILE_BANKING", _("Mobile Banking")
    EBANKING = "EBANKING", _("E-Banking")


class PaymentTransactionStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")
    REFUNDED = "refunded", _("Refunded")


class PaymentTransaction(models.Model):
    """
    Handles payment transactions for multiple products in a single payment
    """

    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order_number = models.CharField(max_length=50, unique=True, editable=False)

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="payment_transactions")
    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name="payment_transactions", null=True, blank=True)

    gateway = models.CharField(max_length=20, choices=PaymentGateway.choices)
    gateway_transaction_id = models.CharField(max_length=255, blank=True, null=True)
    bank = models.CharField(max_length=100, blank=True, null=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])

    status = models.CharField(
        max_length=20, choices=PaymentTransactionStatus.choices, default=PaymentTransactionStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    return_url = models.URLField(max_length=500)

    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)

    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Payment Transaction")
        verbose_name_plural = _("Payment Transactions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["gateway_transaction_id"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Payment {self.order_number} - {self.gateway} - {self.status}"

    def save(self, *args, **kwargs):
        # Generate order number if not set
        if not self.order_number:
            self.order_number = f"PAY-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Set completion timestamp
        if self.status == PaymentTransactionStatus.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @transaction.atomic
    def mark_as_completed(self, gateway_transaction_id: str = None) -> bool:
        """
        Mark payment as completed and create marketplace sales
        """
        if self.status == PaymentTransactionStatus.COMPLETED:
            return True

        if gateway_transaction_id:
            self.gateway_transaction_id = gateway_transaction_id

        self.status = PaymentTransactionStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save()

        if self.cart:
            self._create_marketplace_sales()

        return True

    def _create_marketplace_sales(self):
        """
        Create MarketplaceSale objects for each item in the cart
        """
        if not self.cart:
            return

        cart_items = self.cart.items.select_related("product", "product__product")

        for cart_item in cart_items:
            item_subtotal = cart_item.product.price * cart_item.quantity
            item_tax = (self.tax_amount * item_subtotal / self.subtotal) if self.subtotal > 0 else Decimal('0')
            item_shipping = (self.shipping_cost * item_subtotal / self.subtotal) if self.subtotal > 0 else Decimal('0')
            item_total = item_subtotal + item_tax + item_shipping

            # Round decimal values to 2 places to prevent precision issues
            item_subtotal = item_subtotal.quantize(Decimal('0.01'))
            item_tax = item_tax.quantize(Decimal('0.01'))
            item_shipping = item_shipping.quantize(Decimal('0.01'))
            item_total = item_total.quantize(Decimal('0.01'))

            # Additional validation - ensure values fit in field constraints
            if abs(item_shipping) >= Decimal('100000000'):  # 10^8, max for 10-digit field with 2 decimals
                item_shipping = Decimal('0.00')
            if abs(item_total) >= Decimal('10000000000'):  # 10^10, max for 12-digit field with 2 decimals
                item_total = item_subtotal  # Fallback to subtotal only

            # Handle phone number - be more permissive and clear invalid ones
            buyer_phone_value = ""
            if self.customer_phone:
                phone_clean = str(self.customer_phone).strip()
                # Only process if it looks like a reasonable phone number
                if phone_clean and phone_clean.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').isdigit():
                    digits_only = ''.join(filter(str.isdigit, phone_clean))
                    if 7 <= len(digits_only) <= 15:  # Reasonable phone number length
                        if len(digits_only) == 10 and not phone_clean.startswith('+'):
                            buyer_phone_value = f"+977{digits_only}"  # Nepal format
                        elif phone_clean.startswith('+'):
                            buyer_phone_value = phone_clean
                        elif len(digits_only) >= 10:
                            buyer_phone_value = f"+{digits_only}"
                # If processing fails or results in invalid format, leave empty

            marketplace_sale = MarketplaceSale.objects.create(
                buyer=self.user,
                buyer_name=self.customer_name or (self.user.get_full_name() if self.user else ""),
                buyer_email=self.customer_email or (self.user.email if self.user else ""),
                buyer_phone=buyer_phone_value,
                seller=cart_item.product.product.user,
                product=cart_item.product,
                quantity=cart_item.quantity,
                unit_price=cart_item.product.price,
                unit_price_at_purchase=cart_item.product.price,
                subtotal=item_subtotal,
                tax_amount=item_tax,
                shipping_cost=item_shipping,
                total_amount=item_total,
                payment_method=self.gateway,
                transaction_id=str(self.transaction_id),
                payment_status=PaymentStatus.PAID,
                status=SaleStatus.PROCESSING,
                currency="NPR",
                notes=f"Payment Transaction: {self.order_number}",
            )

            cart_item.product.product.stock = max(0, cart_item.product.product.stock - cart_item.quantity)
            cart_item.product.product.save(update_fields=["stock"])

            PaymentTransactionItem.objects.create(
                payment_transaction=self,
                marketplace_sale=marketplace_sale,
                product=cart_item.product,
                quantity=cart_item.quantity,
                unit_price=cart_item.product.price,
                subtotal=item_subtotal,
                tax_amount=item_tax,
                shipping_cost=item_shipping,
                total_amount=item_total,
            )

    @property
    def is_completed(self):
        return self.status == PaymentTransactionStatus.COMPLETED

    @property
    def is_failed(self):
        return self.status == PaymentTransactionStatus.FAILED

    def get_items_count(self):
        """Get total number of items in this payment"""
        if self.cart:
            return self.cart.items.count()
        return self.transaction_items.count()


class PaymentTransactionItem(models.Model):
    """
    Individual items within a payment transaction
    """

    payment_transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE, related_name="transaction_items")
    marketplace_sale = models.OneToOneField(
        MarketplaceSale, on_delete=models.CASCADE, related_name="payment_item", null=True, blank=True
    )
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("Payment Transaction Item")
        verbose_name_plural = _("Payment Transaction Items")

    def __str__(self):
        return f"{self.quantity}x {self.product.product.name} - {self.payment_transaction.order_number}"
