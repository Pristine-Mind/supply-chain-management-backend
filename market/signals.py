import logging
import os

from django.core.files import File
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.core.cache import cache

logger = logging.getLogger(__name__)

from producer.models import (
    MarketplaceProduct,
    Order,
    Product,
    ProductImage,
    PurchaseOrder,
    Sale,
    StockList,
)

from .models import (
    MarketplaceOrder,
    MarketplaceSale,
    MarketplaceUserProduct,
    Notification,
    OrderTrackingEvent,
    UserProductImage,
)
from .utils import notify_event


def _clear_trending_and_producer_cache(category_name: str = None, featured: bool = False):
    """Clear cache keys related to trending and producer listing.

    If `category_name` is provided, only keys containing that category name
    will be removed. If `featured` is True, keys related to featured lists
    will be removed as well. If Redis isn't available, falls back to clearing
    the entire cache.
    """
    base_patterns = ["trending:*", "producer:*"]
    patterns = []
    if category_name:
        # match query param appearance in cached key
        patterns.extend([f"trending:*{category_name}*", f"producer:*{category_name}*"])
    if featured:
        patterns.append("trending:featured:*")

    # If no specific patterns requested, default to base patterns
    if not patterns:
        patterns = base_patterns

    try:
        # Try to use the redis connection if django_redis is configured
        from django_redis import get_redis_connection

        conn = get_redis_connection("default")
        deleted = 0
        for pattern in patterns:
            try:
                for key in conn.scan_iter(match=pattern):
                    try:
                        conn.delete(key)
                        deleted += 1
                    except Exception:
                        pass
            except Exception:
                try:
                    keys = conn.keys(pattern)
                    if keys:
                        deleted += len(keys)
                        conn.delete(*keys)
                except Exception:
                    pass

        logger.info(f"Cleared {deleted} cache keys for patterns: {patterns}")
        return
    except Exception:
        # Not using django_redis or Redis not available — clear entire cache
        try:
            cache.clear()
            logger.info("Cache cleared (fallback).")
        except Exception:
            pass



def create_product_images(product, marketplace_product):
    """Helper function to create product images after the transaction is committed"""

    def _create_images():
        user_product_images = UserProductImage.objects.filter(product=marketplace_product).order_by("order")
        for idx, user_image in enumerate(user_product_images):
            try:
                with user_image.image.open("rb") as f:
                    img = ProductImage.objects.create(
                        product=product,
                        image=File(f, name=os.path.basename(user_image.image.name)),
                        alt_text=user_image.alt_text or f"Image {idx + 1} for {product.name}",
                    )
                    print(f"Created product image {img.id} from {user_image.image.name}")
            except Exception as e:
                logger.error(f"Error creating product image: {str(e)}")
                logger.error(
                    f"Image data: {user_image.image}, exists: {user_image.image.storage.exists(user_image.image.name)}"
                )
                raise

    transaction.on_commit(_create_images)


@receiver(post_save, sender=MarketplaceUserProduct, dispatch_uid="create_marketplace_product")
def create_marketplace_product(sender, instance, created, **kwargs):
    if created:
        product = Product.objects.create(
            producer=None,
            name=instance.name,
            description=instance.description,
            sku=f"MP-{instance.pk}",
            price=instance.price,
            cost_price=instance.price,
            stock=instance.stock,
            reorder_level=5,
            is_active=True,
            category=instance.category,
            is_marketplace_created=True,
            user=instance.user,
            location=instance.location,
        )
        MarketplaceProduct.objects.create(
            product=product,
            listed_price=instance.price,
            is_available=not instance.is_sold,
        )
        create_product_images(product, instance)


