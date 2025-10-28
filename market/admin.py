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
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceSale,
    MarketplaceUserProduct,
    Notification,
    OrderTrackingEvent,
    Payment,
    Purchase,
    UserInteraction,
    UserProductImage,
)


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
    list_display = ("cart", "customer_name", "phone_number", "city", "state", "created_at")
    list_filter = ("city", "state", "created_at")
    search_fields = ("customer_name", "phone_number", "address")
    readonly_fields = ("created_at", "updated_at")

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
