import logging
from typing import Any, Dict, List

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.utils import timezone

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationTemplate,
    UserNotificationPreference,
)
from .services import DeliveryStatusTracker, NotificationServiceFactory

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_notification_task(self, notification_id: str):
    """Send a single notification"""
    try:
        notification = Notification.objects.get(id=notification_id)

        # Check if notification is still pending
        if notification.status != "pending":
            logger.info(f"Notification {notification_id} already processed with status: {notification.status}")
            return

        # Check if it's time to send
        if notification.scheduled_at > timezone.now():
            logger.info(f"Notification {notification_id} not yet scheduled")
            return

        # Send notification
        success = NotificationServiceFactory.send_notification(notification)

        if success:
            logger.info(f"Successfully sent notification {notification_id}")
            return f"Notification {notification_id} sent successfully"
        else:
            logger.error(f"Failed to send notification {notification_id}")
            return f"Failed to send notification {notification_id}"

    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return f"Notification {notification_id} not found"
    except Exception as e:
        logger.error(f"Error sending notification {notification_id}: {e}")
        # Retry the task
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2**self.request.retries))
        return f"Failed to send notification {notification_id} after {self.max_retries} retries"


@shared_task
def send_delayed_notification_task(notification_id: str):
    """Send a delayed notification"""
    return send_notification_task(notification_id)


@shared_task(bind=True, max_retries=2)
def process_notification_batch_task(self, batch_id: str):
    """Process a batch of notifications"""
    try:
        batch = NotificationBatch.objects.get(id=batch_id)

        if batch.status != "pending":
            logger.info(f"Batch {batch_id} already processed with status: {batch.status}")
            return

        # Update batch status
        batch.status = "processing"
        batch.started_at = timezone.now()
        batch.save()

        # Get target users
        target_users = batch.target_users.all()
        batch.total_count = target_users.count()
        batch.save()

        logger.info(f"Processing batch {batch_id} with {batch.total_count} users")

        # Create notifications for each user
        notifications_created = []

        for user in target_users:
            try:
                # Check user preferences
                try:
                    preferences = user.notification_preferences
                except UserNotificationPreference.DoesNotExist:
                    preferences = UserNotificationPreference.objects.create(user=user)

                # Skip if user has disabled all notifications
                if not any(
                    [
                        preferences.push_enabled,
                        preferences.email_enabled,
                        preferences.sms_enabled,
                        preferences.in_app_enabled,
                    ]
                ):
                    continue

                # Render template with context data
                try:
                    rendered_content = batch.template.render(batch.context_data)
                except ValueError as e:
                    logger.error(f"Template rendering error for batch {batch_id}, user {user.id}: {e}")
                    continue

                # Determine notification type based on template and user preferences
                notification_type = batch.template.template_type
                if notification_type == "push" and not preferences.push_enabled:
                    notification_type = "in_app"
                elif notification_type == "email" and not preferences.email_enabled:
                    notification_type = "in_app"
                elif notification_type == "sms" and not preferences.sms_enabled:
                    notification_type = "in_app"

                # Create notification
                notification = Notification.objects.create(
                    user=user,
                    notification_type=notification_type,
                    title=rendered_content["title"],
                    body=rendered_content["body"],
                    action_url=rendered_content.get("action_url"),
                    icon_url=rendered_content.get("icon_url"),
                    template=batch.template,
                    event_data=batch.context_data,
                    priority=5,  # Default priority for batch notifications
                    scheduled_at=batch.scheduled_at,
                )

                notifications_created.append(notification.id)

            except Exception as e:
                logger.error(f"Error creating notification for user {user.id} in batch {batch_id}: {e}")
                batch.failed_count += 1

        # Send notifications
        for notification_id in notifications_created:
            send_notification_task.delay(str(notification_id))

        # Update batch status
        batch.sent_count = len(notifications_created)
        batch.status = "completed"
        batch.completed_at = timezone.now()
        batch.save()

        logger.info(f"Batch {batch_id} completed: {batch.sent_count} sent, {batch.failed_count} failed")
        return f"Batch {batch_id} processed: {batch.sent_count} notifications created"

    except NotificationBatch.DoesNotExist:
        logger.error(f"Notification batch {batch_id} not found")
        return f"Batch {batch_id} not found"
    except Exception as e:
        logger.error(f"Error processing batch {batch_id}: {e}")

        # Update batch status to failed
        try:
            batch = NotificationBatch.objects.get(id=batch_id)
            batch.status = "failed"
            batch.save()
        except:
            pass

        # Retry the task
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300)  # Retry after 5 minutes
        return f"Failed to process batch {batch_id} after {self.max_retries} retries"


@shared_task
def retry_failed_notifications_task():
    """Retry failed notifications that can be retried"""
    try:
        # Get failed notifications that can be retried
        failed_notifications = Notification.objects.filter(
            status="failed",
            retry_count__lt=F("max_retries"),
            created_at__gte=timezone.now() - timezone.timedelta(days=1),  # Only retry recent failures
        )

        retry_count = 0
        for notification in failed_notifications:
            if notification.can_retry():
                # Reset status to pending
                notification.status = "pending"
                notification.error_message = ""
                notification.save()

                # Schedule retry
                send_notification_task.delay(str(notification.id))
                retry_count += 1

        logger.info(f"Scheduled {retry_count} notifications for retry")
        return f"Scheduled {retry_count} notifications for retry"

    except Exception as e:
        logger.error(f"Error retrying failed notifications: {e}")
        return f"Error retrying failed notifications: {e}"


