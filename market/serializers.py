from urllib.parse import urlencode
import time
import requests
import json
import torch
import joblib
import os
import numpy as np

from django.utils import timezone
from django.contrib.auth.models import User

from rest_framework import serializers

from .models import Purchase, Bid, ChatMessage, Payment, MarketplaceUserProduct
from producer.models import MarketplaceProduct
from .transformer import TransformerBidPredictor

model_path = 'transformer_bid_model.pth'
scaler_x_path = 'scaler_x.pkl'
scaler_y_path = 'scaler_y.pkl'

# Check if files exist and load them if available
if not os.path.exists(model_path):
    raise FileNotFoundError(f"Model file '{model_path}' not found.")
if not os.path.exists(scaler_x_path):
    raise FileNotFoundError(f"Scaler file '{scaler_x_path}' not found.")
if not os.path.exists(scaler_y_path):
    raise FileNotFoundError(f"Scaler file '{scaler_y_path}' not found.")

# Load the trained model and scalers
scaler_x = joblib.load(scaler_x_path)
scaler_y = joblib.load(scaler_y_path)

# Model Configuration (must match training setup)
input_dim = 2  # This should match the input_dim used during training
d_model = 64
num_heads = 8
num_layers = 4
dropout = 0.1

# Instantiate and load the trained model
model = TransformerBidPredictor(input_dim=input_dim, d_model=d_model, num_heads=num_heads, num_layers=num_layers, dropout=dropout)
model.load_state_dict(torch.load(model_path))
model.eval()


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
            print(response.json(), "hhhhhhh")
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
    suggested_bid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Bid
        fields = ["bidder", "product_id", "bid_amount", "bid_date", "max_bid_amount", "suggested_bid"]
        read_only_fields = ["bid_date", "bidder", "suggested_bid"]

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

        data["product"] = product
        return data

    def create(self, validated_data):
        product = validated_data["product"]
        bid_amount = validated_data["bid_amount"]
        bidder = self.context["request"].user

        # Get recent bids for this product
        recent_bids = Bid.objects.filter(product=product).order_by('-bid_date')[:2]

        # Prepare the input sequence for prediction
        if recent_bids.exists():
            bid_sequence = [float(bid.max_bid_amount) for bid in recent_bids]
            bid_sequence.reverse()  # Ensure sequence is in the correct order (oldest to newest)
            print(bid_sequence, "seq")
            # Convert to numpy array and scale the input sequence
            bid_sequence_array = np.array([bid_sequence], dtype=np.float32)  # Shape: (1, input_dim)
            bid_sequence_scaled = scaler_x.transform(bid_sequence_array)  # Scale the input sequence

            # Convert to PyTorch tensor
            input_sequence_tensor = torch.tensor(bid_sequence_scaled, dtype=torch.float32)

            # Make prediction using the model
            with torch.no_grad():
                suggested_bid_scaled = model(input_sequence_tensor).item()
                print(suggested_bid_scaled, "sss")
            # Inverse scale the predicted bid to get the actual bid value
            suggested_bid = scaler_y.inverse_transform([[suggested_bid_scaled]])[0][0]
        else:
            # Default suggestion if no previous bids: start slightly above the listed price
            suggested_bid = float(product.listed_price) * 1.05
            print(suggested_bid, "nnnnnnn")

        # Determine max_bid_amount
        highest_bid = Bid.objects.filter(product=product).order_by("-bid_amount").first()
        if highest_bid is None or bid_amount > highest_bid.max_bid_amount:
            max_bid_amount = bid_amount
        else:
            max_bid_amount = highest_bid.max_bid_amount

        # Create the bid instance
        bid = Bid.objects.create(
            bidder=bidder,
            product=product,
            bid_amount=bid_amount,
            max_bid_amount=max_bid_amount,
            suggested_bid=suggested_bid
        )
        return bid


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class ChatMessageSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    message = serializers.CharField()
    sender_details = UserSerializer(source="sender", read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["sender", "product_id", "message", "timestamp", "sender_details"]
        read_only_fields = ["sender", "timestamp"]

    def validate(self, data):
        try:
            product = MarketplaceProduct.objects.get(id=data["product_id"])
        except MarketplaceProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found.")
        data["product"] = product
        return data

    def create(self, validated_data):
        product = validated_data["product"]
        message = validated_data["message"]
        chat_message = ChatMessage.objects.create(sender=self.context["request"].user, product=product, message=message)

        return chat_message


class MarketplaceUserProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceUserProduct
        fields = '__all__'

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(_("Price must be greater than zero."))
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError(_("Stock cannot be negative."))
        return value
