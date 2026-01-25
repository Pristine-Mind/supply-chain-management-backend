import json
import time
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

import requests
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from market.utils import notify_event
from producer.models import MarketplaceProduct, Product, Sale
from producer.serializers import MarketplaceProductSerializer

from .locks import lock_manager, view_manager
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
    Negotiation,
    NegotiationHistory,
    Notification,
    OrderTrackingEvent,
    Payment,
    ProductChatMessage,
    ProductTag,
    Purchase,
    SellerChatMessage,
    ShoppableVideo,
    ShoppableVideoCategory,
    ShoppableVideoItem,
    UserFollow,
    UserProductImage,
    VideoComment,
    VideoLike,
    VideoReport,
    VideoSave,
)


class PurchaseSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    quantity = serializers.IntegerField()
    payment_url = serializers.URLField(read_only=True)
    khalti_payment_url = serializers.URLField(read_only=True)
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHOD_CHOICES, write_only=True)

    class Meta:
        model = Purchase
        fields = [
            "buyer",
            "product_id",
            "quantity",
            "purchase_price",
            "purchase_date",
            "payment_url",
            "khalti_payment_url",
            "payment_method",
        ]
        read_only_fields = ["purchase_price", "purchase_date", "buyer", "payment_url", "khalti_payment_url"]

    def validate(self, data):
        try:
            product = MarketplaceProduct.objects.get(id=data["product_id"])
        except MarketplaceProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found.")

        if not product.is_available:
            raise serializers.ValidationError("Product is not available for purchase.")
        if product.product.stock < data["quantity"]:
            raise serializers.ValidationError("Insufficient stock for the requested quantity.")

        if product.bid_end_date and product.bid_end_date > timezone.now():
            raise serializers.ValidationError("The bidding time is not over yet. Purchase is not allowed.")

        data["product"] = product
        return data

    def create(self, validated_data):
        product = validated_data["product"]
        quantity = validated_data["quantity"]
        payment_method = validated_data["payment_method"]
        buyer = self.context["request"].user

        # Get the highest bid
        bid = Bid.objects.filter(product__id=product.id).order_by("-max_bid_amount").first()
        if not bid or bid.bidder != buyer:
            raise serializers.ValidationError("Only the highest bidder can purchase this product.")

        # Calculate the total price
        total_price = bid.max_bid_amount * quantity

        # Create the Purchase object
        purchase = Purchase.objects.create(buyer=buyer, product=product, quantity=quantity, purchase_price=total_price)

        # Update product stock
        product.product.stock -= quantity
        if product.product.stock == 0:
            product.is_available = False
        product.product.save()

        # Generate a unique transaction ID for the payment
        transaction_id = "TXN" + str(int(time.time()))

        # Create the Payment object
        Payment.objects.create(
            purchase=purchase,
            transaction_id=transaction_id,
            amount=total_price,
            status="pending",
            payment_method=payment_method,  # Set the selected payment method
        )

        # Prepare the payment URLs based on the payment method
        if payment_method == "esewa":
            esewa_payment_url = "https://uat.esewa.com.np/epay/main"
            success_url = self.context["request"].build_absolute_uri("/payment/verify/")
            failure_url = self.context["request"].build_absolute_uri("/payment/failure/")

            esewa_payload = {
                "amt": total_price,
                "txAmt": 0,
                "psc": 0,
                "pdc": 0,
                "tAmt": total_price,
                "pid": transaction_id,
                "scd": "EPAYTEST",  # eSewa Merchant ID for sandbox
                "su": success_url,
                "fu": failure_url,
            }

            payment_url = f"{esewa_payment_url}?{urlencode(esewa_payload)}"
            return {"purchase": purchase, "payment_url": payment_url}

        elif payment_method == "khalti":
            khalti_payment_url = "https://a.khalti.com/api/v2/epayment/initiate/"
            khalti_payload = {
                "return_url": "http://localhost:8000/payment/verify/",
                "website_url": "http://localhost:8000/",
                "amount": int(total_price * 100),  # Khalti expects the amount in paisa
                "purchase_order_id": str(purchase.id),
                "purchase_order_name": purchase.product.product.name,
                "customer_info": {
                    "name": "Ram Bahadur",  # You can replace this with dynamic values if necessary
                    "email": "test@khalti.com",
                    "phone": "9800000001",  # Use test mobile number for Khalti
                },
            }

            # Headers for the request
            headers = {
                "Authorization": "key b885cd9d8dc04eebb59e6f12190ae017",
                "Content-Type": "application/json",
            }
            response = requests.post(khalti_payment_url, headers=headers, data=json.dumps(khalti_payload))
            if response.status_code == 200:
                # Extracting the payment URL from the response
                response_data = response.json()
                khalti_payment_url = response_data.get("payment_url")
            else:
                # Handle error (optional)
                print(f"Error occurred: {response.status_code}, {response.text}")

            # Return payment URL and purchase info
            return {"purchase": purchase, "khalti_payment_url": khalti_payment_url}


class BidSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    bid_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    max_bid_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    product_details = MarketplaceProductSerializer(source="product", read_only=True)

    class Meta:
        model = Bid
        fields = ["id", "bidder", "product_id", "bid_amount", "bid_date", "max_bid_amount", "product_details"]
        read_only_fields = ["bid_date", "bidder"]

    def validate(self, data):
        try:
            product = MarketplaceProduct.objects.get(id=data["product_id"])
        except MarketplaceProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found.")
        if data["bid_amount"] <= product.listed_price:
            raise serializers.ValidationError("Bid amount must be higher than the listed price.")
        highest_bid = Bid.objects.filter(product=product).order_by("-bid_amount").first()
        if highest_bid and data["bid_amount"] <= highest_bid.bid_amount:
            raise serializers.ValidationError("Your bid must be higher than the current highest bid.")
        if product.product.user == self.context["request"].user:
            raise serializers.ValidationError("Product Owner can't bid in their product")
        data["product"] = product
        return data

    def create(self, validated_data):
        product = validated_data["product"]
        bid_amount = validated_data["bid_amount"]
        bidder = self.context["request"].user
        validated_data["bid_date"] = timezone.now()
        highest_bid = Bid.objects.filter(product=product).order_by("-bid_amount").first()
        if highest_bid is None or bid_amount > highest_bid.max_bid_amount:
            max_bid_amount = bid_amount
        else:
            max_bid_amount = highest_bid.max_bid_amount
        bid_end_date = product.bid_end_date
        if bid_end_date.tzinfo is None:
            bid_end_date = timezone.make_aware(bid_end_date, timezone.get_current_timezone())
        if validated_data["bid_date"] > bid_end_date:
            raise serializers.ValidationError({"bid_date": "Can't bid for this product, Time Expired!!!!!"})
        bid = Bid.objects.create(bidder=bidder, product=product, bid_amount=bid_amount, max_bid_amount=max_bid_amount)

        # Check if the request user is the highest bidder, and send a notification if so
        if highest_bid is None or bid.bid_amount > highest_bid.bid_amount:
            Notification.objects.create(
                user=bid.bidder, message=f"You are the highest bidder for the product '{product.product.name}'"
            )

        return bid

    def delete(self, instance):
        if instance.product.bid_end_date < timezone.now():
            raise serializers.ValidationError("Cannot withdraw bid after bidding has ended.")
        # TODO: Check on this
        # if instance == Bid.objects.filter(product=instance.product).order_by('-bid_amount').first():
        #     raise serializers.ValidationError("Cannot withdraw the highest bid.")
        instance.delete()


class BidUserSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    bid_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    max_bid_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    product_details = MarketplaceProductSerializer(source="product", read_only=True)
    bidder_username = serializers.CharField(source="bidder.username", read_only=True)

    class Meta:
        model = Bid
        fields = [
            "id",
            "bidder",
            "product_id",
            "bid_amount",
            "bid_date",
            "max_bid_amount",
            "product",
            "product_details",
            "bidder_username",
        ]
        read_only_fields = ["bid_date", "bidder"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class ChatMessageSerializer(serializers.ModelSerializer):
    # product_id = serializers.IntegerField(write_only=True)
    message = serializers.CharField()
    sender_details = UserSerializer(source="sender", read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["sender", "product", "message", "timestamp", "sender_details"]
        read_only_fields = ["sender", "timestamp"]

    def create(self, validated_data):
        validated_data["sender"] = self.context["request"].user
        chat_message = super().create(validated_data)

        product = validated_data["product"]
        sender = validated_data["sender"]
        product_user = product.product.user
        if product_user != sender:
            notify_event(
                user=product_user,
                notif_type="alert",
                message=f"New chat message from {sender.username} about your product '{product.product.name}': {chat_message.message}",
                via_in_app=True,
            )
        return chat_message


class ProductChatMessageSerializer(serializers.ModelSerializer):
    sender_details = UserSerializer(source="sender", read_only=True)

    class Meta:
        model = ProductChatMessage
        fields = ["id", "sender", "sender_details", "product", "message", "timestamp"]
        read_only_fields = ["sender", "timestamp"]

    def create(self, validated_data):
        validated_data["sender"] = self.context["request"].user
        # import here to avoid circular import during module load
        from market.models import ProductChatMessage

        chat = ProductChatMessage.objects.create(**validated_data)

        # Notify product owner if not the sender
        try:
            product = validated_data["product"]
            product_owner = product.user
            if product_owner != chat.sender:
                notify_event(
                    user=product_owner,
                    notif_type="alert",
                    message=f"New message from {chat.sender.username} about your product '{product.name}': {chat.message}",
                    via_in_app=True,
                )
        except Exception:
            pass

        return chat


class SellerChatMessageSerializer(serializers.ModelSerializer):
    sender_details = UserSerializer(source="sender", read_only=True)
    target_user_details = UserSerializer(source="target_user", read_only=True)

    class Meta:
        model = SellerChatMessage
        fields = ["id", "sender", "sender_details", "target_user", "target_user_details", "subject", "message", "timestamp"]
        read_only_fields = ["sender", "timestamp"]

    def create(self, validated_data):
        validated_data["sender"] = self.context["request"].user
        chat = super().create(validated_data)

        # Notify the seller about the new message
        try:
            from market.utils import notify_event

            notify_event(
                user=chat.target_user,
                notif_type="alert",
                message=f"New message from {chat.sender.username}: {chat.subject or chat.message[:80]}",
                via_in_app=True,
            )
        except Exception:
            pass

        return chat


class UserProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProductImage
        fields = ["id", "image", "alt_text", "order"]
        read_only_fields = ["id"]


class MarketplaceUserProductSerializer(serializers.ModelSerializer):
    images = UserProductImageSerializer(many=True, required=False)

    class Meta:
        model = MarketplaceUserProduct
        fields = [
            "id",
            "name",
            "description",
            "price",
            "stock",
            "is_sold",
            "category",
            "unit",
            "is_verified",
            "created_at",
            "updated_at",
            "user",
            "location",
            "images",
        ]
        extra_kwargs = {"user": {"read_only": True}}

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock cannot be negative.")
        return value

    def create(self, validated_data):

        images_data = self.context.get("request").FILES.getlist("images")
        validated_data.pop("images", None)
        validated_data["user"] = self.context["request"].user

        with transaction.atomic():
            product = super().create(validated_data)

            for image_data in images_data:
                UserProductImage.objects.create(product=product, image=image_data, alt_text=image_data.name, order=0)

        return product

    def update(self, instance, validated_data):
        images_data = self.context.get("request").FILES.getlist("images")

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if images_data:
                instance.images.all().delete()

                for idx, image_data in enumerate(images_data):
                    UserProductImage.objects.create(product=instance, image=image_data, alt_text=image_data.name, order=idx)

        return instance


class SellerProductSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="product.name", read_only=True)
    description = serializers.CharField(source="product.description", read_only=True)

    class Meta:
        model = MarketplaceProduct
        fields = ["id", "name", "description"]


class SellerBidSerializer(serializers.ModelSerializer):
    bidder_username = serializers.CharField(source="bidder.username", read_only=True)

    class Meta:
        model = Bid
        fields = ["bidder_username", "bid_amount"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "message", "is_read", "created_at"]


class FeedbackSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)
    product_name = serializers.CharField(source="product.product.name", read_only=True)

    class Meta:
        model = Feedback
        fields = ["id", "user", "user_username", "product", "product_name", "rating", "comment", "created_at"]
        read_only_fields = ["user", "created_at"]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class CartItemSerializer(serializers.ModelSerializer):
    product_details = MarketplaceProductSerializer(source="product", read_only=True)
    unit_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "cart", "product", "quantity", "product_details", "unit_price", "total_price"]

    def get_unit_price(self, obj):
        return obj.product.listed_price

    def get_total_price(self, obj):
        return obj.product.listed_price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    shipping = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "user", "items", "subtotal", "shipping", "total", "created_at"]

    def get_subtotal(self, obj):
        return sum(item.product.listed_price * item.quantity for item in obj.items.all())

    def get_shipping(self, obj):
        return 100.0

    def get_total(self, obj):
        return self.get_subtotal(obj) + self.get_shipping(obj)


