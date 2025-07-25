from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (
    Delivery,
    DeliveryPriority,
    DeliveryRating,
    DeliveryTracking,
    Transporter,
    TransportStatus,
)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = ["id", "username"]


class TransporterSerializer(serializers.ModelSerializer):
    """Serializer for Transporter model"""

    user = UserSerializer(read_only=True)
    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = Transporter
        fields = [
            "id",
            "user",
            "license_number",
            "phone",
            "vehicle_type",
            "vehicle_number",
            "vehicle_capacity",
            "current_latitude",
            "current_longitude",
            "is_available",
            "rating",
            "total_deliveries",
            "successful_deliveries",
            "success_rate",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "rating",
            "total_deliveries",
            "successful_deliveries",
            "is_verified",
            "created_at",
            "updated_at",
        ]


class TransporterCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Transporter profile"""

    class Meta:
        model = Transporter
        fields = [
            "license_number",
            "phone",
            "vehicle_type",
            "vehicle_number",
            "vehicle_capacity",
            "current_latitude",
            "current_longitude",
        ]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class MarketplaceSaleBasicSerializer(serializers.Serializer):
    """Basic serializer for MarketplaceSale to avoid circular imports"""

    id = serializers.IntegerField(read_only=True)
    order_number = serializers.CharField(read_only=True)
    buyer_name = serializers.CharField(read_only=True)
    buyer_email = serializers.EmailField(read_only=True)
    buyer_phone = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    # Product information
    product_name = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()

    def get_product_name(self, obj):
        return obj.product.name if hasattr(obj, "product") and obj.product else "N/A"

    def get_seller_name(self, obj):
        return obj.seller.get_full_name() if hasattr(obj, "seller") and obj.seller else "N/A"


class DeliverySerializer(serializers.ModelSerializer):
    """Serializer for Delivery model"""

    marketplace_sale = MarketplaceSaleBasicSerializer(read_only=True)
    transporter = TransporterSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "delivery_id",
            "marketplace_sale",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "pickup_contact_name",
            "pickup_contact_phone",
            "delivery_address",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_contact_name",
            "delivery_contact_phone",
            "package_weight",
            "package_dimensions",
            "special_instructions",
            "transporter",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "requested_pickup_date",
            "requested_delivery_date",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "delivery_fee",
            "distance_km",
            "estimated_delivery_time",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "delivery_id",
            "marketplace_sale",
            "transporter",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "created_at",
            "updated_at",
        ]


class DeliveryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for delivery list views"""

    transporter_name = serializers.SerializerMethodField()
    marketplace_sale = MarketplaceSaleBasicSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "delivery_id",
            "marketplace_sale",
            "pickup_address",
            "delivery_address",
            "package_weight",
            "transporter_name",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "requested_pickup_date",
            "delivery_fee",
            "distance_km",
            "created_at",
        ]

    def get_transporter_name(self, obj):
        return obj.transporter.user.get_full_name() if obj.transporter else None


class DeliveryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating deliveries"""

    class Meta:
        model = Delivery
        fields = [
            "marketplace_sale",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "pickup_contact_name",
            "pickup_contact_phone",
            "delivery_address",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_contact_name",
            "delivery_contact_phone",
            "package_weight",
            "package_dimensions",
            "special_instructions",
            "priority",
            "requested_pickup_date",
            "requested_delivery_date",
            "delivery_fee",
            "distance_km",
        ]


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryTracking model"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = DeliveryTracking
        fields = ["id", "delivery", "status", "status_display", "latitude", "longitude", "notes", "timestamp"]
        read_only_fields = ["id", "timestamp"]


class DeliveryRatingSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryRating model"""

    rated_by_name = serializers.SerializerMethodField()
    transporter_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRating
        fields = [
            "id",
            "delivery",
            "rated_by",
            "rated_by_name",
            "transporter",
            "transporter_name",
            "rating",
            "comment",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_rated_by_name(self, obj):
        return obj.rated_by.get_full_name()

    def get_transporter_name(self, obj):
        return obj.transporter.user.get_full_name()


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating delivery status"""

    status = serializers.ChoiceField(choices=TransportStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    def validate_status(self, value):
        """Validate status transition"""
        delivery = self.context.get("delivery")
        if not delivery:
            return value

        valid_transitions = {
            TransportStatus.ASSIGNED: [TransportStatus.PICKED_UP],
            TransportStatus.PICKED_UP: [TransportStatus.IN_TRANSIT],
            TransportStatus.IN_TRANSIT: [TransportStatus.DELIVERED],
        }

        if value not in valid_transitions.get(delivery.status, []):
            raise serializers.ValidationError(f"Invalid status transition from {delivery.status} to {value}")

        return value


class LocationUpdateSerializer(serializers.Serializer):
    """Serializer for updating transporter location"""

    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class DeliveryFilterSerializer(serializers.Serializer):
    """Serializer for delivery filtering parameters"""

    status = serializers.ChoiceField(choices=TransportStatus.choices, required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=DeliveryPriority.choices, required=False, allow_blank=True)
    transporter = serializers.IntegerField(required=False)
    weight_max = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    distance_max = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    pickup_date_from = serializers.DateTimeField(required=False)
    pickup_date_to = serializers.DateTimeField(required=False)
    delivery_date_from = serializers.DateTimeField(required=False)
    delivery_date_to = serializers.DateTimeField(required=False)


class TransporterStatsSerializer(serializers.Serializer):
    """Serializer for transporter statistics"""

    total_deliveries = serializers.IntegerField()
    successful_deliveries = serializers.IntegerField()
    success_rate = serializers.FloatField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    deliveries_this_month = serializers.IntegerField()
    earnings_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    active_deliveries = serializers.IntegerField()


class DeliveryDashboardSerializer(serializers.Serializer):
    """Serializer for delivery dashboard statistics"""

    total_deliveries = serializers.IntegerField()
    pending_deliveries = serializers.IntegerField()
    assigned_deliveries = serializers.IntegerField()
    in_transit_deliveries = serializers.IntegerField()
    completed_deliveries = serializers.IntegerField()
    total_transporters = serializers.IntegerField()
    active_transporters = serializers.IntegerField()
    average_delivery_time = serializers.FloatField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)


class NearbyDeliverySerializer(serializers.ModelSerializer):
    """Serializer for nearby deliveries based on location"""

    distance = serializers.FloatField(read_only=True)
    marketplace_sale = MarketplaceSaleBasicSerializer(read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "delivery_id",
            "marketplace_sale",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "delivery_address",
            "package_weight",
            "priority",
            "requested_pickup_date",
            "delivery_fee",
            "distance",
            "distance_km",
        ]
