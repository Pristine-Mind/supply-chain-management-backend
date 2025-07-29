from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (
    Delivery,
    DeliveryPriority,
    DeliveryRating,
    DeliveryRoute,
    DeliveryTracking,
    RouteDelivery,
    Transporter,
    TransporterStatus,
    TransportStatus,
    VehicleType,
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
    cancellation_rate = serializers.ReadOnlyField()
    vehicle_type_display = serializers.CharField(source="get_vehicle_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_documents_expired = serializers.ReadOnlyField()
    current_deliveries_count = serializers.SerializerMethodField()

    class Meta:
        model = Transporter
        fields = [
            "id",
            "user",
            "license_number",
            "phone",
            "emergency_contact",
            "business_name",
            "tax_id",
            "vehicle_type",
            "vehicle_type_display",
            "vehicle_number",
            "vehicle_capacity",
            "vehicle_image",
            "vehicle_documents",
            "insurance_expiry",
            "license_expiry",
            "current_latitude",
            "current_longitude",
            "service_radius",
            "is_available",
            "status",
            "status_display",
            "last_location_update",
            "rating",
            "total_deliveries",
            "successful_deliveries",
            "cancelled_deliveries",
            "success_rate",
            "cancellation_rate",
            "earnings_total",
            "commission_rate",
            "is_verified",
            "verification_documents",
            "is_documents_expired",
            "current_deliveries_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "rating",
            "total_deliveries",
            "successful_deliveries",
            "cancelled_deliveries",
            "earnings_total",
            "is_verified",
            "verification_documents",
            "last_location_update",
            "created_at",
            "updated_at",
        ]

    def get_current_deliveries_count(self, obj):
        return obj.get_current_deliveries().count()


class TransporterCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Transporter profile"""

    class Meta:
        model = Transporter
        fields = [
            "license_number",
            "phone",
            "emergency_contact",
            "business_name",
            "tax_id",
            "vehicle_type",
            "vehicle_number",
            "vehicle_capacity",
            "vehicle_image",
            "vehicle_documents",
            "insurance_expiry",
            "license_expiry",
            "current_latitude",
            "current_longitude",
            "service_radius",
            "commission_rate",
        ]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class TransporterListSerializer(serializers.ModelSerializer):
    """Simplified serializer for transporter list views"""

    user_name = serializers.SerializerMethodField()
    vehicle_type_display = serializers.CharField(source="get_vehicle_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = Transporter
        fields = [
            "id",
            "user_name",
            "license_number",
            "phone",
            "vehicle_type",
            "vehicle_type_display",
            "vehicle_number",
            "vehicle_capacity",
            "is_available",
            "status",
            "status_display",
            "rating",
            "success_rate",
            "total_deliveries",
            "is_verified",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class TransporterUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating Transporter profile"""

    class Meta:
        model = Transporter
        fields = [
            "phone",
            "emergency_contact",
            "business_name",
            "tax_id",
            "vehicle_type",
            "vehicle_number",
            "vehicle_capacity",
            "vehicle_image",
            "vehicle_documents",
            "insurance_expiry",
            "license_expiry",
            "service_radius",
            "is_available",
        ]


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
    tracking_number = serializers.CharField(read_only=True)
    success_rate = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    time_since_pickup = serializers.ReadOnlyField()

    class Meta:
        model = Delivery
        fields = [
            "id",
            "delivery_id",
            "marketplace_sale",
            "tracking_number",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "pickup_contact_name",
            "pickup_contact_phone",
            "pickup_instructions",
            "delivery_address",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_contact_name",
            "delivery_contact_phone",
            "delivery_instructions",
            "package_weight",
            "package_dimensions",
            "package_value",
            "fragile",
            "requires_signature",
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
            "cancelled_at",
            "cancellation_reason",
            "delivery_fee",
            "distance_km",
            "fuel_surcharge",
            "estimated_delivery_time",
            "actual_pickup_time",
            "delivery_photo",
            "signature_image",
            "delivery_notes",
            "delivery_attempts",
            "max_delivery_attempts",
            "is_overdue",
            "time_since_pickup",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "delivery_id",
            "marketplace_sale",
            "tracking_number",
            "transporter",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
            "actual_pickup_time",
            "delivery_attempts",
            "created_at",
            "updated_at",
        ]


class DeliveryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for delivery list views"""

    transporter_name = serializers.SerializerMethodField()
    marketplace_sale = MarketplaceSaleBasicSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = Delivery
        fields = [
            "id",
            "delivery_id",
            "tracking_number",
            "marketplace_sale",
            "pickup_address",
            "delivery_address",
            "package_weight",
            "fragile",
            "transporter_name",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "requested_pickup_date",
            "requested_delivery_date",
            "delivery_fee",
            "distance_km",
            "is_overdue",
            "delivery_attempts",
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
            "pickup_instructions",
            "delivery_address",
            "delivery_latitude",
            "delivery_longitude",
            "delivery_contact_name",
            "delivery_contact_phone",
            "delivery_instructions",
            "package_weight",
            "package_dimensions",
            "package_value",
            "fragile",
            "requires_signature",
            "special_instructions",
            "priority",
            "requested_pickup_date",
            "requested_delivery_date",
            "delivery_fee",
            "distance_km",
            "fuel_surcharge",
            "max_delivery_attempts",
        ]


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryTracking model"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryTracking
        fields = [
            "id",
            "delivery",
            "status",
            "status_display",
            "latitude",
            "longitude",
            "notes",
            "timestamp",
            "created_by",
            "created_by_name",
        ]
        read_only_fields = ["id", "timestamp"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


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
            "overall_rating",
            "punctuality_rating",
            "communication_rating",
            "package_handling_rating",
            "comment",
            "is_anonymous",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_rated_by_name(self, obj):
        if obj.is_anonymous:
            return "Anonymous"
        return obj.rated_by.get_full_name()

    def get_transporter_name(self, obj):
        return obj.transporter.user.get_full_name()


class DeliveryRatingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating delivery ratings"""

    class Meta:
        model = DeliveryRating
        fields = [
            "delivery",
            "transporter",
            "overall_rating",
            "punctuality_rating",
            "communication_rating",
            "package_handling_rating",
            "comment",
            "is_anonymous",
        ]

    def create(self, validated_data):
        validated_data["rated_by"] = self.context["request"].user
        return super().create(validated_data)


class RouteDeliverySerializer(serializers.ModelSerializer):
    """Serializer for RouteDelivery model"""

    delivery = DeliveryListSerializer(read_only=True)

    class Meta:
        model = RouteDelivery
        fields = ["id", "delivery", "order"]


class DeliveryRouteSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryRoute model"""

    transporter = TransporterListSerializer(read_only=True)
    route_deliveries = RouteDeliverySerializer(source="routedelivery_set", many=True, read_only=True)
    deliveries_count = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRoute
        fields = [
            "id",
            "transporter",
            "name",
            "route_deliveries",
            "deliveries_count",
            "estimated_distance",
            "estimated_duration",
            "created_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_deliveries_count(self, obj):
        return obj.deliveries.count()


class DeliveryRouteCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating delivery routes"""

    delivery_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)

    class Meta:
        model = DeliveryRoute
        fields = [
            "name",
            "delivery_ids",
            "estimated_distance",
            "estimated_duration",
        ]

    def create(self, validated_data):
        delivery_ids = validated_data.pop("delivery_ids", [])
        validated_data["transporter"] = self.context["request"].user.transporter_profile
        route = super().create(validated_data)

        # Add deliveries to route
        for order, delivery_id in enumerate(delivery_ids, 1):
            try:
                delivery = Delivery.objects.get(id=delivery_id)
                RouteDelivery.objects.create(route=route, delivery=delivery, order=order)
            except Delivery.DoesNotExist:
                continue

        return route


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating delivery status"""

    status = serializers.ChoiceField(choices=TransportStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    delivery_photo = serializers.ImageField(required=False, allow_null=True)
    signature_image = serializers.ImageField(required=False, allow_null=True)

    def validate_status(self, value):
        """Validate status transition"""
        delivery = self.context.get("delivery")
        if not delivery:
            return value

        valid_transitions = {
            TransportStatus.ASSIGNED: [TransportStatus.PICKED_UP, TransportStatus.CANCELLED],
            TransportStatus.PICKED_UP: [TransportStatus.IN_TRANSIT, TransportStatus.CANCELLED],
            TransportStatus.IN_TRANSIT: [TransportStatus.DELIVERED, TransportStatus.FAILED, TransportStatus.CANCELLED],
            TransportStatus.FAILED: [TransportStatus.RETURNED, TransportStatus.IN_TRANSIT],
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
    fragile = serializers.BooleanField(required=False)
    requires_signature = serializers.BooleanField(required=False)
    is_overdue = serializers.BooleanField(required=False)
    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices, required=False, allow_blank=True)


class TransporterStatsSerializer(serializers.Serializer):
    """Serializer for transporter statistics"""

    total_deliveries = serializers.IntegerField()
    successful_deliveries = serializers.IntegerField()
    cancelled_deliveries = serializers.IntegerField()
    success_rate = serializers.FloatField()
    cancellation_rate = serializers.FloatField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    deliveries_this_month = serializers.IntegerField()
    earnings_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    active_deliveries = serializers.IntegerField()
    average_delivery_time = serializers.FloatField()
    is_documents_expired = serializers.BooleanField()


class DeliveryDashboardSerializer(serializers.Serializer):
    """Serializer for delivery dashboard statistics"""

    total_deliveries = serializers.IntegerField()
    pending_deliveries = serializers.IntegerField()
    assigned_deliveries = serializers.IntegerField()
    picked_up_deliveries = serializers.IntegerField()
    in_transit_deliveries = serializers.IntegerField()
    completed_deliveries = serializers.IntegerField()
    cancelled_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    returned_deliveries = serializers.IntegerField()
    total_transporters = serializers.IntegerField()
    active_transporters = serializers.IntegerField()
    verified_transporters = serializers.IntegerField()
    average_delivery_time = serializers.FloatField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_deliveries = serializers.IntegerField()


class NearbyDeliverySerializer(serializers.ModelSerializer):
    """Serializer for nearby deliveries based on location"""

    distance = serializers.FloatField(read_only=True)
    marketplace_sale = MarketplaceSaleBasicSerializer(read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "delivery_id",
            "tracking_number",
            "marketplace_sale",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "delivery_address",
            "package_weight",
            "fragile",
            "priority",
            "priority_display",
            "requested_pickup_date",
            "delivery_fee",
            "distance",
            "distance_km",
        ]


class AssignmentRequestSerializer(serializers.Serializer):
    delivery_id = serializers.IntegerField(required=False)
    priority_filter = serializers.ChoiceField(choices=DeliveryPriority.choices, required=False, allow_blank=True)
    vehicle_type_filter = serializers.ChoiceField(choices=VehicleType.choices, required=False, allow_blank=True)
    max_distance_km = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    max_assignments = serializers.IntegerField(default=50, min_value=1, max_value=100)


class AssignmentResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField(required=False)
    error = serializers.CharField(required=False)
    assigned_transporter = serializers.DictField(required=False)
    delivery = serializers.DictField(required=False)
    score_details = serializers.DictField(required=False)
    alternatives = serializers.ListField(required=False)
    distance_km = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    estimated_delivery_time = serializers.DateTimeField(required=False)


class BulkAssignmentResponseSerializer(serializers.Serializer):
    total_deliveries = serializers.IntegerField()
    assigned = serializers.IntegerField()
    failed = serializers.IntegerField()
    assignments = serializers.ListField()
    failures = serializers.ListField()
    execution_time_seconds = serializers.FloatField()


class ReportFilterSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    transporter_id = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=TransportStatus.choices, required=False)
    priority = serializers.ChoiceField(choices=DeliveryPriority.choices, required=False)
    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices, required=False)
    report_type = serializers.ChoiceField(
        choices=[
            ("overview", "Overview"),
            ("performance", "Performance"),
            ("geographic", "Geographic"),
            ("time", "Time Analysis"),
            ("financial", "Financial"),
            ("comprehensive", "Comprehensive"),
        ],
        default="comprehensive",
    )


class DistanceCalculationSerializer(serializers.Serializer):
    pickup_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    pickup_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    delivery_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    delivery_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class TransporterAvailabilitySerializer(serializers.Serializer):
    """Serializer for updating transporter availability"""

    is_available = serializers.BooleanField()
    status = serializers.ChoiceField(choices=TransporterStatus.choices, required=False)


class DeliveryProofSerializer(serializers.Serializer):
    """Serializer for delivery proof of delivery"""

    delivery_photo = serializers.ImageField(required=False, allow_null=True)
    signature_image = serializers.ImageField(required=False, allow_null=True)
    delivery_notes = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)


class DeliverySearchSerializer(serializers.Serializer):
    """Serializer for delivery search parameters"""

    search = serializers.CharField(required=False, allow_blank=True)
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    pickup_address = serializers.CharField(required=False, allow_blank=True)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True)