class MarketplaceSaleSerializer(serializers.ModelSerializer):
    """Serializer for the MarketplaceSale model."""

    buyer_username = serializers.CharField(source="buyer.username", read_only=True)
    seller_username = serializers.CharField(source="seller.username", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    formatted_subtotal = serializers.CharField(read_only=True)
    formatted_tax = serializers.CharField(read_only=True)
    formatted_shipping = serializers.CharField(read_only=True)
    formatted_total = serializers.CharField(read_only=True)
    buyer_display_name = serializers.CharField(read_only=True)
    buyer_contact_email = serializers.EmailField(read_only=True)

    class Meta:
        model = MarketplaceSale
        fields = [
            "id",
            "order_number",
            "sale_date",
            "updated_at",
            "currency",
            "buyer",
            "buyer_username",
            "buyer_name",
            "buyer_email",
            "buyer_phone",
            "seller",
            "seller_username",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "unit_price_at_purchase",
            "subtotal",
            "tax_amount",
            "shipping_cost",
            "total_amount",
            "status",
            "payment_status",
            "payment_method",
            "transaction_id",
            "notes",
            "formatted_subtotal",
            "formatted_tax",
            "formatted_shipping",
            "formatted_total",
            "buyer_display_name",
            "buyer_contact_email",
            "is_deleted",
            "deleted_at",
        ]
        read_only_fields = [
            "id",
            "order_number",
            "sale_date",
            "updated_at",
            "subtotal",
            "total_amount",
            "formatted_subtotal",
            "formatted_tax",
            "formatted_shipping",
            "formatted_total",
            "buyer_display_name",
            "buyer_contact_email",
            "buyer_username",
            "seller_username",
            "product_name",
            "is_deleted",
            "deleted_at",
        ]

    def validate(self, data):
        """Validate the sale data."""
        product = data.get("product")
        if product and not product.is_available:
            raise serializers.ValidationError({"product": "This product is not available for sale."})

        quantity = data.get("quantity", 0)
        if product and quantity > product.stock:
            raise serializers.ValidationError({"quantity": "Insufficient stock for this product."})

        if self.instance and "payment_status" in data:
            old_status = self.instance.payment_status
            new_status = data["payment_status"]

            if old_status == "paid" and new_status != "refunded":
                raise serializers.ValidationError(
                    {"payment_status": "Paid orders can only be refunded or partially refunded."}
                )

        return data

    def create(self, validated_data):
        """Create a new sale with proper validation."""
        if "buyer" not in validated_data and "request" in self.context:
            validated_data["buyer"] = self.context["request"].user

        if "subtotal" not in validated_data:
            validated_data["subtotal"] = validated_data.get("unit_price", 0) * validated_data.get("quantity", 0)

        if "total_amount" not in validated_data:
            validated_data["total_amount"] = (
                validated_data.get("subtotal", 0)
                + validated_data.get("tax_amount", 0)
                + validated_data.get("shipping_cost", 0)
            )

        sale = super().create(validated_data)

        product = sale.product
        product.stock -= sale.quantity
        if product.stock == 0:
            product.is_available = False
        product.save()

        return sale

    def update(self, instance, validated_data):
        """Update an existing sale with proper validation."""
        if "status" in validated_data:
            old_status = instance.status
            new_status = validated_data["status"]

            if new_status not in instance.SaleStatus.get_next_allowed_statuses(old_status):
                raise serializers.ValidationError({"status": f"Cannot change status from {old_status} to {new_status}."})

            if new_status == "delivered" and instance.payment_status != "paid":
                raise serializers.ValidationError({"status": "Cannot mark as delivered with unpaid order."})

        return super().update(instance, validated_data)


class DeliverySerializer(serializers.ModelSerializer):
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all(), required=False, allow_null=True)
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all(), required=False, allow_null=True)
    marketplace_sale = serializers.PrimaryKeyRelatedField(
        queryset=MarketplaceSale.objects.all(), required=False, allow_null=True
    )
    marketplace_order = serializers.PrimaryKeyRelatedField(
        queryset=MarketplaceOrder.objects.all(), required=False, allow_null=True
    )

    # Read-only computed fields
    delivery_source = serializers.ReadOnlyField()
    total_items = serializers.ReadOnlyField()
    total_value = serializers.ReadOnlyField()
    product_details = serializers.ReadOnlyField()

    class Meta:
        model = Delivery
        fields = [
            "id",
            "cart",
            "sale",
            "marketplace_sale",
            "marketplace_order",
            "customer_name",
            "phone_number",
            "email",
            "address",
            "city",
            "state",
            "zip_code",
            "latitude",
            "longitude",
            "additional_instructions",
            "shop_id",
            "delivery_status",
            "delivery_person_name",
            "delivery_person_phone",
            "delivery_service",
            "tracking_number",
            "estimated_delivery_date",
            "actual_delivery_date",
            "created_at",
            "updated_at",
            # Computed fields
            "delivery_source",
            "total_items",
            "total_value",
            "product_details",
        ]
        read_only_fields = [
            "id",
            "shop_id",  # Automatically set from user profile
            "created_at",
            "updated_at",
            "delivery_source",
            "total_items",
            "total_value",
            "product_details",
        ]

    # def get_shop_id_from_user(self, user):
    #     """
    #     Get shop_id from user profile.
    #     """
    #     try:
    #         if hasattr(user, 'user_profile') and user.user_profile:
    #             return getattr(user.user_profile, 'shop_id', None)
    #     except AttributeError:
    #         pass
    #     return None

    # def create(self, validated_data):
    #     """
    #     Create a delivery and automatically set shop_id from user profile.
    #     """
    #     request = self.context.get('request')
    #     if request and request.user:
    #         validated_data['shop_id'] = self.get_shop_id_from_user(request.user)

    #     return super().create(validated_data)

    # def update(self, instance, validated_data):
    #     """
    #     Update a delivery and automatically set shop_id from user profile if not already set.
    #     """
    #     request = self.context.get('request')
    #     if request and request.user and not instance.shop_id:
    #         validated_data['shop_id'] = self.get_shop_id_from_user(request.user)

    #     return super().update(instance, validated_data)

    def validate(self, data):
        """
        Validate that at least one source (cart, sale, marketplace_sale, marketplace_order) is provided.
        """
        cart = data.get("cart")
        sale = data.get("sale")
        marketplace_sale = data.get("marketplace_sale")
        marketplace_order = data.get("marketplace_order")

        if not any([cart, sale, marketplace_sale, marketplace_order]):
            raise serializers.ValidationError(
                "At least one of cart, sale, marketplace_sale, or marketplace_order must be provided."
            )

        return data


