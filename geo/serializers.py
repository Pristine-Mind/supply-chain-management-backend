from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import GeographicZone, SaleRegion, UserLocationSnapshot


class LocationInputSerializer(serializers.Serializer):
    """
    Input validation for user location coordinates.

    Usage:
        serializer = LocationInputSerializer(data={
            'latitude': 27.7172,
            'longitude': 85.3240
        })
    """

    latitude = serializers.FloatField(min_value=-90, max_value=90, required=True, help_text=_("Latitude (-90 to 90)"))
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=True, help_text=_("Longitude (-180 to 180)"))
    accuracy_meters = serializers.IntegerField(required=False, allow_null=True, help_text=_("GPS accuracy in meters"))
    session_id = serializers.CharField(
        max_length=100, required=False, allow_blank=True, help_text=_("Optional session identifier")
    )


class GeographicZoneSerializer(serializers.ModelSerializer):
    """
    Full geographic zone serializer.
    """

    delivery_tier_display = serializers.CharField(source="get_tier_display", read_only=True)

    class Meta:
        model = GeographicZone
        fields = [
            "id",
            "name",
            "description",
            "tier",
            "delivery_tier_display",
            "shipping_cost",
            "estimated_delivery_days",
            "radius_km",
            "center_latitude",
            "center_longitude",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class GeographicZoneBriefSerializer(serializers.ModelSerializer):
    """
    Brief geographic zone serializer (for nested use).
    """

    class Meta:
        model = GeographicZone
        fields = ["id", "name", "tier", "shipping_cost", "estimated_delivery_days"]


class UserLocationSnapshotSerializer(serializers.ModelSerializer):
    """
    User location snapshot with zone info.
    """

    zone = GeographicZoneBriefSerializer(read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True, allow_null=True)

    class Meta:
        model = UserLocationSnapshot
        fields = [
            "id",
            "latitude",
            "longitude",
            "zone",
            "zone_name",
            "accuracy_meters",
            "session_id",
            "created_at",
        ]
        read_only_fields = ["id", "zone", "zone_name", "created_at"]


class SaleRegionSerializer(serializers.ModelSerializer):
    """
    Sale region with associated zone.
    """

    zone = GeographicZoneBriefSerializer(read_only=True)

    class Meta:
        model = SaleRegion
        fields = [
            "id",
            "name",
            "zone",
            "is_restricted",
            "allowed_countries",
            "allowed_cities",
            "is_active",
        ]
        read_only_fields = ["id"]


class DeliverabilityCheckSerializer(serializers.Serializer):
    """
    Validate product deliverability to location.
    Input/Output for deliverability checks.

    Usage:
        serializer = DeliverabilityCheckSerializer(data={
            'product_id': 123,
            'latitude': 27.7172,
            'longitude': 85.3240,
        })
    """

    product_id = serializers.IntegerField(required=True, help_text=_("MarketplaceProduct ID"))
    latitude = serializers.FloatField(min_value=-90, max_value=90, required=True)
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=True)

    # Output fields
    is_deliverable = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True, allow_null=True)
    estimated_days = serializers.IntegerField(read_only=True)
    shipping_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    zone = serializers.CharField(read_only=True, allow_null=True)


class UserZoneDetectionSerializer(serializers.Serializer):
    """
    Detect user's geographic zone from coordinates.

    Usage:
        serializer = UserZoneDetectionSerializer(data={
            'latitude': 27.7172,
            'longitude': 85.3240,
        })
    """

    latitude = serializers.FloatField(min_value=-90, max_value=90, required=True)
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=True)

    # Output
    zone = GeographicZoneBriefSerializer(read_only=True)
    nearby_zones = serializers.SerializerMethodField(read_only=True)

    def get_nearby_zones(self, obj):
        """Get nearby zones within 50km"""
        return []  # Handled in view


class DeliveryEstimateSerializer(serializers.Serializer):
    """
    Estimated delivery info for product.
    """

    product_id = serializers.IntegerField()
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)

    # Output
    estimated_days = serializers.IntegerField(read_only=True)
    shipping_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    zone = serializers.CharField(read_only=True, allow_null=True)
    is_same_day = serializers.BooleanField(read_only=True)


class LocationFilterSerializer(serializers.Serializer):
    """
    Filter products by location proximity and availability.

    Usage:
        Can be used to batch-filter multiple products
    """

    latitude = serializers.FloatField(min_value=-90, max_value=90, required=True, help_text=_("User's latitude"))
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=True, help_text=_("User's longitude"))
    max_distance_km = serializers.IntegerField(
        required=False, default=100, help_text=_("Filter products within this distance")
    )
    zones = serializers.ListField(
        child=serializers.IntegerField(), required=False, help_text=_("Filter by specific zone IDs")
    )

    # Output - will be populated in view
    deliverable_products = serializers.SerializerMethodField(read_only=True)

    def get_deliverable_products(self, obj):
        """Populated by view"""
        return []