@shared_task
def cleanup_old_notifications_task(days: int = 30):
    """Clean up old notifications and events"""
    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days)

        # Delete old notification events
        from .models import NotificationEvent

        events_deleted = NotificationEvent.objects.filter(timestamp__lt=cutoff_date).delete()[0]

        # Delete old notifications (keep important ones)
        notifications_deleted = Notification.objects.filter(
            created_at__lt=cutoff_date, status__in=["delivered", "read", "failed"]
        ).delete()[0]

        logger.info(f"Cleanup completed: {notifications_deleted} notifications, {events_deleted} events deleted")
        return f"Cleanup completed: {notifications_deleted} notifications, {events_deleted} events deleted"

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return f"Error during cleanup: {e}"


@shared_task
def update_device_token_status_task():
    """Update device token status based on delivery failures"""
    try:
        from django.db.models import Count, F

        # Find tokens with high failure rates
        failed_tokens = DeviceToken.objects.annotate(
            failure_count=Count(
                "user__notifications",
                filter=Q(
                    user__notifications__status="failed", user__notifications__error_message__icontains="invalid token"
                ),
            )
        ).filter(failure_count__gte=3, is_active=True)

        deactivated_count = failed_tokens.update(is_active=False)

        logger.info(f"Deactivated {deactivated_count} device tokens with high failure rates")
        return f"Deactivated {deactivated_count} device tokens"

    except Exception as e:
        logger.error(f"Error updating device token status: {e}")
        return f"Error updating device token status: {e}"


@shared_task
def send_scheduled_notifications_task():
    """Send notifications that are scheduled to be sent now"""
    try:
        # Get notifications scheduled to be sent
        scheduled_notifications = Notification.objects.filter(status="pending", scheduled_at__lte=timezone.now()).order_by(
            "priority", "scheduled_at"
        )[
            :100
        ]  # Process in batches

        sent_count = 0
        for notification in scheduled_notifications:
            send_notification_task.delay(str(notification.id))
            sent_count += 1

        logger.info(f"Scheduled {sent_count} notifications for sending")
        return f"Scheduled {sent_count} notifications for sending"

    except Exception as e:
        logger.error(f"Error sending scheduled notifications: {e}")
        return f"Error sending scheduled notifications: {e}"


@shared_task
def generate_notification_analytics_task():
    """Generate notification analytics and reports"""
    try:
        from datetime import timedelta

        from django.db.models import Avg, Count

        # Calculate statistics for the last 7 days
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)

        stats = Notification.objects.filter(created_at__gte=start_date, created_at__lt=end_date).aggregate(
            total_notifications=Count("id"),
            sent_notifications=Count("id", filter=Q(status="sent")),
            delivered_notifications=Count("id", filter=Q(status="delivered")),
            failed_notifications=Count("id", filter=Q(status="failed")),
            read_notifications=Count("id", filter=Q(status="read")),
            avg_delivery_time=Avg("delivered_at") - Avg("sent_at"),
        )

        # Calculate rates
        total = stats["total_notifications"] or 1
        delivery_rate = (stats["delivered_notifications"] / total) * 100
        read_rate = (stats["read_notifications"] / total) * 100
        failure_rate = (stats["failed_notifications"] / total) * 100

        # Log analytics
        logger.info(
            f"Notification Analytics (7 days): "
            f"Total: {total}, "
            f"Delivery Rate: {delivery_rate:.2f}%, "
            f"Read Rate: {read_rate:.2f}%, "
            f"Failure Rate: {failure_rate:.2f}%"
        )

        # You can store these stats in a separate model or send to analytics service

        return {
            "period": "7_days",
            "total_notifications": stats["total_notifications"],
            "delivery_rate": round(delivery_rate, 2),
            "read_rate": round(read_rate, 2),
            "failure_rate": round(failure_rate, 2),
        }

    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        return f"Error generating analytics: {e}"


# Periodic task to process notification queue
@shared_task
def process_notification_queue_task():
    """Process pending notifications in the queue"""
    try:
        # Get high priority pending notifications
        high_priority_notifications = Notification.objects.filter(
            status="pending", scheduled_at__lte=timezone.now(), priority__gte=7
        ).order_by("-priority", "scheduled_at")[:50]

        # Get regular priority notifications
        regular_notifications = Notification.objects.filter(
            status="pending", scheduled_at__lte=timezone.now(), priority__lt=7
        ).order_by("scheduled_at")[:50]

        # Process high priority first
        processed_count = 0
        for notification in high_priority_notifications:
            send_notification_task.delay(str(notification.id))
            processed_count += 1

        # Then process regular notifications
        for notification in regular_notifications:
            send_notification_task.delay(str(notification.id))
            processed_count += 1

        if processed_count > 0:
            logger.info(f"Queued {processed_count} notifications for processing")

        return f"Queued {processed_count} notifications for processing"

    except Exception as e:
        logger.error(f"Error processing notification queue: {e}")
        return f"Error processing notification queue: {e}"
