from typing import Any

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest
from PIL import Image

from user.admin_mixins import RoleBasedAdminMixin

from .models import (
    AuditLog,
    Category,
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
    Subcategory,
    SubSubcategory,
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
        "is_featured",
        "is_made_in_nepal",
        "estimated_delivery_days",
        "shipping_cost",
        "recent_purchases_count",
        "listed_date",
        "is_available",
        "min_order",
        "rank_score",
    )
    search_fields = ("product__name",)
    list_filter = ("is_available", "is_made_in_nepal", "is_featured", "listed_date")
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


class ProductImageForm(forms.ModelForm):
    """Custom form that accepts AVIF uploads in the admin.

    Pillow may not validate AVIF files in some environments. We accept
    files with a .avif extension and skip PIL verification for them. For
    all other files we attempt to verify using Pillow to keep validation
    strict for standard formats.
    """

    image = forms.FileField(required=False)

    class Meta:
        model = ProductImage
        fields = "__all__"

    def clean_image(self):
        f = self.cleaned_data.get("image")
        if not f:
            return f

        name = getattr(f, "name", "") or ""
        if name.lower().endswith(".avif"):
            # Accept AVIF uploads without Pillow validation.
            return f

        # For non-AVIF files try to validate using Pillow
        try:
            # Pillow's verify() may consume the file pointer; reset after.
            img = Image.open(f)
            img.verify()
            f.seek(0)
        except Exception:
            raise ValidationError("Upload a valid image file.")

        return f


# Use the custom form in the admin so AVIF uploads are allowed.
ProductImageAdmin.form = ProductImageForm


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


# Category Administration
class SubSubcategoryInline(admin.TabularInline):
    model = SubSubcategory
    extra = 0
    fields = ("code", "name", "is_active")


class SubcategoryInline(admin.TabularInline):
    model = Subcategory
    extra = 0
    fields = ("code", "name", "is_active")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "code")
    readonly_fields = ("created_at", "updated_at")
    inlines = [SubcategoryInline]

    fieldsets = (
        (None, {"fields": ("code", "name", "description", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "is_active", "created_at", "updated_at")
    list_filter = ("category", "is_active", "created_at")
    search_fields = ("name", "code", "category__name")
    readonly_fields = ("created_at", "updated_at")
    inlines = [SubSubcategoryInline]

    fieldsets = (
        (None, {"fields": ("category", "code", "name", "description", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(SubSubcategory)
class SubSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "subcategory", "get_category", "is_active", "created_at", "updated_at")
    list_filter = ("subcategory__category", "subcategory", "is_active", "created_at")
    search_fields = ("name", "code", "subcategory__name", "subcategory__category__name")
    readonly_fields = ("created_at", "updated_at")

    def get_category(self, obj):
        return obj.subcategory.category.name

    get_category.short_description = "Category"
    get_category.admin_order_field = "subcategory__category__name"

    fieldsets = (
        (None, {"fields": ("subcategory", "code", "name", "description", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
