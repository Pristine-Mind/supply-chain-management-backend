import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import LoyaltyTransaction
from .services import DuplicateTransactionError, InvalidTransactionError, LoyaltyService

logger = logging.getLogger(__name__)


def safe_award_points(user, amount, description, purchase_id=None, reference_id=None):
    try:
        points, trans = LoyaltyService.award_points(
            user=user, amount=amount, description=description, purchase_id=purchase_id, reference_id=reference_id
        )
        logger.info(f"Awarded {points} points to {user.username} - {description}")
        return True, points

    except DuplicateTransactionError as e:
        logger.warning(f"Duplicate transaction prevented: {e}")
        return False, str(e)

    except InvalidTransactionError as e:
        logger.error(f"Invalid transaction: {e}")
        return False, str(e)

    except Exception as e:
        logger.error(f"Error awarding points: {e}", exc_info=True)
        return False, str(e)


@receiver(post_save, sender="market.Payment")
def award_points_on_market_payment(sender, instance, created, **kwargs):
    if instance.status == "completed":
        reference_id = f"market_payment_{instance.id}_{instance.purchase.id}"

        if LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            logger.debug(f"Points already awarded for market payment {instance.id}")
            return

        safe_award_points(
            user=instance.purchase.buyer,
            amount=instance.amount,
            description=f"Points earned from purchase #{instance.purchase.id}",
            purchase_id=str(instance.purchase.id),
            reference_id=reference_id,
        )


@receiver(post_save, sender="payment.PaymentTransaction")
def award_points_on_payment_transaction(sender, instance, created, **kwargs):
    try:
        from payment.models import PaymentTransactionStatus

        if instance.status == PaymentTransactionStatus.COMPLETED:
            reference_id = f"payment_txn_{instance.id}_{instance.order_number}"

            if LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
                logger.debug(f"Points already awarded for payment txn {instance.order_number}")
                return

            safe_award_points(
                user=instance.user,
                amount=instance.total_amount,
                description=f"Points earned from order {instance.order_number}",
                purchase_id=instance.order_number,
                reference_id=reference_id,
            )

    except ImportError:
        logger.warning("payment.models not found, skipping payment transaction signal")


@receiver(post_save, sender="producer.MarketplaceProductReview")
def award_points_on_review(sender, instance, created, **kwargs):
    if created and instance.user:
        reference_id = f"review_{instance.id}"

        if LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            logger.debug(f"Points already awarded for review {instance.id}")
            return

        safe_award_points(
            user=instance.user,
            amount=500,
            description=f"Bonus points for reviewing {instance.product.product.name}",
            reference_id=reference_id,
        )


@receiver(post_save, sender="market.MarketplaceOrder")
def handle_order_cancellation(sender, instance, **kwargs):
    try:
        from market.models import OrderStatus

        if instance.status == OrderStatus.CANCELLED:
            reference_id = f"refund_order_{instance.id}"

            if LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
                logger.debug(f"Points already refunded for order {instance.id}")
                return

            try:
                points_deducted, trans = LoyaltyService.refund_points(
                    user=instance.buyer,
                    amount=instance.total_amount,
                    description=f"Points refunded for cancelled order #{instance.order_number}",
                    purchase_id=str(instance.id),
                    reference_id=reference_id,
                )
                logger.info(
                    f"Refunded {points_deducted} points from {instance.buyer.username} "
                    f"for cancelled order {instance.order_number}"
                )
            except Exception as e:
                logger.error(f"Error refunding points for order {instance.id}: {e}")

    except ImportError:
        logger.warning("market.models not found, skipping order cancellation signal")


@receiver(post_save, sender="auth.User")
def award_signup_bonus(sender, instance, created, **kwargs):
    if created:
        reference_id = f"signup_bonus_{instance.id}"

        if LoyaltyTransaction.objects.filter(reference_id=reference_id).exists():
            logger.debug(f"Signup bonus already awarded for user {instance.id}")
            return

        safe_award_points(
            user=instance, amount=1000, description="Welcome bonus for new user registration", reference_id=reference_id
        )


@receiver(post_save, sender="loyalty.UserLoyalty")
def notify_tier_change(sender, instance, **kwargs):
    if instance.tier_updated_at:
        import datetime

        from django.utils import timezone

        time_diff = timezone.now() - instance.tier_updated_at
        if time_diff < datetime.timedelta(minutes=1):
            tier_name = instance.tier.name if instance.tier else "No Tier"

            logger.info(f"User {instance.user.username} tier changed to {tier_name}")

            try:
                from .tasks import send_tier_upgrade_notification

                send_tier_upgrade_notification.delay(instance.user.id, tier_name)
            except Exception as e:
                logger.error(f"Failed to trigger tier upgrade notification: {e}")