class CreateDeliveryFromSaleSerializer(serializers.Serializer):
    """
    Simplified serializer for creating deliveries from sales.
    """

    sale_id = serializers.IntegerField()
    customer_name = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    address = serializers.CharField(style={"base_template": "textarea.html"})
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    zip_code = serializers.CharField(max_length=20)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    additional_instructions = serializers.CharField(
        required=False, allow_blank=True, style={"base_template": "textarea.html"}
    )

    def validate_sale_id(self, value):
        """
        Validate that the sale exists and belongs to the current user.
        """
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Authentication required.")

        try:
            sale = Sale.objects.get(id=value, user=request.user)
            return value
        except Sale.DoesNotExist:
            raise serializers.ValidationError("Sale not found or you do not have permission to access it.")

    def create(self, validated_data):
        """
        Create a delivery from the sale with automatic shop_id handling.
        """
        sale_id = validated_data.pop("sale_id")
        sale = Sale.objects.get(id=sale_id, user=self.context["request"].user)

        # The create_delivery method on Sale will automatically handle shop_id
        delivery = sale.create_delivery(**validated_data)
        return delivery


class OrderTrackingEventSerializer(serializers.ModelSerializer):
    """Updated serializer for order tracking events supporting both order types."""

    order_number = serializers.ReadOnlyField()

    class Meta:
        model = OrderTrackingEvent
        fields = [
            "id",
            "marketplace_sale",
            "marketplace_order",
            "order_number",
            "status",
            "message",
            "location",
            "latitude",
            "longitude",
            "metadata",
            "created_at",
        ]
        read_only_fields = ["id", "order_number", "created_at"]


