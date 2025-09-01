from django.contrib import admin
from django.utils.html import format_html

from .models import PaymentTransaction, PaymentTransactionItem


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "user",
        "gateway",
        "total_amount",
        "status",
        "created_at",
        "completed_at",
    ]
    list_filter = ["gateway", "status", "created_at", "completed_at"]
    search_fields = ["order_number", "user__username", "user__email", "gateway_transaction_id"]
    readonly_fields = ["transaction_id", "order_number", "created_at", "updated_at"]

    fieldsets = (
        ("Basic Information", {"fields": ("transaction_id", "order_number", "user", "cart")}),
        ("Payment Details", {"fields": ("gateway", "gateway_transaction_id", "bank", "status")}),
        ("Amount Information", {"fields": ("subtotal", "tax_amount", "shipping_cost", "total_amount")}),
        ("Customer Information", {"fields": ("customer_name", "customer_email", "customer_phone")}),
        ("Additional Information", {"fields": ("return_url", "notes", "metadata")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "completed_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "cart")


@admin.register(PaymentTransactionItem)
class PaymentTransactionItemAdmin(admin.ModelAdmin):
    list_display = [
        "payment_transaction",
        "product",
        "quantity",
        "unit_price",
        "total_amount",
        "marketplace_sale_link",
    ]
    list_filter = ["payment_transaction__gateway", "payment_transaction__status"]
    search_fields = [
        "payment_transaction__order_number",
        "product__product__name",
        "marketplace_sale__order_number",
    ]
    readonly_fields = ["marketplace_sale_link"]

    def marketplace_sale_link(self, obj):
        if obj.marketplace_sale:
            return format_html(
                '<a href="/admin/market/marketplacesale/{}/change/">{}</a>',
                obj.marketplace_sale.id,
                obj.marketplace_sale.order_number,
            )
        return "-"

    marketplace_sale_link.short_description = "Marketplace Sale"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("payment_transaction", "product", "marketplace_sale")
