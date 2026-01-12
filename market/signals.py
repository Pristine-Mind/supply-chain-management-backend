import logging
import os

from django.core.cache import cache
from django.core.files import File
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

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
    Delivery,
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


# @receiver(post_save, sender=Product)
# def low_stock_alert(sender, instance, **kwargs):
#     if instance.stock <= 10:
#         # avoid duplicates
#         recent = Notification.objects.filter(
#             user=instance.user, notification_type=Notification.Type.STOCK, message__icontains=instance.name
#         )
#         if not recent.exists():
#             msg = f"⚠️ Low stock: {instance.name} only {instance.stock} left."
#             notify_event(
#                 user=instance.user,
#                 notif_type=Notification.Type.STOCK,
#                 message=msg,
#                 via_in_app=True,
#                 via_email=True,
#                 email_addr=instance.user.email,
#                 email_tpl="stock_alert.html",
#                 email_ctx={"product_id": instance.id},
#                 via_sms=True,
#                 sms_number=instance.user.user_profile.phone_number,
#                 sms_body=msg,
#             )

#     # Invalidate caches when marketplace products or underlying product data change
#     @receiver(post_save, sender=MarketplaceProduct, dispatch_uid="invalidate_cache_marketplaceproduct_save")
#     @receiver(post_delete, sender=MarketplaceProduct, dispatch_uid="invalidate_cache_marketplaceproduct_delete")
#     @receiver(post_save, sender=Product, dispatch_uid="invalidate_cache_product_save")
#     @receiver(post_delete, sender=Product, dispatch_uid="invalidate_cache_product_delete")
#     @receiver(post_save, sender=ProductImage, dispatch_uid="invalidate_cache_productimage_save")
#     @receiver(post_delete, sender=ProductImage, dispatch_uid="invalidate_cache_productimage_delete")
#     def invalidate_product_cache(sender, instance, **kwargs):
#         # Determine category name (string) if available to perform targeted invalidation
#         category_name = None
#         featured = False
#         try:
#             if hasattr(instance, "product") and getattr(instance, "product") is not None:
#                 prod = instance.product
#             else:
#                 prod = instance

#             # product may have category attribute as FK or as simple value
#             cat = getattr(prod, "category", None)
#             if cat is not None:
#                 # If it's a model, try to get name; else use string form
#                 category_name = getattr(cat, "name", str(cat))

#             # If this is a MarketplaceProduct or Product, check featured flag if present
#             featured = bool(getattr(instance, "is_featured", False) or getattr(prod, "is_featured", False))
#         except Exception:
#             category_name = None
#             featured = False

#         try:
#             _clear_trending_and_producer_cache(category_name=category_name, featured=featured)
#         except Exception:
#             # last resort: clear whole cache
#             try:
#                 cache.clear()
#             except Exception:
#                 pass


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


