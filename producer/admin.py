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
    B2BPriceTier,
    Brand,
    Category,
    CreatorProfile,
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


class ProductAdminForm(forms.ModelForm):
    """
    Custom form for Product admin with enhanced choice field handling
    """

    class Meta:
        model = Product
        fields = "__all__"
        widgets = {
            "size": forms.Select(attrs={"class": "form-control"}),
            "color": forms.Select(attrs={"class": "form-control"}),
            "additional_information": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add help text for choice fields
        if "size" in self.fields:
            self.fields["size"].help_text = "Select the size from available options or leave blank for non-sized products"
        if "color" in self.fields:
            self.fields["color"].help_text = "Select the color from available options or leave blank for colorless products"


class MarketplaceProductAdminForm(forms.ModelForm):
    """
    Custom form for MarketplaceProduct admin with enhanced choice field handling
    """

    class Meta:
        model = MarketplaceProduct
        fields = "__all__"
        widgets = {
            "size": forms.Select(attrs={"class": "form-control"}),
            "color": forms.Select(attrs={"class": "form-control"}),
            "additional_information": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add help text for choice fields
        if "size" in self.fields:
            self.fields["size"].help_text = "Select size for this marketplace listing (overrides product size)"
        if "color" in self.fields:
            self.fields["color"].help_text = "Select color for this marketplace listing (overrides product color)"

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        size = cleaned_data.get("size")
        color = cleaned_data.get("color")

        # If no size/color specified, inherit from product
        if product:
            if not size and product.size:
                cleaned_data["size"] = product.size
            if not color and product.color:
                cleaned_data["color"] = product.color

        return cleaned_data


@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "display_name", "handle", "follower_count", "created_at")
    search_fields = ("user__username", "handle", "display_name")
    readonly_fields = ("created_at", "updated_at")


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


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    """Admin interface for Brand model"""

    list_display = (
        "name",
        "country_of_origin",
        "category",
        "subcategory",
        "is_active",
        "is_verified",
        "website",
        "get_products_count",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "description", "country_of_origin", "contact_email")
    list_filter = ("is_active", "is_verified", "country_of_origin", "category", "created_at")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "logo", "website")}),
        ("Contact Information", {"fields": ("contact_email", "contact_phone", "country_of_origin")}),
        ("Category", {"fields": ("category", "subcategory", "sub_subcategory")}),
        ("Additional Information", {"fields": ("manufacturer_info",)}),
        ("Status", {"fields": ("is_active", "is_verified")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_products_count(self, obj):
        """Get the number of active products for this brand"""
        return obj.products.filter(is_active=True).count()

    get_products_count.short_description = "Active Products"
    get_products_count.admin_order_field = "products__count"

    def get_queryset(self, request):
        """Override to add product count annotation for sorting"""
        qs = super().get_queryset(request)
        qs = qs.prefetch_related("products")
        return qs


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
    form = ProductAdminForm

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)
        # Staff and superusers can see everything
        if request.user.is_superuser:
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

    def get_size_display(self, obj):
        """Display size choice with label"""
        if obj.size:
            return f"{obj.get_size_display()} ({obj.size})"
        return "-"

    get_size_display.short_description = "Size"

    def get_color_display(self, obj):
        """Display color choice with label"""
        if obj.color:
            return f"{obj.get_color_display()} ({obj.color})"
        return "-"

    get_color_display.short_description = "Color"

    def has_additional_info(self, obj):
        """Show if product has additional information"""
        return bool(obj.additional_information)

    has_additional_info.boolean = True
    has_additional_info.short_description = "Has Additional Info"

    def get_brand_display(self, obj):
        """Display brand name with verification status"""
        if obj.brand:
            verified = " ✓" if obj.brand.is_verified else " ✗"
            return f"{obj.brand.name}{verified}"
        return "Unbranded"

    get_brand_display.short_description = "Brand"

    list_display = (
        "name",
        "producer",
        "get_brand_display",
        "sku",
        "price",
        "cost_price",
        "stock",
        "reorder_level",
        "get_size_display",
        "get_color_display",
        "has_additional_info",
        "is_active",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "sku", "size", "color", "brand__name")
    list_filter = ("is_active", "brand", "size", "color", "category", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ["producer", "brand"]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "sku", "producer", "brand", "user")}),
        ("Category", {"fields": ("category", "subcategory", "sub_subcategory", "old_category")}),
        ("Product Attributes", {"fields": ("size", "color", "additional_information", "location")}),
        ("Pricing & Inventory", {"fields": ("price", "cost_price", "stock", "reorder_level", "is_active")}),
        (
            "Supply Chain Management",
            {
                "fields": (
                    "avg_daily_demand",
                    "stddev_daily_demand",
                    "safety_stock",
                    "reorder_point",
                    "reorder_quantity",
                    "lead_time_days",
                    "projected_stockout_date_field",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Metadata", {"fields": ("is_marketplace_created", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


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


class B2BPriceTierInline(admin.TabularInline):
    model = B2BPriceTier
    extra = 1
    fields = ["customer_type", "min_quantity", "price_per_unit", "discount_percentage", "is_active"]
    verbose_name = "B2B Price Tier"
    verbose_name_plural = "B2B Price Tiers"


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
    form = MarketplaceProductAdminForm

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        qs = super().get_queryset(request)

        # Determine base filtered queryset according to user role
        if request.user.is_superuser:
            filtered = qs
        elif not hasattr(request.user, "user_profile"):
            filtered = qs.none()
        else:
            user_profile = request.user.user_profile
            if not user_profile.role:
                filtered = qs.none()
            elif user_profile.role.code in ["business_owner", "business_staff"] and user_profile.shop_id:
                filtered = qs.filter(product__user__user_profile__shop_id=user_profile.shop_id)
            elif user_profile.role.code in ["agent", "admin"] and user_profile.shop_id:
                filtered = qs.all()
            else:
                filtered = qs.none()

        # Avoid N+1 by selecting related product and commonly accessed product relations
        return filtered.select_related("product", "product__brand", "product__user")

    def get_size_display(self, obj):
        """Display size choice with label or inherited from product"""
        if obj.size:
            return f"{obj.get_size_display()} ({obj.size})"
        elif obj.product and obj.product.size:
            return f"[Inherited] {obj.product.get_size_display()} ({obj.product.size})"
        return "-"

    get_size_display.short_description = "Size"

    def get_color_display(self, obj):
        """Display color choice with label or inherited from product"""
        if obj.color:
            return f"{obj.get_color_display()} ({obj.color})"
        elif obj.product and obj.product.color:
            return f"[Inherited] {obj.product.get_color_display()} ({obj.product.color})"
        return "-"

    get_color_display.short_description = "Color"

    def has_additional_info(self, obj):
        """Show if marketplace product has additional information"""
        return bool(obj.additional_information or (obj.product and obj.product.additional_information))

    has_additional_info.boolean = True
    has_additional_info.short_description = "Has Additional Info"

    def get_brand_display(self, obj):
        """Display brand name from associated product"""
        if obj.product and obj.product.brand:
            verified = " ✓" if obj.product.brand.is_verified else " ✗"
            return f"{obj.product.brand.name}{verified}"
        return "Unbranded"

    get_brand_display.short_description = "Brand"

    list_display = (
        "id",
        "product",
        "get_brand_display",
        "listed_price",
        "discounted_price",
        "percent_off",
        "get_size_display",
        "get_color_display",
        "has_additional_info",
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
    search_fields = ("product__name", "product__brand__name", "size", "color")
    list_filter = ("is_available", "is_made_in_nepal", "is_featured", "product__brand", "size", "color", "listed_date")
    autocomplete_fields = ["product"]
    readonly_fields = ("listed_date",)

    fieldsets = (
        ("Product Information", {"fields": ("product",)}),
        ("Product Attributes", {"fields": ("size", "color", "additional_information")}),
        ("Pricing & Offers", {"fields": ("listed_price", "discounted_price", "offer_start", "offer_end")}),
        (
            "B2B Sales",
            {
                "fields": ("enable_b2b_sales", "b2b_price", "b2b_min_quantity"),
                "classes": ("collapse",),
                "description": "Configure business-to-business pricing and requirements",
            },
        ),
        ("Availability & Shipping", {"fields": ("is_available", "min_order", "estimated_delivery_days", "shipping_cost")}),
        ("Marketing & Features", {"fields": ("is_featured", "is_made_in_nepal", "rank_score", "made_for_you")}),
        ("Analytics", {"fields": ("recent_purchases_count", "view_count"), "classes": ("collapse",)}),
    )

    inlines = [
        MarketplaceBulkPriceTierInline,
        B2BPriceTierInline,
        MarketplaceProductVariantInline,
        MarketplaceProductReviewInline,
    ]


@admin.register(MarketplaceBulkPriceTier)
class MarketplaceBulkPriceTierAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_owner"  # Business owners and above can view and edit
    list_display = ("product", "min_quantity", "discount_percent", "price_per_unit")
    search_fields = ("product__product__name",)
    list_filter = ("product",)


@admin.register(B2BPriceTier)
class B2BPriceTierAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    required_role = "business_owner"  # Business owners and above can view and edit
    list_display = ("product", "customer_type", "min_quantity", "price_per_unit", "discount_percentage", "is_active")
    search_fields = ("product__product__name",)
    list_filter = ("customer_type", "is_active", "product")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            None,
            {"fields": ("product", "customer_type", "min_quantity", "price_per_unit", "discount_percentage", "is_active")},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


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
