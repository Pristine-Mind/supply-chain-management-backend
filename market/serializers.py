import json
import time
from datetime import datetime
from urllib.parse import urlencode

import requests
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from market.utils import notify_event
from producer.models import MarketplaceProduct, Sale
from producer.serializers import MarketplaceProductSerializer

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
    Notification,
    OrderTrackingEvent,
    Payment,
    ProductTag,
    Purchase,
    ShoppableVideo,
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

    def create(self, validated_data):
        """Create order from cart."""
        request = self.context.get("request")
        cart_id = validated_data["cart_id"]
        delivery_data = validated_data["delivery_info"]
        payment_method = validated_data.get("payment_method")

        # Get the cart
        cart = Cart.objects.get(id=cart_id, user=request.user)

        # Create delivery info
        delivery_info = DeliveryInfo.objects.create(**delivery_data)

        # Auto-detect first order for this customer and create order
        try:
            is_first_order = not MarketplaceOrder.objects.filter(customer=cart.user, is_deleted=False).exists()
        except Exception:
            is_first_order = False

        order = MarketplaceOrder.objects.create_order_from_cart(
            cart=cart, delivery_info=delivery_info, payment_method=payment_method, is_first_order=is_first_order
        )

        # Clear the cart after successful order creation
        cart.items.all().delete()

        return order


class VoiceSearchInputSerializer(serializers.Serializer):
    audio_file = serializers.FileField(required=False)
    query = serializers.CharField(required=False, max_length=255)

    def validate(self, data):
        if not data.get("audio_file") and not data.get("query"):
            raise serializers.ValidationError("Either 'audio_file' or 'query' must be provided.")
        return data


class ShoppableVideoSerializer(serializers.ModelSerializer):
    uploader_name = serializers.CharField(source="uploader.username", read_only=True)
    uploader_profile = serializers.SerializerMethodField()
    uploader_profile_url = serializers.SerializerMethodField()
    creator_profile = serializers.SerializerMethodField()
    creator_profile_id = serializers.IntegerField(write_only=True, required=False)
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
            "video_file",
            "thumbnail",
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