@receiver(post_save, sender=Order)
def order_notifications(sender, instance, created, **kwargs):
    user = getattr(instance.customer, "user", instance.user)
    # Order placed
    if created:
        msg = f"🎉 Your order {instance.order_number} has been placed."
        notify_event(
            user=user,
            notif_type=Notification.Type.ORDER,
            message=msg,
            via_in_app=True,
            via_email=True,
            email_addr=instance.user.email,
            email_tpl="order_confirmation.html",
            email_ctx={
                "order_id": instance.id,
                "order_number": instance.order_number,
                "status": instance.status,
                "total_amount": str(instance.total_price),
                "created_at": instance.created_at.isoformat(),
                "customer_name": instance.user.username if instance.user else "Customer",
                "order": {
                    "id": instance.id,
                    "order_number": instance.order_number,
                    "status": instance.status,
                    "total_amount": str(instance.total_price),
                    "created_at": instance.created_at.isoformat(),
                },
            },
            via_sms=True,
            sms_number=instance.user.user_profile.phone_number,
            sms_body=f"Order {instance.order_number} placed successfully!",
        )
    else:
        # status updates
        status = instance.status
        if status in ("shipped", "delivered"):
            emoji = "📦" if status == "shipped" else "✅"
            msg = f"{emoji} Order {instance.order_number} {status}."
            notify_event(
                user=user,
                notif_type=Notification.Type.ORDER,
                message=msg,
                via_in_app=True,
                via_email=True,
                email_addr=instance.user.email,
                email_tpl=f"order_{status}.html",
                email_ctx={
                    "order_id": instance.id,
                    "order_number": instance.order_number,
                    "status": instance.status,
                    "total_amount": str(instance.total_price),
                    "created_at": instance.created_at.isoformat(),
                    "customer_name": instance.user.username if instance.user else "Customer",
                },
            )


@receiver(post_save, sender=MarketplaceSale, dispatch_uid="create_initial_order_tracking_event")
def create_initial_order_tracking_event(sender, instance: "MarketplaceSale", created: bool, **kwargs):
    """Create an initial tracking event when a marketplace sale is created."""
    if not created:
        return
    try:
        OrderTrackingEvent.objects.create(
            order=instance,
            status=instance.status,
            message="Order created",
        )
    except Exception:
        pass


@receiver(post_save, sender=Sale)
def sale_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    order = instance.order
    user = getattr(order.user, "user", instance.user)
    msg = f"💰 Sale recorded for Order {order.order_number}."
    notify_event(
        user=user,
        notif_type=Notification.Type.SALE,
        message=msg,
        via_in_app=True,
        via_email=True,
        email_addr=order.user.email,
        email_tpl="sale_recorded.html",
        email_ctx={"sale_id": instance.id},
        via_sms=True,
        sms_number=order.user.user_profile.phone_number,
        sms_body=msg,
    )


@receiver(post_save, sender=PurchaseOrder)
def po_notifications(sender, instance, created, **kwargs):
    # only when flips to approved
    orig = sender.objects.filter(pk=instance.pk).first()
    if orig and not orig.approved and instance.approved:
        user = instance.user
        msg = f"📥 PO #{instance.id} approved: +{instance.quantity} of {instance.product.sku}."
        notify_event(
            user=user,
            notif_type=Notification.Type.PURCHASE_ORDER,
            message=msg,
            via_in_app=True,
            via_email=True,
            email_addr=user.email,
            email_tpl="po_approved.html",
            email_ctx={"po_id": instance.id},
            via_sms=True,
            sms_number=user.user_profile.phone_number,
            sms_body=msg,
        )


@receiver(post_save, sender=StockList)
def stocklist_notifications(sender, instance, created, **kwargs):
    if created and instance.is_pushed_to_marketplace:
        user = instance.user
        msg = f"📢 {instance.product.name} moved to Marketplace."
        notify_event(
            user=user,
            notif_type=Notification.Type.MARKETPLACE,
            message=msg,
            via_in_app=True,
            via_email=True,
            email_addr=user.email,
            email_tpl="stocklist_pushed.html",
            email_ctx={"stocklist_id": instance.id},
            via_sms=True,
            sms_number=user.user_profile.phone_number,
            sms_body=msg,
        )


