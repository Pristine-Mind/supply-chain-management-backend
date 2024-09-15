from django.utils import timezone
from django.contrib.auth.models import User
from urllib.parse import urlencode
import time

from rest_framework import serializers

from .models import Purchase, Bid, ChatMessage, Payment
from producer.models import MarketplaceProduct


class PurchaseSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    quantity = serializers.IntegerField()
    payment_url = serializers.URLField(read_only=True)

    class Meta:
        model = Purchase
        fields = ['buyer', 'product_id', 'quantity', 'purchase_price', 'purchase_date', 'payment_url']
        read_only_fields = ['purchase_price', 'purchase_date', 'buyer', 'payment_url']

    def validate(self, data):
        try:
            product = MarketplaceProduct.objects.get(id=data['product_id'])
        except MarketplaceProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found.")

        if not product.is_available:
            raise serializers.ValidationError("Product is not available for purchase.")
        if product.product.stock < data['quantity']:
            raise serializers.ValidationError("Insufficient stock for the requested quantity.")

        if product.bid_end_date and product.bid_end_date > timezone.now():
            raise serializers.ValidationError("The bidding time is not over yet. Purchase is not allowed.")

        data['product'] = product
        return data

    def create(self, validated_data):
        product = validated_data['product']
        quantity = validated_data['quantity']
        buyer = self.context['request'].user

        # Get the highest bid
        bid = Bid.objects.filter(product__id=product.id).order_by('-max_bid_amount').first()
        if not bid or bid.bidder != buyer:
            raise serializers.ValidationError("Only the highest bidder can purchase this product.")

        # Calculate the total price
        total_price = bid.max_bid_amount * quantity

        # Create the Purchase object
        purchase = Purchase.objects.create(
            buyer=buyer,
            product=product,
            quantity=quantity,
            purchase_price=total_price
        )

        # Update product stock
        product.product.stock -= quantity
        if product.product.stock == 0:
            product.is_available = False
        product.product.save()

        # Generate a unique transaction ID for the payment
        transaction_id = 'TXN' + str(int(time.time()))

        # Create the Payment object
        Payment.objects.create(
            purchase=purchase,
            transaction_id=transaction_id,
            amount=total_price,
            status='pending'
        )

        # Prepare the eSewa payment URL and parameters
        esewa_payment_url = 'https://uat.esewa.com.np/epay/main'
        success_url = self.context['request'].build_absolute_uri('/payment/verify/')
        failure_url = self.context['request'].build_absolute_uri('/payment/failure/')

        payload = {
            'amt': total_price,
            'txAmt': 0,
            'psc': 0,
            'pdc': 0,
            'tAmt': total_price,
            'pid': transaction_id,
            'scd': 'EPAYTEST',  # eSewa Merchant ID for sandbox
            'su': success_url,
            'fu': failure_url
        }

        # Generate the full payment URL
        payment_url = f"{esewa_payment_url}?{urlencode(payload)}"

        # Return the Purchase object with additional payment_url information
        return {
            'purchase': purchase,
            'payment_url': payment_url
        }


class BidSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    bid_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    max_bid_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Bid
        fields = ['bidder', 'product_id', 'bid_amount', 'bid_date', 'max_bid_amount']
        read_only_fields = ['bid_date', 'bidder']

    def validate(self, data):
        try:
            product = MarketplaceProduct.objects.get(id=data['product_id'])
        except MarketplaceProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found.")
        if data['bid_amount'] <= product.listed_price:
            raise serializers.ValidationError("Bid amount must be higher than the listed price.")
        highest_bid = Bid.objects.filter(product=product).order_by('-bid_amount').first()
        if highest_bid and data['bid_amount'] <= highest_bid.bid_amount:
            raise serializers.ValidationError("Your bid must be higher than the current highest bid.")

        data['product'] = product
        return data

    def create(self, validated_data):
        product = validated_data['product']
        bid_amount = validated_data['bid_amount']
        bidder = self.context['request'].user
        highest_bid = Bid.objects.filter(product=product).order_by('-bid_amount').first()
        if highest_bid is None or bid_amount > highest_bid.max_bid_amount:
            max_bid_amount = bid_amount
        else:
            max_bid_amount = highest_bid.max_bid_amount

        bid = Bid.objects.create(
            bidder=bidder,
            product=product,
            bid_amount=bid_amount,
            max_bid_amount=max_bid_amount
        )

        return bid


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id',
            'username'
        )


class ChatMessageSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    message = serializers.CharField()
    sender_details = UserSerializer(source='sender', read_only=True)

    class Meta:
        model = ChatMessage
        fields = ['sender', 'product_id', 'message', 'timestamp', 'sender_details']
        read_only_fields = ['sender', 'timestamp']

    def validate(self, data):
        try:
            product = MarketplaceProduct.objects.get(id=data['product_id'])
        except MarketplaceProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found.")
        data['product'] = product
        return data

    def create(self, validated_data):
        product = validated_data['product']
        message = validated_data['message']
        chat_message = ChatMessage.objects.create(
            sender=self.context['request'].user,
            product=product,
            message=message
        )

        return chat_message
