import logging
from decimal import Decimal

from celery import shared_task
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.utils import timezone

from market.models import MarketplaceSale
from notification.models import Notification
from notification.tasks import send_notification_task

from .models import (
    LoyaltyConfiguration,
    LoyaltyTier,
    LoyaltyTransaction,
    LoyaltyTransactionArchive,
    UserLoyalty,
)
from .services import LoyaltyService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def expire_old_points(self, days_threshold=None):
    try:
        logger.info("Starting points expiry task...")

        users_affected = LoyaltyService.expire_old_points(days_threshold)

        logger.info(f"Points expiry completed. {users_affected} users affected.")

        return {"status": "success", "users_affected": users_affected, "completed_at": timezone.now().isoformat()}
    except Exception as exc:
        logger.error(f"Error expiring points: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def recalculate_all_tiers(self):
    try:
        logger.info("Starting tier recalculation...")

        profiles = UserLoyalty.objects.filter(is_active=True).select_related("user", "tier")

        upgraded = 0
        downgraded = 0
        unchanged = 0
        errors = []

        for profile in profiles:
            try:
                old_tier = profile.tier
                tier_changed = profile.update_tier()

                if tier_changed:
                    profile.refresh_from_db()
                    if old_tier and profile.tier:
                        if profile.tier.min_points > old_tier.min_points:
                            upgraded += 1
                            logger.info(f"User {profile.user.username} upgraded: " f"{old_tier.name} → {profile.tier.name}")
                        else:
                            downgraded += 1
                            logger.info(
                                f"User {profile.user.username} downgraded: " f"{old_tier.name} → {profile.tier.name}"
                            )
                    elif profile.tier:
                        upgraded += 1
                    else:
                        downgraded += 1
                else:
                    unchanged += 1
            except Exception as e:
                logger.error(f"Error updating tier for user {profile.user.username}: {e}")
                errors.append({"user_id": profile.user.id, "username": profile.user.username, "error": str(e)})

        logger.info(
            f"Tier recalculation completed. "
            f"Upgraded: {upgraded}, Downgraded: {downgraded}, Unchanged: {unchanged}, "
            f"Errors: {len(errors)}"
        )

        return {
            "status": "success",
            "upgraded": upgraded,
            "downgraded": downgraded,
            "unchanged": unchanged,
            "total_processed": profiles.count(),
            "errors": errors,
            "completed_at": timezone.now().isoformat(),
        }
    except Exception as exc:
        logger.error(f"Error recalculating tiers: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=300)


@shared_task
def generate_loyalty_report(start_date=None, end_date=None):
    try:
        if start_date:
            start_date = timezone.datetime.fromisoformat(start_date)
        else:
            start_date = timezone.now() - timezone.timedelta(days=30)

        if end_date:
            end_date = timezone.datetime.fromisoformat(end_date)
        else:
            end_date = timezone.now()

        logger.info(f"Generating loyalty report for {start_date} to {end_date}")

        transactions = LoyaltyTransaction.objects.filter(created_at__range=(start_date, end_date))

        earn_stats = transactions.filter(transaction_type__in=["earn", "bonus"]).aggregate(
            count=Count("id"), total=Sum("points")
        )

        redeem_stats = transactions.filter(transaction_type="redeem").aggregate(count=Count("id"), total=Sum("points"))

        expire_stats = transactions.filter(transaction_type="expire").aggregate(count=Count("id"), total=Sum("points"))

        total_users = UserLoyalty.objects.count()
        active_users = UserLoyalty.objects.filter(is_active=True).count()
        users_with_points = UserLoyalty.objects.filter(is_active=True, points__gt=0).count()

        points_stats = UserLoyalty.objects.filter(is_active=True).aggregate(
            total_outstanding=Sum("points"),
            total_lifetime=Sum("lifetime_points"),
            avg_points=Sum("points") / Count("id") if Count("id") > 0 else 0,
        )

        tier_dist = {}
        for tier in LoyaltyTier.objects.filter(is_active=True):
            count = UserLoyalty.objects.filter(tier=tier, is_active=True).count()
            tier_dist[tier.name] = {"count": count, "percentage": (count / active_users * 100) if active_users > 0 else 0}

        top_earners = (
            LoyaltyTransaction.objects.filter(
                created_at__range=(start_date, end_date), transaction_type__in=["earn", "bonus"]
            )
            .values("user_loyalty__user__id", "user_loyalty__user__username")
            .annotate(total_earned=Sum("points"))
            .order_by("-total_earned")[:10]
        )

        top_redeemers = (
            LoyaltyTransaction.objects.filter(created_at__range=(start_date, end_date), transaction_type="redeem")
            .values("user_loyalty__user__id", "user_loyalty__user__username")
            .annotate(total_redeemed=Sum("points"))
            .order_by("total_redeemed")[:10]
        )

        stats = {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "transactions": {
                "total": transactions.count(),
                "earn": {"count": earn_stats["count"] or 0, "total_points": earn_stats["total"] or 0},
                "redeem": {"count": redeem_stats["count"] or 0, "total_points": abs(redeem_stats["total"] or 0)},
                "expire": {"count": expire_stats["count"] or 0, "total_points": abs(expire_stats["total"] or 0)},
            },
            "points": {
                "earned": earn_stats["total"] or 0,
                "redeemed": abs(redeem_stats["total"] or 0),
                "expired": abs(expire_stats["total"] or 0),
                "net_change": (earn_stats["total"] or 0) + (redeem_stats["total"] or 0) + (expire_stats["total"] or 0),
                "total_outstanding": points_stats["total_outstanding"] or 0,
                "total_lifetime": points_stats["total_lifetime"] or 0,
                "average_per_user": float(points_stats["avg_points"] or 0),
            },
            "users": {
                "total": total_users,
                "active": active_users,
                "with_points": users_with_points,
                "percentage_active": (active_users / total_users * 100) if total_users > 0 else 0,
            },
            "tier_distribution": tier_dist,
            "top_earners": list(top_earners),
            "top_redeemers": list(top_redeemers),
            "generated_at": timezone.now().isoformat(),
        }

        logger.info("Generated loyalty report successfully")

        return stats

    except Exception as exc:
        logger.error(f"Error generating report: {exc}", exc_info=True)
        raise


@shared_task(bind=True, max_retries=3)
def award_points_async(self, user_id, amount, description, purchase_id=None, reference_id=None, metadata=None):
    try:
        user = User.objects.get(id=user_id)

        points, transaction = LoyaltyService.award_points(
            user=user,
            amount=Decimal(str(amount)),
            description=description,
            purchase_id=purchase_id,
            reference_id=reference_id,
            metadata=metadata or {},
        )  # type: ignore

        logger.info(f"Awarded {points} points to user {user.username} (async)")

        return {
            "status": "success",
            "user_id": user_id,
            "username": user.username,
            "points_awarded": points,
            "transaction_id": transaction.id,
            "completed_at": timezone.now().isoformat(),
        }
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {"status": "error", "message": f"User {user_id} not found"}
    except Exception as exc:
        logger.error(f"Error awarding points to user {user_id}: {exc}", exc_info=True)
        # Retry after 1 minute
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def refund_points_async(self, user_id, amount, description, purchase_id=None, reference_id=None):
    try:
        user = User.objects.get(id=user_id)

        points_deducted, transaction = LoyaltyService.refund_points(
            user=user,
            amount=Decimal(str(amount)),
            description=description,
            purchase_id=purchase_id,
            reference_id=reference_id,
        )

        logger.info(f"Refunded {points_deducted} points from user {user.username} (async)")

        return {
            "status": "success",
            "user_id": user_id,
            "username": user.username,
            "points_deducted": points_deducted,
            "transaction_id": transaction.id,
            "completed_at": timezone.now().isoformat(),
        }
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {"status": "error", "message": f"User {user_id} not found"}
    except Exception as exc:
        logger.error(f"Error refunding points for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@shared_task
def send_tier_upgrade_notification(user_id, new_tier_name, old_tier_name=None):
    try:
        user = User.objects.get(id=user_id)

        logger.info(f"User {user.username} upgraded to {new_tier_name}")

        # Create in-app notification
        notification = Notification.objects.create(
            user=user,
            notification_type="in_app",
            title=f"Welcome to {new_tier_name}!",
            body=f"Congratulations! You have been upgraded to the {new_tier_name} tier. Enjoy your new perks!",
            action_url="/loyalty/status/",  # Adjust based on frontend routes
        )

        # Trigger sending
        send_notification_task.delay(str(notification.id))

        # Also send email if user has email
        if user.email:
            email_notification = Notification.objects.create(
                user=user,
                notification_type="email",
                title=f"Congratulations! You are now {new_tier_name}",
                body=f"You have been upgraded to {new_tier_name} tier! Check out your new perks in the app.",
            )
            send_notification_task.delay(str(email_notification.id))

        return {"status": "success", "user_id": user_id, "tier": new_tier_name}
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {"status": "error", "message": f"User {user_id} not found"}
    except Exception as exc:
        logger.error(f"Error sending tier notification: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}


@shared_task
def send_points_expiry_warning(days_before=7):
    try:
        config = LoyaltyConfiguration.get_config()

        if not config.points_expiry_days:
            logger.info("Points expiry is disabled, skipping warning task")
            return {"status": "skipped", "message": "Points expiry is disabled"}

        expiry_date = timezone.now() - timezone.timedelta(days=config.points_expiry_days)
        warning_date = expiry_date + timezone.timedelta(days=days_before)

        logger.info(f"Checking for points expiring around {warning_date.date()}")

        expiring_transactions = LoyaltyTransaction.objects.filter(
            transaction_type="earn", created_at__date=warning_date.date()
        ).select_related("user_loyalty__user")

        users_notified = 0
        notification_data = []

        for trans in expiring_transactions:
            expired_ref = f"expire_{trans.id}"
            if not LoyaltyTransaction.objects.filter(reference_id=expired_ref).exists():
                user = trans.user_loyalty.user
                points = trans.points
                expiry_date_str = (trans.created_at + timezone.timedelta(days=config.points_expiry_days)).strftime(
                    "%Y-%m-%d"
                )

                logger.info(f"Warning: {points} points will expire on {expiry_date_str} " f"for user {user.username}")

                notification_data.append(
                    {"user_id": user.id, "username": user.username, "points": points, "expiry_date": expiry_date_str}
                )

                notif = Notification.objects.create(
                    user=user,
                    notification_type="in_app",
                    title=f"{points} Points Expiring Soon!",
                    body=f"Your {points} points will expire on {expiry_date_str}. Use them before they expire!",
                    action_url="/loyalty/transactions/",
                )
                send_notification_task.delay(str(notif.id))

                if user.email:
                    email_notif = Notification.objects.create(
                        user=user,
                        notification_type="email",
                        title=f"{points} Points Expiring Soon!",
                        body=f"Hi {user.username}, your {points} points will expire on {expiry_date_str}. Don't let them go to waste!",
                    )
                    send_notification_task.delay(str(email_notif.id))

                users_notified += 1

        logger.info(f"Sent expiry warnings to {users_notified} users")

        return {
            "status": "success",
            "users_notified": users_notified,
            "days_before_expiry": days_before,
            "notifications": notification_data,
            "completed_at": timezone.now().isoformat(),
        }

    except Exception as exc:
        logger.error(f"Error sending expiry warnings: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}


@shared_task
def cleanup_old_transactions(days_to_keep=730):
    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)

        logger.warning(f"Cleaning up transactions older than {cutoff_date}")

        old_transactions = LoyaltyTransaction.objects.filter(created_at__lt=cutoff_date)

        count = old_transactions.count()

        if count > 0:
            logger.info(f"Archiving {count} old transactions...")

            archive_entries = []
            for trans in old_transactions.select_related("user_loyalty__user"):
                archive_entries.append(
                    LoyaltyTransactionArchive(
                        user_id=trans.user_loyalty.user.id,
                        username=trans.user_loyalty.user.username,
                        points=trans.points,
                        transaction_type=trans.transaction_type,
                        description=trans.description,
                        created_at=trans.created_at,
                        purchase_id=trans.purchase_id,
                        reference_id=trans.reference_id,
                        metadata=trans.metadata,
                        balance_after=trans.balance_after,
                    )
                )

            LoyaltyTransactionArchive.objects.bulk_create(archive_entries)

            old_transactions.delete()

            logger.info(f"Successfully archived and deleted {count} transactions.")

        return {"status": "success", "transactions_archived": count, "cutoff_date": cutoff_date.isoformat()}

    except Exception as exc:
        logger.error(f"Error in cleanup task: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}


@shared_task(bind=True)
def batch_award_points(self, user_point_data):
    try:
        results = {"success": [], "failed": [], "total": len(user_point_data)}

        for item in user_point_data:
            try:
                user = User.objects.get(id=item["user_id"])

                points, transaction = LoyaltyService.award_points(
                    user=user,
                    amount=Decimal(str(item["amount"])),
                    description=item["description"],
                    reference_id=item.get("reference_id"),
                    transaction_type=item.get("transaction_type", "bonus"),
                )  # type: ignore

                results["success"].append({"user_id": user.id, "username": user.username, "points": points})

            except Exception as e:
                logger.error(f"Error awarding points to user {item.get('user_id')}: {e}")
                results["failed"].append({"user_id": item.get("user_id"), "error": str(e)})

        logger.info(f"Batch award completed. " f"Success: {len(results['success'])}, Failed: {len(results['failed'])}")

        return {"status": "completed", "results": results, "completed_at": timezone.now().isoformat()}

    except Exception as exc:
        logger.error(f"Error in batch award: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}


@shared_task
def sync_points_with_orders():
    try:
        logger.info("Starting points sync with orders...")
        from market.models import PaymentStatus

        completed_sales = MarketplaceSale.objects.filter(
            payment_status=PaymentStatus.PAID, created_at__gte=timezone.now() - timezone.timedelta(days=7)
        )

        processed_count = 0
        awarded_count = 0

        for sale in completed_sales:
            processed_count += 1
            ref_id = f"sale_{sale.id}"

            if not LoyaltyTransaction.objects.filter(reference_id=ref_id).exists():
                points = LoyaltyService.award_points(  # type: ignore
                    user=sale.buyer,
                    amount=sale.total_amount,
                    description=f"Sync: Points from sale #{sale.order_number}",
                    purchase_id=str(sale.id),
                    reference_id=ref_id,
                )
                if points > 0:
                    awarded_count += 1
                    logger.info(f"Awarded {points} missing points for sale {sale.order_number}")

        return {
            "status": "success",
            "processed_sales": processed_count,
            "awarded_sales": awarded_count,
            "completed_at": timezone.now().isoformat(),
        }

    except Exception as exc:
        logger.error(f"Error syncing points: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}
