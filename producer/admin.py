from django.contrib import admin
from .models import Producer, Customer, Product, Order, Sale, StockList


@admin.register(Producer)
class ProducerAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact', 'email', 'registration_number', 'created_at', 'updated_at')
    search_fields = ('name', 'email', 'registration_number')
    list_filter = ('created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'producer', 'customer_type', 'contact', 'email', 'credit_limit', 'current_balance', 'created_at', 'updated_at')
    search_fields = ('name', 'email', 'customer_type')
    list_filter = ('customer_type', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'producer', 'sku', 'price', 'cost_price', 'stock', 'reorder_level', 'is_active', 'created_at', 'updated_at')
    search_fields = ('name', 'sku')
    list_filter = ('producer', 'is_active', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'product', 'quantity', 'status', 'total_price', 'order_date', 'delivery_date', 'payment_status')
    search_fields = ('order_number', 'customer__name', 'product__name')
    list_filter = ('status', 'payment_status', 'order_date', 'delivery_date')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-order_date',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'quantity', 'sale_price', 'sale_date', 'customer_name', 'customer_contact')
    search_fields = ('customer__name', 'product__name', 'customer_name')
    list_filter = ('sale_date',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockList)
class StockListAdmin(admin.ModelAdmin):
    list_display = ('product', 'moved_date')
    search_fields = ('product__name',)
    list_filter = ('moved_date',)
    readonly_fields = ('moved_date',)