@receiver(post_save, sender=Product)
def low_stock_alert(sender, instance, **kwargs):
    if instance.stock <= 10:
        # avoid duplicates
        recent = Notification.objects.filter(
            user=instance.user, notification_type=Notification.Type.STOCK, message__icontains=instance.name
        )
        if not recent.exists():
            msg = f"⚠️ Low stock: {instance.name} only {instance.stock} left."
            notify_event(
                user=instance.user,
                notif_type=Notification.Type.STOCK,
                message=msg,
                via_in_app=True,
                via_email=True,
                email_addr=instance.user.email,
                email_tpl="stock_alert.html",
                email_ctx={"product_id": instance.id},
                via_sms=True,
                sms_number=instance.user.user_profile.phone_number,
                sms_body=msg,
            )


    # Invalidate caches when marketplace products or underlying product data change
    @receiver(post_save, sender=MarketplaceProduct, dispatch_uid="invalidate_cache_marketplaceproduct_save")
    @receiver(post_delete, sender=MarketplaceProduct, dispatch_uid="invalidate_cache_marketplaceproduct_delete")
    @receiver(post_save, sender=Product, dispatch_uid="invalidate_cache_product_save")
    @receiver(post_delete, sender=Product, dispatch_uid="invalidate_cache_product_delete")
    @receiver(post_save, sender=ProductImage, dispatch_uid="invalidate_cache_productimage_save")
    @receiver(post_delete, sender=ProductImage, dispatch_uid="invalidate_cache_productimage_delete")
    def invalidate_product_cache(sender, instance, **kwargs):
        # Determine category name (string) if available to perform targeted invalidation
        category_name = None
        featured = False
        try:
            if hasattr(instance, "product") and getattr(instance, "product") is not None:
                prod = instance.product
            else:
                prod = instance

            # product may have category attribute as FK or as simple value
            cat = getattr(prod, "category", None)
            if cat is not None:
                # If it's a model, try to get name; else use string form
                category_name = getattr(cat, "name", str(cat))

            # If this is a MarketplaceProduct or Product, check featured flag if present
            featured = bool(getattr(instance, "is_featured", False) or getattr(prod, "is_featured", False))
        except Exception:
            category_name = None
            featured = False

        try:
            _clear_trending_and_producer_cache(category_name=category_name, featured=featured)
        except Exception:
            # last resort: clear whole cache
            try:
                cache.clear()
            except Exception:
                pass


@receiver(post_save, sender=MarketplaceOrder, dispatch_uid="marketplace_order_created_notification")
def marketplace_order_created_notification(sender, instance: "MarketplaceOrder", created: bool, **kwargs):
    """Send notifications when a new marketplace order is created."""
    if created:
        try:
            msg = f"🛒 Your order #{instance.order_number} has been placed successfully!"
            notify_event(
                user=instance.customer,
                notif_type=Notification.Type.ORDER,
                message=msg,
                via_in_app=True,
                via_email=True,
                email_addr=instance.customer.email,
                email_tpl="order_created.html",
                email_ctx={"order": instance},
                via_sms=False,
            )
        except Exception as e:
            logger.error(f"Error sending order creation notification: {str(e)}")


# Invoice Generation Signals
@receiver(post_save, sender=MarketplaceSale, dispatch_uid="generate_invoice_from_marketplace_sale")
def generate_invoice_from_marketplace_sale(sender, instance, created, **kwargs):
    """
    Generate invoice when marketplace sale payment is completed
    """
    print(f"Signal triggered for MarketplaceSale {instance.order_number}, payment_status: {instance.payment_status}")

    # Process if payment status is paid (both on creation and update)
    if instance.payment_status == "paid":
        try:
            # Check if invoice already exists using proper OneToOne relationship check
            try:
                existing_invoice = instance.invoice
                if existing_invoice:
                    print(f"Invoice already exists for sale {instance.order_number}: {existing_invoice.invoice_number}")
                    return
            except Exception:
                # No invoice exists yet, which is what we want
                pass

            # Import here to avoid circular imports
            from .services import InvoiceGenerationService

            print(f"Creating invoice for sale {instance.order_number}")
            # Generate invoice
            invoice = InvoiceGenerationService.create_invoice_from_marketplace_sale(instance)
            print(f"✅ Invoice {invoice.invoice_number} generated for sale {instance.order_number}")

            # Send invoice via email (optional - can be done manually from admin)
            try:
                InvoiceGenerationService.send_invoice_email(invoice)
                print(f"✅ Invoice {invoice.invoice_number} sent via email")
            except Exception as e:
                print(f"⚠️ Error sending invoice email: {str(e)}")

        except Exception as e:
            print(f"❌ Error generating invoice for sale {instance.order_number}: {str(e)}")
            import traceback

            traceback.print_exc()
    else:
        print(
            f"Sale {instance.order_number} payment_status is '{instance.payment_status}', not 'paid' - skipping invoice generation"
        )


