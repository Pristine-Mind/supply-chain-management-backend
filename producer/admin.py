from django.contrib import admin
from .models import Producer, Customer, Product, Order, Sale, StockList, MarketplaceProduct, ProductImage


@admin.register(Producer)
class ProducerAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact', 'email', 'registration_number', 'created_at', 'updated_at')
    search_fields = ('name', 'email', 'registration_number')
    list_filter = ('created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer_type', 'contact', 'email', 'credit_limit', 'current_balance', 'created_at', 'updated_at')
    search_fields = ('name', 'email', 'customer_type')
    list_filter = ('customer_type', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'producer', 'sku', 'price', 'cost_price', 'stock', 'reorder_level', 'is_active', 'created_at', 'updated_at')
    search_fields = ('name', 'sku')
    list_filter = ('is_active', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['producer']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'product', 'quantity', 'status', 'total_price', 'order_date', 'delivery_date')
    search_fields = ('order_number', 'customer__name', 'product__name')
    list_filter = ('status', 'order_date', 'delivery_date')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-order_date',)
    autocomplete_fields = ['customer', 'product']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('order', 'quantity', 'sale_price', 'sale_date', 'payment_status', 'payment_due_date')
    search_fields = ('order__customer__name', 'order__product__name', 'order__order_number')
    list_filter = ('sale_date', 'payment_status')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['order',]


@admin.register(StockList)
class StockListAdmin(admin.ModelAdmin):
    list_display = ('product', 'moved_date')
    search_fields = ('product__name',)
    list_filter = ('moved_date',)
    readonly_fields = ('moved_date',)
    autocomplete_fields = ['product']


@admin.register(MarketplaceProduct)
class MarketplaceProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ['product']


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    autocomplete_fields = ['product',]
