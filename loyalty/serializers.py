from decimal import Decimal

from rest_framework import serializers

from .models import (
    LoyaltyConfiguration,
    LoyaltyPerk,
    LoyaltyTier,
    LoyaltyTransaction,
    UserLoyalty,
)
from .services import LoyaltyService


class LoyaltyPerkSerializer(serializers.ModelSerializer):
    """Serializer for loyalty perks."""

    class Meta:
        model = LoyaltyPerk
        fields = ["id", "name", "description", "code", "is_active"]
        read_only_fields = ["id"]


class LoyaltyTierSerializer(serializers.ModelSerializer):
    """Serializer for loyalty tiers with nested perks."""

    perks = LoyaltyPerkSerializer(many=True, read_only=True)
    active_perk_count = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = LoyaltyTier
        fields = [
            "id",
            "name",
            "min_points",
            "point_multiplier",
            "description",
            "is_active",
            "perks",
            "active_perk_count",
            "user_count",
        ]
        read_only_fields = ["id"]

    def get_active_perk_count(self, obj):
        """Get count of active perks."""
        return obj.perks.filter(is_active=True).count()

    def get_user_count(self, obj):
        """Get count of users in this tier."""
        return obj.userloyalty_set.filter(is_active=True).count()


class LoyaltyTierMinimalSerializer(serializers.ModelSerializer):
    """Minimal tier serializer for nested use."""

    class Meta:
        model = LoyaltyTier
        fields = ["id", "name", "min_points", "point_multiplier"]
        read_only_fields = ["id"]


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    """Serializer for loyalty transactions."""

    transaction_type_display = serializers.CharField(source="get_transaction_type_display", read_only=True)
    user = serializers.CharField(source="user_loyalty.user.username", read_only=True)

    class Meta:
        model = LoyaltyTransaction
        fields = [
            "id",
            "user",
            "points",
            "transaction_type",
            "transaction_type_display",
            "description",
            "created_at",
            "purchase_id",
            "reference_id",
            "balance_after",
        ]
        read_only_fields = ["id", "created_at", "balance_after"]


class UserLoyaltySerializer(serializers.ModelSerializer):
    """Serializer for user loyalty profile."""

    tier = LoyaltyTierMinimalSerializer(read_only=True)
    tier_name = serializers.CharField(source="tier.name", read_only=True)
    next_tier = serializers.SerializerMethodField()
    perks = serializers.SerializerMethodField()
    points_to_next_tier = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    member_since = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = UserLoyalty
        fields = [
            "id",
            "username",
            "points",
            "lifetime_points",
            "tier",
            "tier_name",
            "next_tier",
            "points_to_next_tier",
            "perks",
            "is_active",
            "member_since",
            "tier_updated_at",
        ]
        read_only_fields = ["id", "points", "lifetime_points", "tier", "member_since", "tier_updated_at"]

    def get_next_tier(self, obj):
        """Get information about the next tier."""
        if not obj.tier:
            # User has no tier, get the first tier
            next_tier = LoyaltyTier.objects.filter(is_active=True).order_by("min_points").first()
        else:
            # Get next tier above current
            next_tier = (
                LoyaltyTier.objects.filter(min_points__gt=obj.tier.min_points, is_active=True).order_by("min_points").first()
            )

        if next_tier:
            return {
                "id": next_tier.id,
                "name": next_tier.name,
                "min_points": next_tier.min_points,
                "points_required": next_tier.min_points - obj.lifetime_points,
                "point_multiplier": float(next_tier.point_multiplier),
            }
        return None

    def get_points_to_next_tier(self, obj):
        """Calculate points needed for next tier."""
        return obj.get_points_to_next_tier()

    def get_perks(self, obj):
        """Get all available perks for user's tier."""
        perks = LoyaltyService.get_user_perks(obj.user)
        return LoyaltyPerkSerializer(perks, many=True).data


class UserLoyaltySummarySerializer(serializers.Serializer):
    """Comprehensive summary of user's loyalty status."""

    has_profile = serializers.BooleanField()
    is_active = serializers.BooleanField(required=False)
    points = serializers.IntegerField()
    lifetime_points = serializers.IntegerField()
    tier = serializers.CharField(allow_null=True)
    tier_multiplier = serializers.FloatField()
    perks = serializers.ListField()
    points_to_next_tier = serializers.IntegerField(allow_null=True)
    transaction_count = serializers.IntegerField()
    member_since = serializers.DateTimeField(allow_null=True)


class RedeemPointsSerializer(serializers.Serializer):
    """Serializer for point redemption requests."""

    points = serializers.IntegerField(min_value=1)
    description = serializers.CharField(max_length=255)
    reference_id = serializers.CharField(max_length=100, required=False, allow_null=True)

    def validate_points(self, value):
        """Validate points is positive."""
        if value <= 0:
            raise serializers.ValidationError("Points must be greater than 0")

        # Check against configuration
        config = LoyaltyConfiguration.get_config()
        if value < config.min_redemption_points:
            raise serializers.ValidationError(f"Minimum redemption is {config.min_redemption_points} points")

        if config.max_redemption_points and value > config.max_redemption_points:
            raise serializers.ValidationError(f"Maximum redemption is {config.max_redemption_points} points")

        return value


class AwardPointsSerializer(serializers.Serializer):
    """Serializer for awarding points (admin use)."""

    user_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField(max_length=255)
    purchase_id = serializers.CharField(max_length=100, required=False, allow_null=True)
    reference_id = serializers.CharField(max_length=100, required=False, allow_null=True)
    transaction_type = serializers.ChoiceField(choices=["earn", "bonus"], default="earn")

    def validate_amount(self, value):
        """Validate amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value


class AdminAdjustPointsSerializer(serializers.Serializer):
    """Serializer for admin point adjustments."""

    user_id = serializers.IntegerField()
    points = serializers.IntegerField()
    description = serializers.CharField(max_length=255)
    affect_lifetime = serializers.BooleanField(default=False)
    reference_id = serializers.CharField(max_length=100, required=False, allow_null=True)

    def validate_points(self, value):
        """Validate points is not zero."""
        if value == 0:
            raise serializers.ValidationError("Points adjustment cannot be zero")
        return value


class LoyaltyConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for loyalty configuration."""

    class Meta:
        model = LoyaltyConfiguration
        fields = [
            "points_per_unit",
            "unit_amount",
            "points_expiry_days",
            "min_redemption_points",
            "max_redemption_points",
            "allow_negative_balance",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_unit_amount(self, value):
        """Ensure unit amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Unit amount must be greater than 0")
        return value

    def validate(self, data):
        """Cross-field validation."""
        min_redemption = data.get("min_redemption_points")
        max_redemption = data.get("max_redemption_points")

        if min_redemption and max_redemption:
            if min_redemption > max_redemption:
                raise serializers.ValidationError("Minimum redemption cannot be greater than maximum redemption")

        return data


class TransactionHistorySerializer(serializers.Serializer):
    """Serializer for transaction history with pagination."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LoyaltyTransactionSerializer(many=True)


class LoyaltyStatisticsSerializer(serializers.Serializer):
    """Serializer for loyalty program statistics."""

    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    total_points_issued = serializers.IntegerField()
    total_points_redeemed = serializers.IntegerField()
    total_points_outstanding = serializers.IntegerField()

    tier_distribution = serializers.DictField()
    recent_transactions = LoyaltyTransactionSerializer(many=True)
