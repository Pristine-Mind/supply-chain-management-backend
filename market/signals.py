import logging
import os

from django.core.files import File
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
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
    MarketplaceSale,
    MarketplaceUserProduct,
    Notification,
    OrderTrackingEvent,
    UserProductImage,
)
from .utils import notify_event


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
    if instance.stock <= instance.reorder_level:
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