@receiver(post_save, sender=Delivery, dispatch_uid="create_transport_delivery_from_sale")
def create_transport_delivery_from_sale(sender, instance, created, **kwargs):
    """
    Create a transport delivery record when a market delivery is created from a sale.
    This makes the delivery available to transporters.
    """
    # Only create transport delivery for new deliveries that are from sales
    if not created or not instance.sale:
        return

    try:
        # Import here to avoid circular imports
        from django.utils import timezone

        from transport.models import Delivery as TransportDelivery
        from transport.models import DeliveryPriority, TransportStatus

        # Check if transport delivery already exists
        if TransportDelivery.objects.filter(sale=instance.sale).exists():
            return

        # Set default dates if not provided
        now = timezone.now()
        pickup_date = instance.estimated_delivery_date or (now + timezone.timedelta(days=1))
        delivery_date = instance.estimated_delivery_date or (now + timezone.timedelta(days=2))

        # Get producer/seller details for pickup
        producer_obj = instance.sale.order.product.producer
        producer_user = producer_obj.user if producer_obj else None

        # Use producer profile information for pickup address
        pickup_addr = producer_obj.address if producer_obj and producer_obj.address else "Producer Address"
        pickup_city = producer_obj.city.name if producer_obj and producer_obj.city else "Unknown"
        pickup_state = producer_obj.state if producer_obj and producer_obj.state else ""
        pickup_lat = producer_obj.latitude if producer_obj and producer_obj.latitude else instance.latitude
        pickup_lng = producer_obj.longitude if producer_obj and producer_obj.longitude else instance.longitude

        # Get producer contact details
        pickup_contact_name = (
            producer_obj.business_name
            if producer_obj and producer_obj.business_name
            else (producer_user.get_full_name() if producer_user else "Producer")
        )
        pickup_phone = (
            producer_obj.phone_number
            if producer_obj and producer_obj.phone_number
            else (getattr(producer_user, "phone", "") if producer_user else "")
        )

        # Create transport delivery record
        transport_delivery = TransportDelivery.objects.create(
            sale=instance.sale,
            pickup_address=f"{pickup_addr}, {pickup_city}, {pickup_state}".strip(", "),
            pickup_latitude=pickup_lat,
            pickup_longitude=pickup_lng,
            pickup_contact_name=pickup_contact_name,
            pickup_contact_phone=pickup_phone,
            delivery_address=f"{instance.address}, {instance.city}, {instance.state} {instance.zip_code}",
            delivery_latitude=instance.latitude,
            delivery_longitude=instance.longitude,
            delivery_contact_name=instance.customer_name,
            delivery_contact_phone=instance.phone_number,
            delivery_instructions=instance.additional_instructions or "",
            package_weight=1.0,  # Default weight, can be updated
            package_value=float(instance.sale.sale_price) if instance.sale.sale_price else 100.0,
            status=TransportStatus.AVAILABLE,
            priority=DeliveryPriority.NORMAL,
            delivery_fee=10.00,  # Default delivery fee, can be updated based on distance
            requested_pickup_date=pickup_date,
            requested_delivery_date=delivery_date,
        )

        logger.info(f"Created transport delivery {transport_delivery.delivery_id} for sale {instance.sale.id}")

    except Exception as e:
        logger.error(f"Error creating transport delivery for sale {instance.sale.id}: {str(e)}")
        import traceback

        traceback.print_exc()


@receiver(post_save, sender=Product)
def handle_stock_change(sender, instance, **kwargs):
    """
    Reject all active negotiations where the requested quantity is no longer available in stock.
    """
    from market.models import Negotiation

    # Get all active negotiations for this product
    active_negotiations = Negotiation.objects.filter(
        product__product=instance, status__in=[Negotiation.Status.PENDING, Negotiation.Status.COUNTER_OFFER]
    )

    for negotiation in active_negotiations:
        if negotiation.proposed_quantity > instance.stock:
            negotiation.status = Negotiation.Status.REJECTED
            negotiation.save()
            # History log
            from market.models import NegotiationHistory

            NegotiationHistory.objects.create(
                negotiation=negotiation,
                offer_by=negotiation.seller,  # Rejection by system on behalf of seller
                price=negotiation.proposed_price,
                quantity=negotiation.proposed_quantity,
                message=f"Negotiation automatically rejected: Requested quantity ({negotiation.proposed_quantity}) exceeds available stock ({instance.stock}).",
            )


@receiver(post_save, sender=MarketplaceProduct)
def handle_marketplace_product_update(sender, instance, **kwargs):
    """
    If a product is marked as unavailable or B2B sales are disabled, reject active negotiations.
    """
    from market.models import Negotiation

    if not instance.is_available or not instance.enable_b2b_sales:
        active_negotiations = Negotiation.objects.filter(
            product=instance, status__in=[Negotiation.Status.PENDING, Negotiation.Status.COUNTER_OFFER]
        )

        reason = "Product is no longer available" if not instance.is_available else "B2B sales disabled for this product"

        for negotiation in active_negotiations:
            negotiation.status = Negotiation.Status.REJECTED
            negotiation.save()
            from market.models import NegotiationHistory

            NegotiationHistory.objects.create(
                negotiation=negotiation,
                offer_by=negotiation.seller,
                price=negotiation.proposed_price,
                quantity=negotiation.proposed_quantity,
                message=f"Negotiation automatically rejected: {reason}.",
            )
