import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Tuple, Union

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.functional import cached_property

from .models import LoyaltyConfiguration, LoyaltyTransaction, UserLoyalty

logger = logging.getLogger(__name__)


class LoyaltyError(Exception):
    pass


class InsufficientPointsError(LoyaltyError):
    pass


class InvalidTransactionError(LoyaltyError):
    pass


class DuplicateTransactionError(LoyaltyError):
    pass


class LoyaltyService:
    """
    Optimized Service for handling loyalty operations.
    Converted to static methods for direct access without instantiation.
    """

    @staticmethod
    def _validate_amount(amount: Union[Decimal, int, float]) -> Decimal:
        try:
            amount_decimal = Decimal(str(amount))
        except (ValueError, TypeError) as e:
            raise InvalidTransactionError(f"Invalid amount: {amount}") from e
        if amount_decimal < 0:
            raise InvalidTransactionError("Amount cannot be negative")
        return amount_decimal

    @staticmethod
    def _calculate_points(amount: Decimal, multiplier: Decimal = Decimal("1.00")) -> int:
        conf = LoyaltyConfiguration.get_config()
        if conf.unit_amount <= 0:
            raise InvalidTransactionError("Invalid unit_amount configuration")

        # Atomic calculation: (Amount / Unit) * PointsPerUnit * Multiplier
        base_points = (amount / conf.unit_amount) * Decimal(conf.points_per_unit)
        final_points = (base_points * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(final_points)

    @staticmethod
    def _get_or_create_locked_profile(user) -> UserLoyalty:
        """Thread-safe acquisition of the loyalty profile."""
        profile, created = UserLoyalty.objects.get_or_create(user=user, defaults={"is_active": True})
        return UserLoyalty.objects.select_for_update().get(pk=profile.pk)

    @staticmethod
    @transaction.atomic
    def award_points(
        user, amount: Union[Decimal, int, float], description: str, reference_id: Optional[str] = None, **kwargs
    ) -> Tuple[int, LoyaltyTransaction]:

        amount_decimal = LoyaltyService._validate_amount(amount)
        if amount_decimal == 0:
            raise InvalidTransactionError("Cannot award points for zero amount")

        # Idempotency Check
        if reference_id and LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            raise DuplicateTransactionError(f"Ref {reference_id} already processed.")

        profile = LoyaltyService._get_or_create_locked_profile(user)
        if not profile.is_active:
            raise InvalidTransactionError("Profile inactive")

        multiplier = profile.tier.point_multiplier if (profile.tier and profile.tier.is_active) else Decimal("1.00")
        points = LoyaltyService._calculate_points(amount_decimal, multiplier)

        UserLoyalty.objects.filter(pk=profile.pk).update(
            points=F("points") + points, lifetime_points=F("lifetime_points") + points
        )
        profile.refresh_from_db()

        txn = LoyaltyTransaction.objects.create(
            user_loyalty=profile,
            points=points,
            transaction_type="earn",
            description=description,
            reference_id=reference_id,
            balance_after=profile.points,
            **kwargs,
        )

        profile.update_tier()
        return points, txn

    @staticmethod
    @transaction.atomic
    def redeem_points(
        user, points: int, description: str, reference_id: Optional[str] = None, **kwargs
    ) -> Tuple[bool, str, Optional[LoyaltyTransaction]]:

        if points <= 0:
            return False, "Points must be positive", None

        conf = LoyaltyConfiguration.get_config()
        if points < conf.min_redemption_points:
            return False, f"Min redemption is {conf.min_redemption_points}", None

        if reference_id and LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            return False, "Duplicate transaction", None

        profile = LoyaltyService._get_or_create_locked_profile(user)

        if profile.points < points:
            return False, "Insufficient balance", None

        UserLoyalty.objects.filter(pk=profile.pk).update(points=F("points") - points)
        profile.refresh_from_db()

        txn = LoyaltyTransaction.objects.create(
            user_loyalty=profile,
            points=-points,
            transaction_type="redeem",
            description=description,
            reference_id=reference_id,
            balance_after=profile.points,
            **kwargs,
        )
        return True, "Success", txn

    @staticmethod
    def expire_old_points(days_override: Optional[int] = None) -> int:
        """
        High-performance bulk expiry.
        Uses a 'Sweep and Aggregate' approach to avoid N+1 queries.
        """
        config = LoyaltyConfiguration.get_config()
        days = days_override or config.points_expiry_days
        if not days:
            return 0

        cutoff = timezone.now() - timezone.timedelta(days=days)

        expired_refs = LoyaltyTransaction.objects.filter(transaction_type="expire").values_list("reference_id", flat=True)

        to_expire = (
            LoyaltyTransaction.objects.filter(transaction_type="earn", created_at__lt=cutoff)
            .exclude(reference_id__in=expired_refs)
            .values("user_loyalty")
            .annotate(total_to_expire=Sum("points"))
        )

        processed_count = 0
        for entry in to_expire:
            with transaction.atomic():
                profile = UserLoyalty.objects.select_for_update().get(pk=entry["user_loyalty"])
                points_deducted = min(profile.points, entry["total_to_expire"])

                if points_deducted > 0:
                    UserLoyalty.objects.filter(pk=profile.pk).update(points=F("points") - points_deducted)
                    profile.refresh_from_db()

                    LoyaltyTransaction.objects.create(
                        user_loyalty=profile,
                        points=-points_deducted,
                        transaction_type="expire",
                        description="Bulk expiry",
                        balance_after=profile.points,
                    )
                    processed_count += 1
        return processed_count

    @staticmethod
    def get_user_perks(user):
        """Get all active perks for a user."""
        profile = UserLoyalty.objects.select_related("tier").filter(user=user).first()
        if not profile or not profile.tier:
            return []
        return profile.tier.perks.filter(is_active=True)

    @staticmethod
    def get_user_summary(user) -> dict:
        """Optimized summary using select_related and prefetch_related."""
        profile = (
            UserLoyalty.objects.select_related("tier")
            .prefetch_related("tier__perks")
            .filter(user=user)
            .first()
        )

        if not profile:
            return {
                "has_profile": False,
                "is_active": False,
                "points": 0,
                "lifetime_points": 0,
                "tier": "Standard",
                "tier_multiplier": 1.0,
                "perks": [],
                "points_to_next_tier": None,
                "transaction_count": 0,
                "member_since": None,
            }

        return {
            "has_profile": True,
            "is_active": profile.is_active,
            "points": profile.points,
            "lifetime_points": profile.lifetime_points,
            "tier": profile.tier.name if profile.tier else "Standard",
            "tier_multiplier": float(profile.tier.point_multiplier) if profile.tier else 1.0,
            "perks": [
                {"name": perk.name, "description": perk.description, "code": perk.code}
                for perk in (profile.tier.perks.filter(is_active=True) if profile.tier else [])
            ],
            "points_to_next_tier": profile.get_points_to_next_tier(),
            "transaction_count": profile.transactions.count(),
            "member_since": profile.created_at,
        }
