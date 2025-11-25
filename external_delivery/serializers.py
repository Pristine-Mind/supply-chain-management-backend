from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import (
    ExternalBusiness,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
    ExternalDeliveryStatusHistory,
)


class ExternalBusinessSerializer(serializers.ModelSerializer):
    """Serializer for external business registration"""

    api_key = serializers.CharField(read_only=True)
    webhook_secret = serializers.CharField(read_only=True)
    usage_stats = serializers.SerializerMethodField()

    class Meta:
        model = ExternalBusiness
        fields = [
            "id",
            "business_name",
            "business_email",
            "contact_person",
            "contact_phone",
            "business_address",
            "registration_number",
            "website",
            "webhook_url",
            "plan",
            "status",
            "api_key",
            "webhook_secret",
            "max_delivery_value",
            "allowed_pickup_cities",
            "allowed_delivery_cities",
            "created_at",
            "usage_stats",
        ]
        read_only_fields = ["id", "api_key", "webhook_secret", "status", "created_at", "usage_stats"]

    def get_usage_stats(self, obj):
        return obj.get_usage_stats()

    def validate_business_email(self, value):
        """Validate business email uniqueness"""
        if self.instance and self.instance.business_email == value:
            return value

        if ExternalBusiness.objects.filter(business_email=value).exists():
            raise serializers.ValidationError("Business with this email already exists.")

        return value


class ExternalDeliveryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating external deliveries"""

    # Read-only fields that will be set automatically
    tracking_number = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    platform_commission = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    transporter_earnings = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ExternalDelivery
        fields = [
            # External reference
            "external_delivery_id",
            # Pickup information
            "pickup_name",
            "pickup_phone",
            "pickup_address",
            "pickup_city",
            "pickup_latitude",
            "pickup_longitude",
            "pickup_instructions",
            # Delivery information
            "delivery_name",
            "delivery_phone",
            "delivery_address",
            "delivery_city",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_instructions",
            # Package information
            "package_description",
            "package_weight",
            "package_value",
            "fragile",
            # Scheduling
            "scheduled_pickup_time",
            "scheduled_delivery_time",
            # Payment
            "is_cod",
            "cod_amount",
            # Additional
            "notes",
            # Read-only response fields
            "tracking_number",
            "status",
            "delivery_fee",
            "platform_commission",
            "transporter_earnings",
            "created_at",
        ]

    def validate(self, data):
        """Validate delivery data"""
        # Validate COD
        if data.get("is_cod") and not data.get("cod_amount"):
            raise serializers.ValidationError({"cod_amount": "COD amount is required when is_cod is True."})

        if not data.get("is_cod") and data.get("cod_amount"):
            data["cod_amount"] = None

        # Validate package weight and value
        if data.get("package_weight", 0) <= 0:
            raise serializers.ValidationError({"package_weight": "Package weight must be greater than 0."})

        if data.get("package_value", 0) <= 0:
            raise serializers.ValidationError({"package_value": "Package value must be greater than 0."})

        return data

    def create(self, validated_data):
        """Create delivery with automatic fee calculation"""
        # The external_business will be set in the view
        delivery = super().create(validated_data)

        # Calculate delivery fees
        fees = delivery.calculate_delivery_fee()
        delivery.delivery_fee = fees["delivery_fee"]
        delivery.platform_commission = fees["platform_commission"]
        delivery.transporter_earnings = fees["transporter_earnings"]
        delivery.save(update_fields=["delivery_fee", "platform_commission", "transporter_earnings"])

        return delivery


class ExternalDeliverySerializer(serializers.ModelSerializer):
    """Detailed serializer for external deliveries"""

    external_business_name = serializers.CharField(source="external_business.business_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = ExternalDelivery
        fields = [
            "id",
            "external_business_name",
            "external_delivery_id",
            "tracking_number",
            "status",
            "status_display",
            # Pickup information
            "pickup_name",
            "pickup_phone",
            "pickup_address",
            "pickup_city",
            "pickup_latitude",
            "pickup_longitude",
            "pickup_instructions",
            # Delivery information
            "delivery_name",
            "delivery_phone",
            "delivery_address",
            "delivery_city",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_instructions",
            # Package information
            "package_description",
            "package_weight",
            "package_value",
            "fragile",
            # Scheduling
            "scheduled_pickup_time",
            "scheduled_delivery_time",
            # Payment
            "is_cod",
            "cod_amount",
            "delivery_fee",
            "platform_commission",
            "transporter_earnings",
            # Status tracking
            "created_at",
            "updated_at",
            "accepted_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
            # Additional information
            "notes",
            "cancellation_reason",
            "failure_reason",
            "can_cancel",
        ]
        read_only_fields = [
            "id",
            "external_business_name",
            "tracking_number",
            "status",
            "status_display",
            "delivery_fee",
            "platform_commission",
            "transporter_earnings",
            "created_at",
            "updated_at",
            "accepted_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
            "can_cancel",
        ]

    def get_can_cancel(self, obj):
        return obj.can_cancel()


class ExternalDeliveryUpdateStatusSerializer(serializers.Serializer):
    """Serializer for updating delivery status"""

    status = serializers.ChoiceField(choices=ExternalDeliveryStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_status(self, value):
        """Validate status transition"""
        delivery = self.context["delivery"]

        # Check if status transition is valid
        valid_transitions = {
            ExternalDeliveryStatus.PENDING: [ExternalDeliveryStatus.ACCEPTED, ExternalDeliveryStatus.CANCELLED],
            ExternalDeliveryStatus.ACCEPTED: [ExternalDeliveryStatus.PICKED_UP, ExternalDeliveryStatus.CANCELLED],
            ExternalDeliveryStatus.PICKED_UP: [
                ExternalDeliveryStatus.IN_TRANSIT,
                ExternalDeliveryStatus.DELIVERED,
                ExternalDeliveryStatus.FAILED,
            ],
            ExternalDeliveryStatus.IN_TRANSIT: [ExternalDeliveryStatus.DELIVERED, ExternalDeliveryStatus.FAILED],
        }

        current_status = delivery.status
        if current_status in valid_transitions and value not in valid_transitions[current_status]:
            raise serializers.ValidationError(f"Cannot transition from {current_status} to {value}")

        return value


class ExternalDeliveryStatusHistorySerializer(serializers.ModelSerializer):
    """Serializer for delivery status history"""

    old_status_display = serializers.CharField(source="get_old_status_display", read_only=True)
    new_status_display = serializers.CharField(source="get_new_status_display", read_only=True)
    changed_by_name = serializers.CharField(source="changed_by.get_full_name", read_only=True)

    class Meta:
        model = ExternalDeliveryStatusHistory
        fields = [
            "id",
            "old_status",
            "old_status_display",
            "new_status",
            "new_status_display",
            "reason",
            "changed_by_name",
            "changed_at",
        ]


class ExternalDeliveryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for delivery lists"""

    external_business_name = serializers.CharField(source="external_business.business_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ExternalDelivery
        fields = [
            "id",
            "tracking_number",
            "external_business_name",
            "external_delivery_id",
            "status",
            "status_display",
            "pickup_city",
            "delivery_city",
            "package_value",
            "delivery_fee",
            "is_cod",
            "cod_amount",
            "created_at",
            "scheduled_pickup_time",
        ]


class ExternalDeliveryTrackingSerializer(serializers.ModelSerializer):
    """Public tracking serializer with limited information"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    estimated_delivery = serializers.SerializerMethodField()

    class Meta:
        model = ExternalDelivery
        fields = [
            "tracking_number",
            "status",
            "status_display",
            "pickup_city",
            "delivery_city",
            "created_at",
            "accepted_at",
            "picked_up_at",
            "delivered_at",
            "estimated_delivery",
        ]

    def get_estimated_delivery(self, obj):
        """Calculate estimated delivery time"""
        if obj.scheduled_delivery_time:
            return obj.scheduled_delivery_time

        # Default estimation logic
        if obj.accepted_at:
            if obj.pickup_city == obj.delivery_city:
                # Same city: 1 day
                return obj.accepted_at + timedelta(days=1)
            else:
                # Different city: 2-3 days
                return obj.accepted_at + timedelta(days=2)

        return None


class ExternalBusinessStatsSerializer(serializers.Serializer):
    """Serializer for business statistics"""

    total_deliveries = serializers.IntegerField()
    current_month_deliveries = serializers.IntegerField()
    successful_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    pending_deliveries = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    current_month_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    success_rate = serializers.FloatField()
    average_delivery_value = serializers.DecimalField(max_digits=15, decimal_places=2)


class WebhookTestSerializer(serializers.Serializer):
    """Serializer for testing webhook endpoints"""

    webhook_url = serializers.URLField()
    event_type = serializers.CharField(max_length=50)
    test_data = serializers.JSONField(required=False, default=dict)
