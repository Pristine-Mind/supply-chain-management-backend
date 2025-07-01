from django.contrib import admin

from .models import (
    AuditLog,
    Customer,
    LedgerEntry,
    MarketplaceProduct,
    Order,
    Producer,
    Product,
    ProductImage,
    PurchaseOrder,
    Sale,
    StockList,
)


@admin.register(Producer)
class ProducerAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "email", "registration_number", "created_at", "updated_at")
    search_fields = ("name", "email", "registration_number")
    list_filter = ("created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
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
class ProductAdmin(admin.ModelAdmin):
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
class OrderAdmin(admin.ModelAdmin):
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
class SaleAdmin(admin.ModelAdmin):
    list_display = ("order", "quantity", "sale_price", "sale_date", "payment_status", "payment_due_date")
    search_fields = ("order__customer__name", "order__product__name", "order__order_number")
    list_filter = ("sale_date", "payment_status")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = [
        "order",
    ]


@admin.register(StockList)
class StockListAdmin(admin.ModelAdmin):
    list_display = ("product", "moved_date")
    search_fields = ("product__name",)
    list_filter = ("moved_date",)
    readonly_fields = ("moved_date",)
    autocomplete_fields = ["product"]


@admin.register(MarketplaceProduct)
class MarketplaceProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ["product"]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "product",
    ]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
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
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "transaction_type", "reference_id", "entity_id", "amount")
    search_fields = ("reference_id", "user__username", "transaction_type")
    list_filter = ("transaction_type", "user")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "quantity", "created_at", "approved", "sent_to_vendor")
    search_fields = ("product__name",)
    list_filter = ("approved", "sent_to_vendor")
    readonly_fields = ("created_at",)
    autocomplete_fields = ["product"]