@receiver(post_save, sender=MarketplaceOrder, dispatch_uid="generate_invoice_from_marketplace_order")
def generate_invoice_from_marketplace_order(sender, instance, created, **kwargs):
    """
    Generate invoice when marketplace order payment is completed
    """
    print(f"Signal triggered for MarketplaceOrder {instance.order_number}, payment_status: {instance.payment_status}")

    # Only process if payment status is completed
    if instance.payment_status == "completed":
        try:
            # Check if invoice already exists using proper OneToOne relationship check
            try:
                existing_invoice = instance.invoice
                if existing_invoice:
                    print(f"Invoice already exists for order {instance.order_number}: {existing_invoice.invoice_number}")
                    return
            except Exception:
                # No invoice exists yet, which is what we want
                pass

            # Import here to avoid circular imports
            from .services import InvoiceGenerationService

            print(f"Creating invoice for order {instance.order_number}")
            # Generate invoice (you'll need to implement this method)
            invoice = InvoiceGenerationService.create_invoice_from_marketplace_order(instance)
            print(f"✅ Invoice {invoice.invoice_number} generated for order {instance.order_number}")

            # Send invoice via email (optional)
            try:
                _ = InvoiceGenerationService.send_invoice_email(invoice)
                print(f"✅ Invoice {invoice.invoice_number} sent via email")
            except Exception as e:
                print(f"⚠️ Error sending invoice email: {str(e)}")

        except Exception as e:
            print(f"❌ Error generating invoice for order {instance.order_number}: {str(e)}")
            import traceback

            traceback.print_exc()
    else:
        print(
            f"Order {instance.order_number} payment_status is '{instance.payment_status}', not 'completed' - skipping invoice generation"
        )


# Signal for PaymentTransaction (if you want to handle the new payment system)
try:
    from payment.models import PaymentTransaction

    @receiver(post_save, sender=PaymentTransaction, dispatch_uid="generate_invoice_from_payment_transaction")
    def generate_invoice_from_payment_transaction(sender, instance, created, **kwargs):
        """
        Generate invoice when payment transaction is completed
        """
        print(f"Signal triggered for PaymentTransaction {instance.id}, status: {instance.status}")

        # Only process if status is completed
        if instance.status == "completed":
            try:
                # Check if invoice already exists
                existing_invoices = instance.invoices.all()
                if existing_invoices.exists():
                    print(f"Invoice already exists for payment {instance.id}")
                    return

                # Import here to avoid circular imports
                from .services import InvoiceGenerationService

                print(f"Creating invoice for payment {instance.id}")
                # Generate invoice (both for new creations and status updates)
                invoice = InvoiceGenerationService.create_invoice_from_payment_transaction(instance)
                print(f"✅ Invoice {invoice.invoice_number} generated for payment {instance.id}")

                # Send invoice via email (optional)
                try:
                    _ = InvoiceGenerationService.send_invoice_email(invoice)
                    print(f"✅ Invoice {invoice.invoice_number} sent via email")
                except Exception as e:
                    print(f"⚠️ Error sending invoice email: {str(e)}")

            except Exception as e:
                print(f"❌ Error generating invoice for payment {instance.id}: {str(e)}")
                import traceback

                traceback.print_exc()
        else:
            print(f"Payment {instance.id} status is '{instance.status}', not 'completed' - skipping invoice generation")

except ImportError:
    print("PaymentTransaction model not available - invoice generation signals disabled for payments")
