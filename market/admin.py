import logging

from django.contrib import admin
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

try:
    from reversion.admin import VersionAdmin as BaseVersionAdmin
except ImportError:
    # Fallback to regular ModelAdmin if reversion is not available
    BaseVersionAdmin = admin.ModelAdmin

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
    Feedback,
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


@admin.register(OrderTrackingEvent)
class OrderTrackingEventAdmin(RoleBasedModelAdminMixin, admin.ModelAdmin):
    list_display = ("order", "status", "message", "location", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "message", "location")
    readonly_fields = ("created_at",)

    view_roles = ["admin", "manager", "agent", "business_owner", "business_staff"]
    add_roles = ["admin", "manager", "agent", "business_owner", "business_staff"]
    change_roles = ["admin", "manager", "agent", "business_owner", "business_staff"]
    delete_roles = ["admin", "manager"]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("order")
        if not request.user.is_staff and hasattr(request.user, "user_profile"):
            return qs.filter(Q(order__buyer=request.user) | Q(order__seller=request.user))
        return qs


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
class MarketplaceSaleAdmin(BaseVersionAdmin):
    list_display = (
        "order_number",
        "get_buyer_display",
        "product",
        "quantity",
        "status",
        "payment_status",
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
        "product__name",
        "shipping_address",
    )
    readonly_fields = (
        "order_number",
        "sale_date",
        "deleted_at",
    )
    fieldsets = (
        (
            _("Order Information"),
            {
                "fields": (
                    "order_number",
                    "status",
                    "sale_date",
                    "notes",
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
                    "quantity",
                    "unit_price_at_purchase",
                    "currency",
                    "tax_amount",
                    "shipping_cost",
                )
            },
        ),
        (
            _("Payment Information"),
            {
                "fields": (
                    "payment_status",
                    "payment_method",
                    "transaction_id",
                    "payment_date",
                )
            },
        ),
        (
            _("Shipping Information"),
            {
                "fields": (
                    "shipping_address",
                    "tracking_number",
                    "shipping_carrier",
                    "delivery_date",
                )
            },
        ),
        (
            _("Audit Information"),
            {
                "classes": ("collapse",),
                "fields": (
                    "is_deleted",
                    "deleted_at",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_buyer_display(self, obj):
        return obj.buyer_display

    get_buyer_display.short_description = _("Buyer")
    get_buyer_display.admin_order_field = "buyer__username"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("buyer", "product", "seller")

    def has_delete_permission(self, request, obj=None):
        # Only allow soft delete from the admin
        return False

    def delete_model(self, request, obj):
        # Override to perform soft delete
        obj.soft_delete()

    def delete_queryset(self, request, queryset):
        # Override to perform soft delete on multiple objects
        for obj in queryset:
            obj.soft_delete()


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
