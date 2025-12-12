import logging

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

from user.admin_permissions import (
    MarketplaceProductAdminMixin,
    PaymentAdminMixin,
    PurchaseAdminMixin,
    RoleBasedModelAdminMixin,
)

from .models import (
    Bid,
    Cart,
    CartItem,
    ChatMessage,
    Delivery,
    DeliveryInfo,
    Feedback,
    Invoice,
    InvoiceLineItem,
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceSale,
    MarketplaceUserProduct,
    Notification,
    OrderTrackingEvent,
    Payment,
    Purchase,
    ShoppableVideo,
    UserInteraction,
    UserProductImage,
    VideoLike,
)


@admin.register(ShoppableVideo)
class ShoppableVideoAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "uploader", "product", "created_at", "views_count", "likes_count", "is_active")
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "uploader__username", "description", "product__name")
    readonly_fields = ("views_count", "likes_count", "shares_count", "created_at")

    # Enable admin autocomplete widgets for related fields
    autocomplete_fields = ("uploader", "product", "additional_products")


@admin.register(VideoLike)
class VideoLikeAdmin(admin.ModelAdmin):
    list_display = ("user", "video", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "video__description")
    readonly_fields = ("created_at",)


@admin.register(Purchase)
class PurchaseAdmin(PurchaseAdminMixin, admin.ModelAdmin):
    list_display = ("buyer", "product", "quantity", "purchase_price", "purchase_date")
    list_filter = ("purchase_date",)
    search_fields = ("buyer__username", "product__name")
    readonly_fields = ("purchase_date",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.user_profile.role.code == "business_owner":
            return qs.filter(product__user=request.user)
        elif request.user.user_profile.role.code == "business_staff":
            return qs.filter(product__user=request.user)
        return qs


@admin.register(Bid)
class BidAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("bidder", "product", "bid_amount", "max_bid_amount", "bid_date")
    list_filter = ("bid_date",)
    search_fields = ("bidder__username", "product__name")
    readonly_fields = ("bid_date",)

    # Only admin, manager, and agent can manage bids
    view_roles = ["admin", "manager", "agent", "business_owner"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin", "manager"]


@admin.register(ChatMessage)
class ChatMessageAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("sender", "message", "timestamp")
    list_filter = ("timestamp",)
    search_fields = ("sender__username", "message")
    readonly_fields = ("timestamp",)

    # Business owners can only see their messages
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.user_profile.role.code == "business_owner":
            return qs.filter(sender=request.user)
        return qs


@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    list_display = ("purchase", "transaction_id", "amount", "status", "payment_date")
    list_filter = ("status", "payment_date")
    search_fields = ("transaction_id", "purchase__buyer__username")
    readonly_fields = ("payment_date", "transaction_id")


@admin.register(UserInteraction)
class UserInteractionAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("user", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("user__username", "event_type")
    readonly_fields = ("created_at",)

    # Only admin and manager can view user interactions
    view_roles = ["admin", "manager"]
    add_roles = ["admin"]
    change_roles = ["admin"]
    delete_roles = ["admin"]


@admin.register(UserProductImage)
class UserProductImageAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("product", "image", "alt_text")
    list_filter = ("product",)
    search_fields = ("product__name", "alt_text")


@admin.register(Feedback)
class FeedbackAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("user", "product", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "product__name", "comment")
    readonly_fields = ("created_at",)

    # Business owners can only see feedback for their products
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.user_profile.role.code == "business_owner":
            return qs.filter(product__user=request.user)
        return qs


@admin.register(MarketplaceUserProduct)
class MarketplaceUserProductAdmin(MarketplaceProductAdminMixin, admin.ModelAdmin):
    list_display = ("name", "user", "price", "stock", "is_verified", "created_at")
    list_filter = ("is_verified", "created_at", "category")
    search_fields = ("name", "user__username", "description")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.user_profile.role.code == "business_owner":
            return qs.filter(user=request.user)
        elif request.user.user_profile.role.code == "business_staff":
            return qs.filter(user=request.user)
        return qs


@admin.register(Notification)
class NotificationAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("user", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("user__username", "message")
    readonly_fields = ("created_at",)

    view_roles = ["admin", "manager", "agent", "business_owner", "business_staff"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin", "manager"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, "user_profile"):
            return qs.filter(user=request.user)
        return qs


@admin.register(Cart)
class CartAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("user", "created_at", "item_count")
    list_filter = ("created_at",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "Items"


@admin.register(CartItem)
class CartItemAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("cart", "product", "quantity")
    search_fields = ("cart__user__username", "product__name")


@admin.register(MarketplaceSale)
class MarketplaceSaleAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "buyer_display_name",
        "product",
        "quantity",
        "status",
        "payment_status",
        "total_amount",
        "sale_date",
    )
    list_filter = (
        "status",
        "payment_status",
        "sale_date",
        "currency",
        "is_deleted",
    )
    search_fields = (
        "order_number",
        "buyer__username",
        "buyer_name",
        "buyer_email",
        "product__product__name",
        "seller__username",
    )
    readonly_fields = (
        "order_number",
        "sale_date",
        "updated_at",
        "deleted_at",
        "subtotal",
        "total_amount",
    )
    fieldsets = (
        (
            _("Order Information"),
            {
                "fields": (
                    "order_number",
                    "status",
                    "payment_status",
                    "sale_date",
                    "updated_at",
                )
            },
        ),
        (
            _("Buyer Information"),
            {
                "fields": (
                    "buyer",
                    "buyer_name",
                    "buyer_email",
                    "buyer_phone",
                )
            },
        ),
        (
            _("Product Information"),
            {
                "fields": (
                    "product",
                    "seller",
                    "quantity",
                    "unit_price_at_purchase",
                    "unit_price",
                )
            },
        ),
        (
            _("Pricing"),
            {
                "fields": (
                    "subtotal",
                    "tax_amount",
                    "shipping_cost",
                    "total_amount",
                    "currency",
                )
            },
        ),
        (
            _("Payment Information"),
            {
                "fields": (
                    "payment_method",
                    "transaction_id",
                )
            },
        ),
        (
            _("Delivery Information"),
            {"fields": ("delivery",)},
        ),
        (
            _("Additional Information"),
            {"fields": ("notes",)},
        ),
        (
            _("Soft Delete"),
            {
                "classes": ("collapse",),
                "fields": (
                    "is_deleted",
                    "deleted_at",
                ),
            },
        ),
    )

    def buyer_display_name(self, obj):
        """Display buyer name with fallback."""
        return obj.buyer_display_name

    buyer_display_name.short_description = _("Buyer")
    buyer_display_name.admin_order_field = "buyer__username"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("buyer", "product", "seller", "delivery")

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        obj.delete()  # Uses soft delete

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()  # Uses soft delete


@admin.register(Delivery)
class DeliveryAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = (
        "customer_name",
        "phone_number",
        "city",
        "state",
        "delivery_status",
        "delivery_source_display",
        "tracking_number",
        "created_at",
    )
    list_filter = ("city", "state", "delivery_status", "created_at")
    search_fields = ("customer_name", "phone_number", "address", "tracking_number")
    readonly_fields = ("created_at", "updated_at", "delivery_source")

    fieldsets = (
        (_("Source"), {"fields": ("cart", "sale", "marketplace_sale", "marketplace_order", "delivery_source")}),
        (_("Customer Information"), {"fields": ("customer_name", "phone_number", "email")}),
        (_("Delivery Address"), {"fields": ("address", "city", "state", "zip_code", "latitude", "longitude")}),
        (_("Delivery Status"), {"fields": ("delivery_status", "tracking_number")}),
        (
            _("Delivery Personnel"),
            {"fields": ("delivery_person_name", "delivery_person_phone", "delivery_service"), "classes": ("collapse",)},
        ),
        (_("Delivery Times"), {"fields": ("estimated_delivery_date", "actual_delivery_date"), "classes": ("collapse",)}),
        (_("Additional Information"), {"fields": ("additional_instructions", "shop_id"), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def delivery_source_display(self, obj):
        """Display the source of the delivery in a readable format."""
        return obj.delivery_source

    delivery_source_display.short_description = _("Source")

    view_roles = ["admin", "manager", "agent"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin"]


# ==========================================
# New Marketplace Order Models Admin
# ==========================================


@admin.register(DeliveryInfo)
class DeliveryInfoAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    """Admin interface for delivery information."""

    list_display = ("customer_name", "phone_number", "city", "state", "zip_code", "created_at")
    list_filter = ("city", "state", "created_at")
    search_fields = ("customer_name", "phone_number", "address", "city")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (_("Customer Information"), {"fields": ("customer_name", "phone_number")}),
        (_("Address"), {"fields": ("address", "city", "state", "zip_code")}),
        (_("Location"), {"fields": ("latitude", "longitude"), "classes": ("collapse",)}),
        (_("Instructions"), {"fields": ("delivery_instructions",), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    view_roles = ["admin", "manager", "agent"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin"]


class MarketplaceOrderItemInline(admin.TabularInline):
    """Inline admin for order items within orders."""

    model = MarketplaceOrderItem
    extra = 0
    readonly_fields = ("total_price", "created_at", "updated_at")
    fields = ("product", "quantity", "unit_price", "total_price")

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(self.readonly_fields)
        if obj:  # Editing existing order
            readonly_fields.extend(["product", "quantity"])
        return readonly_fields


class OrderTrackingEventInline(admin.TabularInline):
    """Inline admin for tracking events within orders."""

    model = OrderTrackingEvent
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("status", "message", "location", "created_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(marketplace_order__isnull=False)


@admin.register(MarketplaceOrder)
class MarketplaceOrderAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    """Comprehensive admin interface for marketplace orders."""

    list_display = (
        "order_number",
        "customer",
        "order_status",
        "payment_status",
        "total_amount",
        "created_at",
        "items_count",
    )
    list_filter = (
        "order_status",
        "payment_status",
        "currency",
        "payment_method",
        "created_at",
        "delivered_at",
        "is_deleted",
    )
    search_fields = (
        "order_number",
        "customer__username",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "transaction_id",
        "tracking_number",
    )
    readonly_fields = ("order_number", "created_at", "updated_at", "delivered_at", "items_count", "total_items_quantity")

    inlines = [MarketplaceOrderItemInline, OrderTrackingEventInline]

    fieldsets = (
        (_("Order Information"), {"fields": ("order_number", "customer", "created_at", "updated_at")}),
        (_("Status"), {"fields": ("order_status", "payment_status")}),
        (_("Financial Information"), {"fields": ("total_amount", "currency")}),
        (_("Payment Details"), {"fields": ("payment_method", "transaction_id"), "classes": ("collapse",)}),
        (_("Delivery"), {"fields": ("delivery", "tracking_number", "delivered_at", "estimated_delivery_date")}),
        (_("Additional Information"), {"fields": ("notes",), "classes": ("collapse",)}),
        (_("Summary"), {"fields": ("items_count", "total_items_quantity"), "classes": ("collapse",)}),
        (_("Soft Delete"), {"fields": ("is_deleted", "deleted_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("customer", "delivery").prefetch_related("items")

    def items_count(self, obj):
        """Number of different products in the order."""
        return obj.items.count()

    items_count.short_description = _("Items Count")
    items_count.admin_order_field = "items__count"

    def total_items_quantity(self, obj):
        """Total quantity of all items."""
        return sum(item.quantity for item in obj.items.all())

    total_items_quantity.short_description = _("Total Quantity")

    # Permission settings
    view_roles = ["admin", "manager", "agent"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin"]

    # Custom actions
    actions = ["mark_as_confirmed", "mark_as_shipped", "mark_as_delivered", "cancel_orders"]

    def mark_as_confirmed(self, request, queryset):
        """Mark selected orders as confirmed."""
        count = 0
        for order in queryset:
            if order.order_status == "pending":
                order.order_status = "confirmed"
                order.save()
                count += 1

        self.message_user(request, f"{count} order(s) marked as confirmed.")

    mark_as_confirmed.short_description = _("Mark selected orders as confirmed")

    def mark_as_shipped(self, request, queryset):
        """Mark selected orders as shipped."""
        count = 0
        for order in queryset:
            if order.order_status in ["confirmed", "processing"]:
                order.order_status = "shipped"
                order.save()
                count += 1

        self.message_user(request, f"{count} order(s) marked as shipped.")

    mark_as_shipped.short_description = _("Mark selected orders as shipped")

    def mark_as_delivered(self, request, queryset):
        """Mark selected orders as delivered."""
        count = 0
        for order in queryset:
            if order.order_status in ["shipped", "in_transit"] and order.payment_status == "paid":
                order.mark_as_delivered()
                count += 1

        self.message_user(request, f"{count} order(s) marked as delivered.")

    mark_as_delivered.short_description = _("Mark selected orders as delivered")

    def cancel_orders(self, request, queryset):
        """Cancel selected orders."""
        count = 0
        for order in queryset:
            if order.can_cancel:
                order.cancel_order(reason="Admin cancellation")
                count += 1

        self.message_user(request, f"{count} order(s) cancelled.")

    cancel_orders.short_description = _("Cancel selected orders")


@admin.register(MarketplaceOrderItem)
class MarketplaceOrderItemAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    """Admin interface for individual order items."""

    list_display = ("order_number", "product_name", "quantity", "unit_price", "total_price", "created_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("order__order_number", "product__product__name", "product__listed_price")
    readonly_fields = ("total_price", "created_at", "updated_at")

    fieldsets = (
        (_("Order Information"), {"fields": ("order",)}),
        (_("Product Details"), {"fields": ("product", "quantity", "unit_price", "total_price")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("order", "product", "product__product")

    def order_number(self, obj):
        """Get order number for display."""
        return obj.order.order_number

    order_number.short_description = _("Order Number")
    order_number.admin_order_field = "order__order_number"

    def product_name(self, obj):
        """Get product name for display."""
        return obj.product.product.name

    product_name.short_description = _("Product")
    product_name.admin_order_field = "product__product__name"

    view_roles = ["admin", "manager", "agent"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin"]


# Enhanced OrderTrackingEvent Admin for both order types
@admin.register(OrderTrackingEvent)
class OrderTrackingEventAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    """Enhanced admin interface for order tracking events supporting both order types."""

    list_display = ("order_number", "order_type", "status", "message", "location", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("marketplace_sale__order_number", "marketplace_order__order_number", "status", "message", "location")
    readonly_fields = ("created_at", "order_number")

    fieldsets = (
        (_("Order Reference"), {"fields": ("marketplace_sale", "marketplace_order")}),
        (_("Event Details"), {"fields": ("status", "message", "location")}),
        (_("Location Data"), {"fields": ("latitude", "longitude"), "classes": ("collapse",)}),
        (_("Additional Data"), {"fields": ("metadata",), "classes": ("collapse",)}),
        (_("Timestamp"), {"fields": ("created_at",)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("marketplace_sale", "marketplace_order")

    def order_type(self, obj):
        """Identify the type of order."""
        if obj.marketplace_order:
            return "Marketplace Order"
        elif obj.marketplace_sale:
            return "Marketplace Sale"
        return "Unknown"

    order_type.short_description = _("Order Type")

    def order_number(self, obj):
        """Get order number from either order type."""
        return obj.order_number

    order_number.short_description = _("Order Number")

    view_roles = ["admin", "manager", "agent"]
    add_roles = ["admin", "manager", "agent"]
    change_roles = ["admin", "manager", "agent"]
    delete_roles = ["admin"]


# Invoice Line Item Inline
class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    readonly_fields = ("total_price",)
    fields = ("product_name", "product_sku", "description", "quantity", "unit_price", "total_price", "marketplace_product")


@admin.register(Invoice)
class InvoiceAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer_name",
        "customer_email",
        "total_amount",
        "status",
        "invoice_date",
        "source_order_number",
        "pdf_available",
    )
    list_filter = ("status", "invoice_date", "currency", "created_at")
    search_fields = (
        "invoice_number",
        "customer_name",
        "customer_email",
        "marketplace_sale__order_number",
        "marketplace_order__order_number",
        "payment_transaction__order_number",
    )
    readonly_fields = (
        "invoice_number",
        "invoice_date",
        "created_at",
        "updated_at",
        "sent_at",
        "source_order_number",
        "is_overdue",
    )

    inlines = [InvoiceLineItemInline]

    fieldsets = (
        (_("Invoice Information"), {"fields": ("invoice_number", "invoice_date", "due_date", "status", "is_overdue")}),
        (
            _("Source Order"),
            {
                "fields": ("marketplace_sale", "marketplace_order", "payment_transaction", "source_order_number"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Customer Information"),
            {"fields": ("customer", "customer_name", "customer_email", "customer_phone", "billing_address")},
        ),
        (_("Financial Details"), {"fields": ("subtotal", "tax_amount", "shipping_cost", "total_amount", "currency")}),
        (_("Files & Communication"), {"fields": ("pdf_file", "sent_at", "notes")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = [
        "generate_pdf_action",
        "send_invoice_email_action",
        "mark_as_sent_action",
        "mark_as_paid_action",
        "download_invoice_pdf_action",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("customer", "marketplace_sale", "marketplace_order", "payment_transaction")

    def source_order_number(self, obj):
        """Get the source order number"""
        return obj.source_order_number or "-"

    source_order_number.short_description = _("Source Order")

    def pdf_available(self, obj):
        """Check if PDF is available"""
        return bool(obj.pdf_file)

    pdf_available.boolean = True
    pdf_available.short_description = _("PDF Available")

    def is_overdue(self, obj):
        """Check if invoice is overdue"""
        return obj.is_overdue

    is_overdue.boolean = True
    is_overdue.short_description = _("Overdue")

    # Custom Actions
    def generate_pdf_action(self, request, queryset):
        """Generate PDF for selected invoices"""
        from .services import InvoiceGenerationService

        success_count = 0
        error_count = 0

        for invoice in queryset:
            try:
                if InvoiceGenerationService.generate_invoice_pdf(invoice):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"Error generating PDF for invoice {invoice.invoice_number}: {str(e)}")

        if success_count > 0:
            self.message_user(request, f"Successfully generated {success_count} PDF(s).")
        if error_count > 0:
            self.message_user(request, f"Failed to generate {error_count} PDF(s). Check logs for details.", level="ERROR")

    generate_pdf_action.short_description = _("Generate PDF for selected invoices")

    def send_invoice_email_action(self, request, queryset):
        """Send email for selected invoices"""
        from .services import InvoiceGenerationService

        success_count = 0
        error_count = 0

        for invoice in queryset:
            try:
                if InvoiceGenerationService.send_invoice_email(invoice):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"Error sending email for invoice {invoice.invoice_number}: {str(e)}")

        if success_count > 0:
            self.message_user(request, f"Successfully sent {success_count} invoice email(s).")
        if error_count > 0:
            self.message_user(request, f"Failed to send {error_count} email(s). Check logs for details.", level="ERROR")

    send_invoice_email_action.short_description = _("Send invoice email for selected invoices")

    def mark_as_sent_action(self, request, queryset):
        """Mark selected invoices as sent"""
        from django.utils import timezone

        updated = queryset.filter(status="draft").update(status="sent", sent_at=timezone.now())

        if updated > 0:
            self.message_user(request, f"Successfully marked {updated} invoice(s) as sent.")
        else:
            self.message_user(request, "No draft invoices were updated.", level="WARNING")

    mark_as_sent_action.short_description = _("Mark selected invoices as sent")

    def mark_as_paid_action(self, request, queryset):
        """Mark selected invoices as paid"""
        updated = queryset.exclude(status="paid").update(status="paid")

        if updated > 0:
            self.message_user(request, f"Successfully marked {updated} invoice(s) as paid.")
        else:
            self.message_user(request, "No unpaid invoices were updated.", level="WARNING")

    mark_as_paid_action.short_description = _("Mark selected invoices as paid")

    def download_invoice_pdf_action(self, request, queryset):
        """Download PDF for first selected invoice"""
        invoice = queryset.first()
        if not invoice:
            self.message_user(request, "No invoice selected.", level="ERROR")
            return

        if not invoice.pdf_file:
            self.message_user(request, f"No PDF available for invoice {invoice.invoice_number}.", level="ERROR")
            return

        from django.http import HttpResponse

        try:
            with open(invoice.pdf_file.path, "rb") as pdf_file:
                response = HttpResponse(pdf_file.read(), content_type="application/pdf")
                filename = f"invoice_{invoice.invoice_number}.pdf"
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                return response
        except Exception as e:
            self.message_user(request, f"Error downloading PDF: {str(e)}", level="ERROR")

    download_invoice_pdf_action.short_description = _("Download PDF for first selected invoice")

    # Role-based permissions
    view_roles = ["admin", "manager", "accountant", "agent"]
    add_roles = ["admin", "manager", "accountant"]
    change_roles = ["admin", "manager", "accountant"]
    delete_roles = ["admin", "manager"]


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("invoice", "product_name", "product_sku", "quantity", "unit_price", "total_price")
    list_filter = ("invoice__status", "invoice__invoice_date")
    search_fields = ("invoice__invoice_number", "product_name", "product_sku", "invoice__customer_name")
    readonly_fields = ("total_price",)

    fieldsets = (
        (_("Product Information"), {"fields": ("product_name", "product_sku", "description", "marketplace_product")}),
        (_("Pricing"), {"fields": ("quantity", "unit_price", "total_price")}),
        (_("Invoice"), {"fields": ("invoice",)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("invoice", "marketplace_product")

    # Role-based permissions
    view_roles = ["admin", "manager", "accountant", "agent"]
    add_roles = ["admin", "manager", "accountant"]
    change_roles = ["admin", "manager", "accountant"]
    delete_roles = ["admin", "manager"]
