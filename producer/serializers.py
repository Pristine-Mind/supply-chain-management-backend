import json
from datetime import datetime
from django.contrib.gis.geos import Point

from rest_framework import serializers

from .models import (
    Producer,
    Customer,
    Product,
    Order,
    Sale,
    StockList,
    MarketplaceProduct,
    ProductImage,
    City,
)


class ProducerSerializer(serializers.ModelSerializer):
    location_details = serializers.SerializerMethodField()

    class Meta:
        model = Producer
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def get_location_details(self, producer) -> dict:
        if producer and producer.location:
            return json.loads(producer.location.geojson)
        return None

    def validate_registration_number(self, value):
        """
        Validate that the registration number is alphanumeric and unique.
        """
        if not value.isalnum():
            raise serializers.ValidationError("Registration number must be alphanumeric.")
        return value

    def create(self, validated_data):
        location_data = self.initial_data.get("location")
        if location_data:
            latitude = location_data.get("latitude")
            longitude = location_data.get("longitude")

            if latitude is not None and longitude is not None:
                validated_data["location"] = Point(longitude, latitude)
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        location_data = self.initial_data.get("location")
        if location_data:
            latitude = location_data.get("latitude")
            longitude = location_data.get("longitude")

            if latitude is not None and longitude is not None:
                validated_data["location"] = Point(longitude, latitude)
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

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

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "created_at"]


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(child=serializers.ImageField(), write_only=True, required=False)
    category_details = serializers.CharField(source="get_category_display", read_only=True)
    deleted_images = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)

    class Meta:
        model = Product
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

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

    def create(self, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        validated_data["user"] = self.context["request"].user
        product = super().create(validated_data)
        for image in uploaded_images:
            ProductImage.objects.create(product=product, image=image)

        return product

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        deleted_images = validated_data.pop("deleted_images", [])
        validated_data["user"] = self.context["request"].user
        product = super().update(instance, validated_data)
        for image in uploaded_images:
            ProductImage.objects.create(product=product, image=image)

        if deleted_images:
            ProductImage.objects.filter(id__in=deleted_images, product=product).delete()

        return product


class OrderSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    customer_details = CustomerSerializer(source="customer", read_only=True)
    product_details = ProductSerializer(source="product", read_only=True)
    order_number = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

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

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class SaleSerializer(serializers.ModelSerializer):
    order_details = OrderSerializer(source="order", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)

    class Meta:
        model = Sale
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

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
        product = data["order"]
        if data["sale_price"] > product.product.price:
            raise serializers.ValidationError("Sale price cannot be greater than the original product price.")
        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)


class CustomerSalesSerializer(serializers.Serializer):
    total_sales = serializers.FloatField()
    name = serializers.CharField()
    id = serializers.IntegerField()

    class Meta:
        fields = ["id", "name", "total_sales"]


class CustomerOrdersSerializer(serializers.ModelSerializer):
    total_orders = serializers.IntegerField()

    class Meta:
        model = Customer
        fields = ["id", "name", "total_orders"]


class StockListSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source="product", read_only=True)

    class Meta:
        model = StockList
        fields = ["product", "moved_date", "product_details", "id", "is_pushed_to_marketplace"]


class MarketplaceProductSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source="product", read_only=True)

    class Meta:
        model = MarketplaceProduct
        fields = ["product", "listed_price", "listed_date", "is_available", "id", "product_details", "bid_end_date"]


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name']
