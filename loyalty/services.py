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
    Features: Request-caching, Bulk Expiry, and Atomic Integrity.
    """

    @cached_property
    def config(self) -> LoyaltyConfiguration:
        """Cache configuration for the duration of the request/service instance."""
        return LoyaltyConfiguration.get_config()

    def _validate_amount(self, amount: Union[Decimal, int, float]) -> Decimal:
        try:
            amount_decimal = Decimal(str(amount))
        except (ValueError, TypeError) as e:
            raise InvalidTransactionError(f"Invalid amount: {amount}") from e
        if amount_decimal < 0:
            raise InvalidTransactionError("Amount cannot be negative")
        return amount_decimal

    def _calculate_points(self, amount: Decimal, multiplier: Decimal = Decimal("1.00")) -> int:
        conf = self.config
        if conf.unit_amount <= 0:
            raise InvalidTransactionError("Invalid unit_amount configuration")

        # Atomic calculation: (Amount / Unit) * PointsPerUnit * Multiplier
        base_points = (amount / conf.unit_amount) * Decimal(conf.points_per_unit)
        final_points = (base_points * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(final_points)

    def _get_or_create_locked_profile(self, user) -> UserLoyalty:
        """Thread-safe acquisition of the loyalty profile."""
        profile, created = UserLoyalty.objects.get_or_create(user=user, defaults={"is_active": True})
        return UserLoyalty.objects.select_for_update().get(pk=profile.pk)

    @transaction.atomic
    def award_points(
        self, user, amount: Union[Decimal, int, float], description: str, reference_id: Optional[str] = None, **kwargs
    ) -> Tuple[int, LoyaltyTransaction]:

        amount_decimal = self._validate_amount(amount)
        if amount_decimal == 0:
            raise InvalidTransactionError("Cannot award points for zero amount")

        # Idempotency Check
        if reference_id and LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            raise DuplicateTransactionError(f"Ref {reference_id} already processed.")

        profile = self._get_or_create_locked_profile(user)
        if not profile.is_active:
            raise InvalidTransactionError("Profile inactive")

        multiplier = profile.tier.point_multiplier if (profile.tier and profile.tier.is_active) else Decimal("1.00")
        points = self._calculate_points(amount_decimal, multiplier)

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

    @transaction.atomic
    def redeem_points(
        self, user, points: int, description: str, reference_id: Optional[str] = None, **kwargs
    ) -> Tuple[bool, str, Optional[LoyaltyTransaction]]:

        if points <= 0:
            return False, "Points must be positive", None

        conf = self.config
        if points < conf.min_redemption_points:
            return False, f"Min redemption is {conf.min_redemption_points}", None

        if reference_id and LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            return False, "Duplicate transaction", None

        profile = self._get_or_create_locked_profile(user)

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

    def expire_old_points(self) -> int:
        """
        High-performance bulk expiry.
        Uses a 'Sweep and Aggregate' approach to avoid N+1 queries.
        """
        days = self.config.points_expiry_days
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

    def get_user_summary(self, user) -> dict:
        """Optimized summary using select_related to reduce SQL hits."""
        profile = UserLoyalty.objects.select_related("tier").filter(user=user).first()
        if not profile:
            return {"points": 0, "tier": "None"}

        return {
            "points": profile.points,
            "tier": profile.tier.name if profile.tier else "Standard",
            "next_tier_progress": profile.get_points_to_next_tier(),
            "is_active": profile.is_active,
        }