# New serializers for marketplace orders
class DeliveryInfoSerializer(serializers.ModelSerializer):
    """Serializer for delivery information."""

    full_address = serializers.ReadOnlyField()

    class Meta:
        model = DeliveryInfo
        fields = [
            "id",
            "customer_name",
            "phone_number",
            "address",
            "city",
            "state",
            "zip_code",
            "latitude",
            "longitude",
            "delivery_instructions",
            "full_address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "full_address"]


class CouponSerializer(serializers.ModelSerializer):
    """Serializer for Coupon model."""

    class Meta:
        from .models import Coupon

        model = Coupon
        fields = [
            "id",
            "code",
            "description",
            "discount_type",
            "discount_value",
            "min_purchase_amount",
            "max_discount_amount",
            "start_date",
            "end_date",
            "is_active",
            "usage_limit",
            "user_limit",
            "used_count",
        ]
        read_only_fields = ["used_count"]


class MarketplaceOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for marketplace order items."""

    product = MarketplaceProductSerializer(read_only=True)
    product_details = serializers.SerializerMethodField()
    formatted_unit_price = serializers.ReadOnlyField()
    formatted_total_price = serializers.ReadOnlyField()

    class Meta:
        model = MarketplaceOrderItem
        fields = [
            "id",
            "product",
            "product_details",
            "quantity",
            "unit_price",
            "total_price",
            "formatted_unit_price",
            "formatted_total_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "total_price", "created_at", "updated_at"]

    def get_product_details(self, obj):
        """Get detailed product information for the frontend."""
        if obj.product and obj.product.product:
            product = obj.product.product
            try:
                return {
                    "id": product.id,
                    "name": getattr(product, "name", "Unknown Product"),
                    "description": getattr(product, "description", ""),
                    "sku": getattr(product, "sku", ""),
                    "category": product.category.name if hasattr(product, "category") and product.category else None,
                    "category_details": product.category.name if hasattr(product, "category") and product.category else None,
                    "images": (
                        [
                            {
                                "id": img.id,
                                "image": img.image.url if img.image else None,
                                "alt_text": img.alt_text,
                            }
                            for img in product.images.all()
                        ]
                        if hasattr(product, "images")
                        else []
                    ),
                    "price": float(product.price) if hasattr(product, "price") else 0,
                    "cost_price": float(product.cost_price) if hasattr(product, "cost_price") else 0,
                    "stock": product.stock if hasattr(product, "stock") else 0,
                }
            except AttributeError as e:
                # Fallback if product data is corrupted
                return {
                    "id": getattr(product, "id", None),
                    "name": str(product),
                    "description": f"Error accessing product data: {e}",
                    "sku": "",
                    "category": None,
                    "category_details": None,
                    "images": [],
                    "price": 0,
                    "cost_price": 0,
                    "stock": 0,
                }
        return None


class MarketplaceOrderSerializer(serializers.ModelSerializer):
    """Serializer for marketplace orders."""

    items = MarketplaceOrderItemSerializer(many=True, read_only=True)
    delivery = DeliveryInfoSerializer(read_only=True)
    order_status_display = serializers.ReadOnlyField()
    payment_status_display = serializers.ReadOnlyField()
    formatted_total = serializers.ReadOnlyField()
    can_cancel = serializers.ReadOnlyField()
    can_refund = serializers.ReadOnlyField()
    is_paid = serializers.ReadOnlyField()
    is_delivered = serializers.ReadOnlyField()
    coupon_code = serializers.CharField(source="coupon.code", read_only=True)

    class Meta:
        model = MarketplaceOrder
        fields = [
            "id",
            "order_number",
            "customer",
            "order_status",
            "order_status_display",
            "payment_status",
            "payment_status_display",
            "total_amount",
            "discount_amount",
            "coupon_code",
            "formatted_total",
            "currency",
            "payment_method",
            "transaction_id",
            "delivery",
            "items",
            "created_at",
            "updated_at",
            "delivered_at",
            "estimated_delivery_date",
            "tracking_number",
            "notes",
            "can_cancel",
            "can_refund",
            "is_paid",
            "is_delivered",
        ]
        read_only_fields = [
            "id",
            "order_number",
            "created_at",
            "updated_at",
            "delivered_at",
            "order_status_display",
            "payment_status_display",
            "formatted_total",
            "discount_amount",
            "coupon_code",
            "can_cancel",
            "can_refund",
            "is_paid",
            "is_delivered",
        ]


class CreateOrderSerializer(serializers.Serializer):
    """Serializer for creating orders from cart."""

    cart_id = serializers.IntegerField()
    delivery_info = DeliveryInfoSerializer()
    payment_method = serializers.CharField(max_length=50, required=False)
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate_cart_id(self, value):
        """Validate that the cart exists and belongs to the user."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        try:
            cart = Cart.objects.get(id=value, user=request.user)
            if not cart.items.exists():
                raise serializers.ValidationError("Cart is empty")
            return value
        except Cart.DoesNotExist:
            raise serializers.ValidationError("Cart not found")

    def validate_coupon_code(self, value):
        """Validate coupon code if provided."""
        if not value:
            return value

        from .models import Coupon

        try:
            coupon = Coupon.objects.get(code=value)
            # Basic existence check here, full validation happens in create_order_from_cart
            return value
        except Coupon.DoesNotExist:
            raise serializers.ValidationError("Invalid coupon code")

    def create(self, validated_data):
        """Create order from cart."""
        request = self.context.get("request")
        cart_id = validated_data["cart_id"]
        delivery_data = validated_data["delivery_info"]
        payment_method = validated_data.get("payment_method")
        coupon_code = validated_data.get("coupon_code")

        # Get the cart
        cart = Cart.objects.get(id=cart_id, user=request.user)

        # Create delivery info
        from .models import Coupon, DeliveryInfo, MarketplaceOrder

        delivery_info = DeliveryInfo.objects.create(**delivery_data)

        # Get Coupon if code provided
        coupon = None
        if coupon_code:
            coupon = Coupon.objects.filter(code=coupon_code).first()

        # Auto-detect first order for this customer and create order
        try:
            is_first_order = not MarketplaceOrder.objects.filter(customer=cart.user, is_deleted=False).exists()
        except Exception:
            is_first_order = False

        order = MarketplaceOrder.objects.create_order_from_cart(
            cart=cart,
            delivery_info=delivery_info,
            payment_method=payment_method,
            is_first_order=is_first_order,
            coupon=coupon,
        )

        # Clear the cart after successful order creation
        cart.items.all().delete()

        return order


class VoiceSearchInputSerializer(serializers.Serializer):
    audio_file = serializers.FileField(required=False)
    query = serializers.CharField(required=False, max_length=255)
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)

    def validate(self, data):
        if not data.get("audio_file") and not data.get("query"):
            raise serializers.ValidationError("Either 'audio_file' or 'query' must be provided.")
        return data


class ShoppableVideoCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppableVideoCategory
        fields = ["id", "name", "icon", "is_active", "order"]


class ShoppableVideoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppableVideoItem
        fields = ["id", "file", "thumbnail", "order", "created_at"]


class ShoppableVideoSerializer(serializers.ModelSerializer):
    uploader_name = serializers.CharField(source="uploader.username", read_only=True)
    uploader_profile = serializers.SerializerMethodField()
    uploader_profile_url = serializers.SerializerMethodField()
    creator_profile = serializers.SerializerMethodField()
    creator_profile_id = serializers.IntegerField(write_only=True, required=False)
    category_details = ShoppableVideoCategorySerializer(source="category", read_only=True)
    items = ShoppableVideoItemSerializer(many=True, read_only=True)
    product = MarketplaceProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=MarketplaceProduct.objects.all(), source="product", write_only=True
    )
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    product_tags = serializers.SerializerMethodField()

    class Meta:
        model = ShoppableVideo
        fields = [
            "id",
            "uploader",
            "uploader_profile",
            "creator_profile",
            "creator_profile_id",
            "uploader_profile_url",
            "uploader_name",
            "content_type",
            "video_file",
            "image_file",
            "thumbnail",
            "items",
            "category",
            "category_details",
            "title",
            "description",
            "product",
            "product_id",
            "tags",
            "product_tags",
            "trend_score",
            "views_count",
            "likes_count",
            "shares_count",
            "created_at",
            "is_liked",
            "is_saved",
        ]
        read_only_fields = ["uploader", "views_count", "likes_count", "shares_count", "created_at", "trend_score"]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        liked_ids = self.context.get("liked_ids")
        if liked_ids is not None:
            return obj.id in liked_ids
        if request and request.user.is_authenticated:
            return VideoLike.objects.filter(user=request.user, video=obj).exists()
        return False

    def get_uploader_profile(self, obj):
        try:
            from producer.serializers import CreatorProfileSerializer

            if hasattr(obj.uploader, "creator_profile"):
                return CreatorProfileSerializer(obj.uploader.creator_profile, context=self.context).data
        except Exception:
            return None
        return None

    def get_uploader_profile_url(self, obj):
        request = self.context.get("request")
        try:
            if not request:
                return None
            if hasattr(obj.uploader, "creator_profile"):
                from django.urls import reverse

                cp = obj.uploader.creator_profile
                # router basename in main urls: 'creators'
                url = reverse("creators-detail", args=[cp.id])
                return request.build_absolute_uri(url)
        except Exception:
            return None
        return None

    def get_creator_profile(self, obj):
        try:
            if hasattr(obj, "creator_profile") and obj.creator_profile is not None:
                from producer.serializers import CreatorProfileSerializer

                return CreatorProfileSerializer(obj.creator_profile, context=self.context).data
        except Exception:
            return None
        return None

    def get_is_saved(self, obj):
        request = self.context.get("request")
        saved_ids = self.context.get("saved_ids")
        if saved_ids is not None:
            return obj.id in saved_ids
        if request and request.user.is_authenticated:
            return VideoSave.objects.filter(user=request.user, video=obj).exists()
        return False

    def create(self, validated_data):
        # If request user is authenticated, set uploader; otherwise allow creator_profile via payload
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            validated_data["uploader"] = request.user
        # If uploader has a creator_profile, set it on the video for faster reads
        try:
            cp = getattr(request.user, "creator_profile", None) if request and getattr(request, "user", None) else None
            if cp:
                validated_data["creator_profile"] = cp
            else:
                # Accept creator_profile_id from payload for unauthenticated/alternate flows
                cp_id = validated_data.pop("creator_profile_id", None)
                if cp_id:
                    from producer.models import CreatorProfile

                    try:
                        validated_data["creator_profile"] = CreatorProfile.objects.get(pk=cp_id)
                    except CreatorProfile.DoesNotExist:
                        pass
        except Exception:
            pass
        return super().create(validated_data)

    def get_product_tags(self, obj):
        # Provide structured product tags for the content (if any)
        tags = getattr(obj, "product_tags", None)
        if tags is None:
            return []
        return ProductTagSerializer(tags.all(), many=True).data


class VideoLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoLike
        fields = ["id", "user", "video", "created_at"]
        read_only_fields = ["user", "created_at"]


class VideoCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = VideoComment
        fields = ["id", "user", "user_name", "video", "text", "created_at", "parent", "replies"]
        read_only_fields = ["user", "created_at", "replies"]

    def get_replies(self, obj):
        if obj.replies.exists():
            return VideoCommentSerializer(obj.replies.all(), many=True).data
        return []

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class VideoReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoReport
        fields = ["id", "reporter", "video", "reason", "description", "status", "created_at"]
        read_only_fields = ["reporter", "status", "created_at"]

    def create(self, validated_data):
        validated_data["reporter"] = self.context["request"].user
        return super().create(validated_data)


class ProductTagSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(read_only=True)
    product_detail = serializers.SerializerMethodField()

    class Meta:
        model = ProductTag
        fields = [
            "id",
            "product",
            "product_detail",
            "x",
            "y",
            "width",
            "height",
            "timecode",
            "label",
            "merchant_url",
            "affiliate_meta",
            "created_at",
        ]

    def get_product_detail(self, obj):
        try:
            from producer.serializers import MarketplaceProductSerializer

            return MarketplaceProductSerializer(obj.product).data
        except Exception:
            return None


class UserFollowSerializer(serializers.ModelSerializer):
    follower_name = serializers.CharField(source="follower.username", read_only=True)
    following_name = serializers.CharField(source="following.username", read_only=True)

    class Meta:
        model = UserFollow
        fields = ["id", "follower", "follower_name", "following", "following_name", "created_at"]
        read_only_fields = ["follower", "created_at"]

    def create(self, validated_data):
        validated_data["follower"] = self.context["request"].user
        return super().create(validated_data)


class NegotiationHistorySerializer(serializers.ModelSerializer):
    """Serializer for negotiation history with price masking"""

    offer_by_username = serializers.CharField(source="offer_by.username", read_only=True)

    # Price field that will be masked based on permissions
    masked_price = serializers.SerializerMethodField()

    class Meta:
        model = NegotiationHistory
        fields = ["id", "offer_by", "offer_by_username", "price", "masked_price", "quantity", "message", "timestamp"]
        read_only_fields = ["id", "offer_by", "timestamp", "price"]

    def get_masked_price(self, obj):
        """Get masked price based on user's view permissions"""
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            try:
                # Get the negotiation object
                negotiation = obj.negotiation

                # Check if user can view price
                can_view, viewable_price = view_manager.can_view_price(negotiation.id, request.user.id)

                if can_view:
                    # User can view price - return actual price
                    return obj.price
                else:
                    # User cannot view price - mask it
                    # Determine mask type based on negotiation status
                    if negotiation.status in [Negotiation.Status.PENDING, Negotiation.Status.LOCKED]:
                        # Initial offers show to both parties
                        if obj.id == negotiation.history.first().id:
                            return obj.price
                    # Mask subsequent counter offers
                    return "****"

            except Exception as e:
                raise e

        # Default: mask the price
        return "****"

    def to_representation(self, instance):
        """Override representation to use masked price"""
        data = super().to_representation(instance)

        # Replace price with masked_price for display
        data["price"] = data.pop("masked_price")

        return data


