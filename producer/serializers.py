from datetime import datetime

from rest_framework import serializers

from .models import Producer, Customer, Product, Order, Sale


class ProducerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producer
        fields = "__all__"

    def validate_registration_number(self, value):
        """
        Validate that the registration number is alphanumeric and unique.
        """
        if not value.isalnum():
            raise serializers.ValidationError("Registration number must be alphanumeric.")
        return value


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"

    def validate_credit_limit(self, value):
        """
        Ensure the credit limit is a non-negative value.
        """
        if value < 0:
            raise serializers.ValidationError("Credit limit cannot be negative.")
        return value

    def validate_current_balance(self, value):
        """
        Ensure the current balance is non-negative.
        """
        if value < 0:
            raise serializers.ValidationError("Current balance cannot be negative.")
        return value


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"

    def validate_price(self, value):
        """
        Ensure that the product price is a positive number.
        """
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_cost_price(self, value):
        """
        Ensure that the cost price is a positive number and not greater than the selling price.
        """
        if value <= 0:
            raise serializers.ValidationError("Cost price must be greater than zero.")
        return value

    def validate(self, data):
        """
        Ensure that the cost price is not greater than the selling price.
        """
        if data["cost_price"] > data["price"]:
            raise serializers.ValidationError("Cost price cannot be greater than selling price.")
        return data


class OrderSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)

    class Meta:
        model = Order
        fields = "__all__"

    def validate_quantity(self, value):
        """
        Ensure the order quantity is a positive integer.
        """
        if value <= 0:
            raise serializers.ValidationError("Order quantity must be greater than zero.")
        return value

    def validate_total_price(self, value):
        """
        Ensure that the total price is positive.
        """
        if value <= 0:
            raise serializers.ValidationError("Total price must be greater than zero.")
        return value

    def validate_status(self, value):
        """
        Ensure the status is one of the defined choices.
        """
        if value not in dict(Order.Status.choices).keys():
            raise serializers.ValidationError("Invalid status choice.")
        return value

    def validate_delivery_date(self, value):
        """
        Ensure the delivery date is not in the past or before the order date.
        """
        if value and value < datetime.now():
            raise serializers.ValidationError("Delivery date cannot be in the past.")
        return value

    def validate(self, data):
        # Ensure delivery_date is after order_date
        if "delivery_date" in data and data["delivery_date"] and data["delivery_date"] < data["order_date"]:
            raise serializers.ValidationError("Delivery date cannot be before the order date.")

        # Ensure payment_due_date is after order_date
        if "payment_due_date" in data and data["payment_due_date"] and data["payment_due_date"] < data["order_date"]:
            raise serializers.ValidationError("Payment due date cannot be before the order date.")

        return data


class SaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = "__all__"

    def validate_quantity(self, value):
        """
        Ensure the sale quantity is a positive integer.
        """
        if value <= 0:
            raise serializers.ValidationError("Sale quantity must be greater than zero.")
        return value

    def validate_sale_price(self, value):
        """
        Ensure the sale price is a positive number.
        """
        if value <= 0:
            raise serializers.ValidationError("Sale price must be greater than zero.")
        return value

    def validate(self, data):
        """
        Ensure that the sale price does not exceed the original product price.
        """
        product = data["product"]
        if data["sale_price"] > product.price:
            raise serializers.ValidationError("Sale price cannot be greater than the original product price.")
        return data