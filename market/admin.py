from django.contrib import admin
from .models import Purchase, Bid, ChatMessage, Payment


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("buyer", "product", "quantity", "purchase_price", "purchase_date")
    list_filter = ("purchase_date",)
    search_fields = ("buyer__username", "product__name")


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ("bidder", "product", "bid_amount", "max_bid_amount", "bid_date")
    list_filter = ("bid_date",)
    search_fields = ("bidder__username", "product__name")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "message", "timestamp")
    list_filter = ("timestamp",)
    search_fields = ("sender__username", "receiver__username", "message")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("purchase", "transaction_id", "amount", "status", "payment_date")
    list_filter = ("status", "payment_date")
    search_fields = ("transaction_id", "purchase__buyer__username")