class NegotiationSerializer(serializers.ModelSerializer):
    """Serializer for negotiations with locking and price masking"""

    history = NegotiationHistorySerializer(many=True, read_only=True)
    product_name = serializers.CharField(source="product.product.name", read_only=True)
    buyer_username = serializers.CharField(source="buyer.username", read_only=True)
    seller_username = serializers.CharField(source="seller.username", read_only=True)
    last_offer_by_username = serializers.CharField(source="last_offer_by.username", read_only=True)
    message = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Lock-related fields
    is_locked = serializers.BooleanField(read_only=True)
    lock_owner_username = serializers.CharField(source="lock_owner.username", read_only=True, allow_null=True)
    lock_expires_in = serializers.SerializerMethodField(read_only=True)
    can_user_negotiate = serializers.SerializerMethodField(read_only=True)

    # Price field that will be masked based on permissions
    masked_price = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Negotiation
        fields = [
            "id",
            "buyer",
            "buyer_username",
            "seller",
            "seller_username",
            "product",
            "product_name",
            "proposed_price",  # Original price field (for internal use)
            "masked_price",  # Masked price field (for display)
            "proposed_quantity",
            "status",
            "last_offer_by",
            "last_offer_by_username",
            "lock_owner",
            "lock_owner_username",
            "is_locked",
            "lock_expires_in",
            "can_user_negotiate",
            "created_at",
            "updated_at",
            "history",
            "message",
        ]
        read_only_fields = [
            "id",
            "buyer",
            "seller",
            "last_offer_by",
            "status",
            "lock_owner",
            "created_at",
            "updated_at",
            "history",
            "is_locked",
        ]
        extra_kwargs = {"proposed_price": {"write_only": True}}  # Hide original price in responses

    def get_masked_price(self, obj):
        """Get the price that the current user can view"""
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            try:
                # Check if user can view price
                can_view, viewable_price = view_manager.can_view_price(obj.id, request.user.id)

                if can_view:
                    return viewable_price
                else:
                    # Check if user is part of this negotiation
                    if request.user.id in [obj.buyer_id, obj.seller_id]:
                        # User is part of negotiation but can't view price
                        # This means it's not their turn to see the current offer
                        return "****"

            except Exception as e:
                raise e
        # Default: mask the price
        return "****"

    def get_lock_expires_in(self, obj):
        """Calculate remaining lock time in seconds"""
        if obj.lock_expires_at and obj.is_locked:
            remaining = (obj.lock_expires_at - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return None

    def get_can_user_negotiate(self, obj):
        """Check if current user can negotiate (has lock or can acquire)"""
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            # Check if user is part of this negotiation
            user_id = request.user.id
            if user_id not in [obj.buyer_id, obj.seller_id]:
                return False

            # Check if negotiation is locked
            if obj.is_locked:
                # Check if user owns the lock
                is_owner, _ = lock_manager.check_lock_ownership(obj.id, user_id)
                return is_owner
            else:
                # Not locked - check if it's user's turn
                # Logic: The user who didn't make the last offer can negotiate
                return user_id != obj.last_offer_by_id

        return False

    def to_representation(self, instance):
        """Custom representation to handle price masking and lock status"""
        data = super().to_representation(instance)

        # Remove the original price field from response
        # It's already write-only, but ensure it's not in the response
        data.pop("proposed_price", None)

        # Add lock status message if applicable
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            user_id = request.user.id

            # Add lock status information
            if instance.is_locked:
                is_owner, lock_data = lock_manager.check_lock_ownership(instance.id, user_id)

                if is_owner:
                    data["lock_status"] = "You currently hold the lock"
                    data["lock_expires_at"] = instance.lock_expires_at.isoformat() if instance.lock_expires_at else None
                else:
                    lock_owner_name = lock_data.get("user_display_name") if lock_data else "Another user"
                    data["lock_status"] = f"Currently locked by {lock_owner_name}"
                    data["lock_expires_at"] = None
            else:
                data["lock_status"] = "Available for negotiation"

        return data

    def validate(self, data):
        """Enhanced validation with lock checking"""
        request = self.context["request"]
        user = request.user
        product = data.get("product")
        proposed_price = data.get("proposed_price")
        proposed_quantity = data.get("proposed_quantity")

        # For updates (counter offers), check lock status
        if self.instance:
            negotiation = self.instance

            # Check if negotiation is locked
            if negotiation.is_locked:
                # Verify user owns the lock
                is_owner, _ = lock_manager.check_lock_ownership(negotiation.id, user.id)
                if not is_owner:
                    raise serializers.ValidationError(
                        "This negotiation is currently locked by another user. "
                        "Please wait for them to finish or the lock to expire."
                    )
            else:
                # Check if it's user's turn to negotiate
                if user.id == negotiation.last_offer_by_id:
                    raise serializers.ValidationError(
                        "It's not your turn to make an offer. Please wait for the other party to respond."
                    )

        # Original validation logic (unchanged)
        # 1. Product availability
        if not product.is_available:
            raise serializers.ValidationError("This product is not currently available for negotiation.")

        if not product.enable_b2b_sales:
            raise serializers.ValidationError("This product does not support B2B price negotiation.")

        # 2. User verification
        try:
            profile = user.user_profile
            if not profile.b2b_verified:
                raise serializers.ValidationError("Your account must be B2B verified to start a negotiation.")
        except Exception:
            raise serializers.ValidationError("User profile not found. Please complete your profile.")

        # 3. Price validation
        listed_price = Decimal(str(product.discounted_price or product.listed_price))
        if proposed_price > listed_price:
            raise serializers.ValidationError(f"Proposed price cannot be higher than the listed price ({listed_price}).")

        # Floor price (e.g., 50% of listed price to prevent extreme low-balling)
        floor_price = listed_price * Decimal("0.5")
        if proposed_price < floor_price:
            raise serializers.ValidationError(f"Proposed price is too low. Minimum allowed is {floor_price}.")

        # 4. Quantity validation
        if product.min_order and proposed_quantity < product.min_order:
            raise serializers.ValidationError(f"Minimum order quantity for this product is {product.min_order}.")

        if proposed_quantity > product.product.stock:
            raise serializers.ValidationError(f"Requested quantity exceeds current stock ({product.product.stock}).")

        # 5. For counter offers, ensure price is different
        if self.instance:
            if proposed_price == self.instance.proposed_price:
                raise serializers.ValidationError("New price must be different from the current price.")

        return data

    def create(self, validated_data):
        """Create a new negotiation with initial view permissions"""
        message = validated_data.pop("message", "")
        buyer = self.context["request"].user
        product = validated_data["product"]
        proposed_price = validated_data["proposed_price"]

        # Determine seller from product
        try:
            seller = product.product.producer.user
        except Exception:
            raise serializers.ValidationError("Seller information not found for this product.")

        if buyer == seller:
            raise serializers.ValidationError("You cannot negotiate with yourself.")

        # Check for existing active negotiation
        existing = Negotiation.objects.filter(
            buyer=buyer,
            product=product,
            status__in=[Negotiation.Status.PENDING, Negotiation.Status.COUNTER_OFFER],
        ).first()
        if existing:
            raise serializers.ValidationError("An active negotiation already exists for this product.")

        # Create negotiation
        negotiation = Negotiation.objects.create(
            buyer=buyer,
            seller=seller,
            product=product,
            proposed_price=proposed_price,
            proposed_quantity=validated_data["proposed_quantity"],
            last_offer_by=buyer,
            status=Negotiation.Status.PENDING,
        )

        # Create history entry
        NegotiationHistory.objects.create(
            negotiation=negotiation,
            offer_by=buyer,
            price=negotiation.proposed_price,
            quantity=negotiation.proposed_quantity,
            message=message,
        )

        # Set initial view permissions
        # Both parties can see the initial offer
        view_manager.grant_view_permission(negotiation.id, buyer.id, float(proposed_price), duration=3600)  # 1 hour
        view_manager.grant_view_permission(negotiation.id, seller.id, float(proposed_price), duration=3600)

        # Notify seller
        from market.utils import notify_event

        notify_event(
            user=seller,
            notif_type=Notification.Type.MARKETPLACE,
            message=f"New negotiation offer for {product.product.name} from {buyer.username}",
            via_in_app=True,
        )

        return negotiation

    def update(self, instance, validated_data):
        """Update negotiation for counter offers with lock management"""
        request = self.context["request"]
        user = request.user
        new_price = validated_data.get("proposed_price", instance.proposed_price)
        new_quantity = validated_data.get("proposed_quantity", instance.proposed_quantity)
        message = validated_data.get("message", "")

        # Check if user has lock
        is_locked, lock_data = lock_manager.check_lock_ownership(instance.id, user.id)

        if not is_locked:
            # Try to acquire lock
            lock_id = lock_manager.acquire_lock(instance.id, user.id, timeout=300)  # 5 minutes

            if not lock_id:
                raise serializers.ValidationError(
                    "Failed to acquire lock. Please try again or wait for the other party to finish."
                )

            lock_data = {"lock_id": lock_id}

        try:
            # Update negotiation
            old_price = instance.proposed_price
            instance.proposed_price = new_price
            instance.proposed_quantity = new_quantity
            instance.status = Negotiation.Status.COUNTER_OFFER
            instance.last_offer_by = user

            # Update lock ownership in model
            instance.lock_owner = user
            instance.lock_expires_at = timezone.now() + timezone.timedelta(seconds=300)
            instance.save()

            # Create history entry
            history = NegotiationHistory.objects.create(
                negotiation=instance,
                offer_by=user,
                price=new_price,
                quantity=new_quantity,
                message=message,
            )

            # Update view permissions
            # Only the other party can see the new price
            other_party = instance.seller if user == instance.buyer else instance.buyer
            view_manager.update_view_permission_on_counter(instance.id, user.id, float(new_price))

            # Release lock after making counter offer
            if lock_data.get("lock_id"):
                lock_manager.release_lock(instance.id, user.id, lock_data["lock_id"])

            # Reset lock fields in model
            instance.lock_owner = None
            instance.lock_expires_at = None
            instance.save(update_fields=["lock_owner", "lock_expires_at"])

            # Notify other party
            from market.utils import notify_event

            notify_event(
                user=other_party,
                notif_type=Notification.Type.MARKETPLACE,
                message=f"New counter offer for {instance.product.product.name} from {user.username}",
                via_in_app=True,
            )

            return instance

        except Exception as e:
            logger.error(f"Error updating negotiation: {e}")

            # Release lock on error
            if lock_data.get("lock_id"):
                try:
                    lock_manager.release_lock(instance.id, user.id, lock_data["lock_id"])
                except:
                    pass

            raise serializers.ValidationError(f"Error making counter offer: {str(e)}")


class NegotiationLockSerializer(serializers.Serializer):
    """Serializer for lock operations"""

    lock_id = serializers.CharField(read_only=True)
    timeout = serializers.IntegerField(
        required=False, default=300, min_value=60, max_value=1800, help_text="Lock timeout in seconds (60-1800)"
    )

    def create(self, validated_data):
        """Acquire a lock for negotiation"""
        request = self.context["request"]
        user = request.user
        negotiation = self.context["negotiation"]
        timeout = validated_data.get("timeout", 300)

        # Check if negotiation is already locked
        if negotiation.is_locked:
            # Check if user already owns the lock
            is_owner, lock_data = lock_manager.check_lock_ownership(negotiation.id, user.id)
            if is_owner:
                return {"lock_id": lock_data.get("lock_id"), "message": "You already hold the lock"}

            # Locked by someone else
            raise serializers.ValidationError(
                "Negotiation is currently locked by another user. " f"Lock expires at {negotiation.lock_expires_at}"
            )

        # Check if it's user's turn to negotiate
        if user.id == negotiation.last_offer_by_id:
            raise serializers.ValidationError("It's not your turn to negotiate. Please wait for the other party to respond.")

        # Acquire lock
        lock_id = lock_manager.acquire_lock(negotiation.id, user.id, timeout)

        if not lock_id:
            raise serializers.ValidationError("Failed to acquire lock. Please try again.")

        # Update negotiation model
        negotiation.status = Negotiation.Status.LOCKED
        negotiation.lock_owner = user
        negotiation.lock_expires_at = timezone.now() + timezone.timedelta(seconds=timeout)
        negotiation.save()

        # Grant view permission to lock holder
        view_manager.grant_view_permission(negotiation.id, user.id, float(negotiation.proposed_price), duration=timeout)

        return {
            "lock_id": lock_id,
            "expires_at": negotiation.lock_expires_at.isoformat(),
            "timeout": timeout,
            "message": "Lock acquired successfully",
        }


class NegotiationReleaseLockSerializer(serializers.Serializer):
    """Serializer for releasing locks"""

    lock_id = serializers.CharField(required=True)

    def validate(self, data):
        """Validate lock ownership"""
        request = self.context["request"]
        user = request.user
        negotiation = self.context["negotiation"]
        lock_id = data["lock_id"]

        # Verify lock ownership
        is_owner, lock_data = lock_manager.check_lock_ownership(negotiation.id, user.id)

        if not is_owner or lock_data.get("lock_id") != lock_id:
            raise serializers.ValidationError("Invalid lock ID or you don't own this lock")

        return data

    def create(self, validated_data):
        """Release the lock"""
        request = self.context["request"]
        user = request.user
        negotiation = self.context["negotiation"]
        lock_id = validated_data["lock_id"]

        # Release lock
        released = lock_manager.release_lock(negotiation.id, user.id, lock_id)

        if not released:
            raise serializers.ValidationError("Failed to release lock")

        # Update negotiation model
        if negotiation.status == Negotiation.Status.LOCKED:
            negotiation.status = Negotiation.Status.COUNTER_OFFER
        negotiation.lock_owner = None
        negotiation.lock_expires_at = None
        negotiation.save()

        return {"message": "Lock released successfully", "negotiation_status": negotiation.status}
