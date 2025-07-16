from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from user.admin_mixins import RoleBasedAdminMixin

from .models import (
    AuditLog,
    Customer,
    DirectSale,
    LedgerEntry,
    MarketplaceBulkPriceTier,
    MarketplaceProduct,
    MarketplaceProductReview,
    MarketplaceProductVariant,
    Order,
    Producer,
    Product,
    ProductImage,
    PurchaseOrder,
    Sale,
    StockHistory,
    StockList,
)


@admin.register(Producer)
class ProducerAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit
    list_display = ("name", "contact", "email", "registration_number", "created_at", "updated_at")
    search_fields = ("name", "email", "registration_number")
    list_filter = ("created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # Staff and superusers can see everything
        if request.user.is_staff or request.user.is_superuser:
            return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()


@admin.register(Customer)
class CustomerAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view and edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = (
        "name",
        "customer_type",
        "contact",
        "email",
        "credit_limit",
        "current_balance",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "email", "customer_type")
    list_filter = ("customer_type", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = (
        "name",
        "producer",
        "sku",
        "price",
        "cost_price",
        "stock",
        "reorder_level",
        "is_active",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "sku")
    list_filter = ("is_active", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ["producer"]


@admin.register(Order)
class OrderAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view and edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = (
        "order_number",
        "customer",
        "product",
        "quantity",
        "status",
        "total_price",
        "order_date",
        "delivery_date",
    )
    search_fields = ("order_number", "customer__name", "product__name")
    list_filter = ("status", "order_date", "delivery_date")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-order_date",)
    autocomplete_fields = ["customer", "product"]


@admin.register(Sale)
class SaleAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(order__user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = ("order", "quantity", "sale_price", "sale_date", "payment_status", "payment_due_date")
    search_fields = ("order__customer__name", "order__product__name", "order__order_number")
    list_filter = ("sale_date", "payment_status")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = [
        "order",
    ]


@admin.register(StockList)
class StockListAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(product__user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = ("product", "moved_date")
    search_fields = ("product__name",)
    list_filter = ("moved_date",)
    readonly_fields = ("moved_date",)
    autocomplete_fields = ["product"]


@admin.register(StockHistory)
class StockHistoryAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, only managers and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(product__user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = ("product", "date", "quantity_in", "quantity_out", "user", "notes")
    search_fields = ("product__name", "user__username", "notes")
    list_filter = ("date", "product", "user")
    autocomplete_fields = ["product", "user"]
    date_hierarchy = "date"
    readonly_fields = ()


class MarketplaceBulkPriceTierInline(admin.TabularInline):
    model = MarketplaceBulkPriceTier
    extra = 1


class MarketplaceProductVariantInline(admin.TabularInline):
    model = MarketplaceProductVariant
    extra = 1


class MarketplaceProductReviewInline(admin.TabularInline):
    model = MarketplaceProductReview
    extra = 1
    # readonly_fields = ("user", "rating", "review_text", "created_at")


@admin.register(MarketplaceProduct)
class MarketplaceProductAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(product__user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = (
        "id",
        "product",
        "listed_price",
        "discounted_price",
        "percent_off",
        "is_offer_active",
        "estimated_delivery_days",
        "shipping_cost",
        "recent_purchases_count",
        "listed_date",
        "is_available",
        "min_order",
        "rank_score",
    )
    search_fields = ("product__name",)
    list_filter = ("is_available", "listed_date")
    autocomplete_fields = ["product"]
    readonly_fields = ("listed_date",)
    inlines = [
        MarketplaceBulkPriceTierInline,
        MarketplaceProductVariantInline,
        MarketplaceProductReviewInline,
    ]


@admin.register(MarketplaceBulkPriceTier)
class MarketplaceBulkPriceTierAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_owner"  # Business owners and above can view and edit
    list_display = ("product", "min_quantity", "discount_percent", "price_per_unit")
    search_fields = ("product__product__name",)
    list_filter = ("product",)


@admin.register(MarketplaceProductVariant)
class MarketplaceProductVariantAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit
    list_display = ("product", "name", "value", "additional_price", "stock")
    search_fields = ("product__product__name", "name", "value")
    list_filter = ("product", "name")


@admin.register(MarketplaceProductReview)
class MarketplaceProductReviewAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_owner"  # Business owners and above can view, only managers and above can edit
    list_display = ("product", "user", "rating", "created_at")
    search_fields = ("product__product__name", "user__username", "review_text")
    list_filter = ("rating", "created_at")
    readonly_fields = ("created_at",)


@admin.register(ProductImage)
class ProductImageAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit
    autocomplete_fields = [
        "product",
    ]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_owner"  # Business owners and above can view, only managers and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, "user_profile"):
            role = request.user.user_profile.role.code
            if role == "business_owner":
                # Business owners can only see their organization's ledger entries
                return qs.filter(product__user__user_profile__shop_id=request.user.user_profile.shop_id)
        return qs.none()

    list_display = (
        "id",
        "account_type",
        "amount",
        "debit",
        "reference_id",
        "related_entity",
    )
    search_fields = ("reference_id", "user__username", "account_type")
    list_filter = ("account_type", "debit", "user")


@admin.register(AuditLog)
class AuditLogAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "manager"  # Managers and above can view, only admins can edit

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # Prevent adding audit logs through admin

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False  # Prevent modifying audit logs through admin

    list_display = ("id", "transaction_type", "reference_id", "entity_id", "amount")
    search_fields = ("reference_id", "user__username", "transaction_type")
    list_filter = ("transaction_type", "user")


@admin.register(DirectSale)
class DirectSaleAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    """
    Admin interface for managing direct sales.
    """

    required_role = "business_staff"
    list_display = ("id", "product", "quantity", "unit_price", "total_amount", "sale_date", "user", "reference")
    list_filter = ("sale_date", "user")
    search_fields = ("product__name", "user__username", "reference", "notes")
    readonly_fields = ("sale_date", "created_at", "updated_at")
    date_hierarchy = "sale_date"
    autocomplete_fields = ["product", "user"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("product", "user")
        return qs


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_staff"  # Business staff and above can view, business_owner and above can edit

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # # Staff and superusers can see everything
        # if request.user.is_staff or request.user.is_superuser:
        #     return qs

        if not hasattr(request.user, "user_profile"):
            return qs.none()

        user_profile = request.user.user_profile
        if not user_profile.role:
            return qs.none()

        # Filter by shop_id if user is business_owner or business_staff
        if user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
            return qs.filter(product__user__user_profile__shop_id=user_profile.shop_id)
        # For other roles, only show their own records
        elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
            return qs.all()

        return qs.none()

    list_display = ("id", "product", "quantity", "created_at", "approved", "sent_to_vendor")
    search_fields = ("product__name",)
    list_filter = ("approved", "sent_to_vendor")
    readonly_fields = ("created_at",)
    autocomplete_fields = ["product"]
