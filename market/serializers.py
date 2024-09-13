from rest_framework import serializers
from django.utils import timezone
from django.contrib.auth.models import User

from .models import Purchase, Bid, ChatMessage
from producer.models import MarketplaceProduct


class PurchaseSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    quantity = serializers.IntegerField()

    class Meta:
        model = Purchase
        fields = ['buyer', 'product_id', 'quantity', 'purchase_price', 'purchase_date']
        read_only_fields = ['purchase_price', 'purchase_date', 'buyer']

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
        bid = Bid.objects.filter(product__id=product.id).order_by('-max_bid_amount').first()
        total_price = bid.max_bid_amount * quantity
        purchase = Purchase.objects.create(
            buyer=self.context['request'].user,
            product=product,
            quantity=quantity,
            purchase_price=total_price
        )
        product.product.stock -= quantity
        product.product.save()

        return purchase


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
