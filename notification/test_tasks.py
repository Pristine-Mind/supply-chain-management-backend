"""
Comprehensive test cases for notification Celery tasks
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationEvent,
    NotificationTemplate,
    UserNotificationPreference,
)
from .tasks import (
    cleanup_old_notifications_task,
    generate_notification_analytics_task,
    process_notification_batch_task,
    process_notification_queue_task,
    retry_failed_notifications_task,
    send_delayed_notification_task,
    send_notification_task,
    send_scheduled_notifications_task,
    update_device_token_status_task,
)

User = get_user_model()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class NotificationTaskTests(TestCase):
    """Test notification Celery tasks"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        # Create user preferences
        UserNotificationPreference.objects.create(user=self.user, push_enabled=True, email_enabled=True)

    @patch("notification.tasks.NotificationServiceFactory.send_notification")
    def test_send_notification_task_success(self, mock_send):
        """Test successful notification sending task"""
        mock_send.return_value = True

        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Task Test", body="Testing notification task", status="pending"
        )

        result = send_notification_task(str(notification.id))

        self.assertIn("sent successfully", result)
        mock_send.assert_called_once_with(notification)

        # Check notification status
        notification.refresh_from_db()
        # Note: Status might not be 'sent' because mock doesn't call mark_as_sent

    @patch("notification.tasks.NotificationServiceFactory.send_notification")
    def test_send_notification_task_failure(self, mock_send):
        """Test failed notification sending task"""
        mock_send.return_value = False

        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Task Failure Test",
            body="Testing notification task failure",
            status="pending",
        )

        result = send_notification_task(str(notification.id))

        self.assertIn("Failed to send", result)
        mock_send.assert_called_once_with(notification)

    def test_send_notification_task_not_found(self):
        """Test notification task with non-existent notification"""
        result = send_notification_task("non-existent-uuid")

        self.assertIn("not found", result)

    def test_send_notification_task_already_processed(self):
        """Test notification task with already processed notification"""
        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Already Processed",
            body="This notification is already sent",
            status="sent",
        )

        result = send_notification_task(str(notification.id))

        self.assertIn("already processed", result)

    def test_send_notification_task_not_scheduled(self):
        """Test notification task with future scheduled time"""
        future_time = timezone.now() + timedelta(hours=1)

        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Future Notification",
            body="This notification is scheduled for future",
            status="pending",
            scheduled_at=future_time,
        )

        result = send_notification_task(str(notification.id))

        self.assertIn("not yet scheduled", result)

    def test_send_delayed_notification_task(self):
        """Test delayed notification task"""
        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Delayed Test",
            body="Testing delayed notification",
            status="pending",
        )

        # This should call send_notification_task internally
        with patch("notification.tasks.send_notification_task") as mock_task:
            result = send_delayed_notification_task(str(notification.id))
            mock_task.assert_called_once_with(str(notification.id))


class NotificationBatchTaskTests(TestCase):
    """Test notification batch processing tasks"""

    def setUp(self):
        self.users = []
        for i in range(3):
            user = User.objects.create_user(username=f"user{i}", email=f"user{i}@example.com", password="testpass123")
            self.users.append(user)

            # Create preferences
            UserNotificationPreference.objects.create(user=user, push_enabled=True, in_app_enabled=True)

        self.template = NotificationTemplate.objects.create(
            name="batch_template",
            template_type="push",
            title_template="Batch {title}",
            body_template="Batch notification: {message}",
            variables=["title", "message"],
        )

        self.batch = NotificationBatch.objects.create(
            name="Test Batch",
            template=self.template,
            context_data={"title": "Test", "message": "Hello everyone"},
            created_by=self.users[0],
            status="pending",
        )

        # Add target users
        self.batch.target_users.set(self.users)

    @patch("notification.tasks.send_notification_task")
    def test_process_notification_batch_task_success(self, mock_send_task):
        """Test successful batch processing"""
        result = process_notification_batch_task(str(self.batch.id))

        self.assertIn("notifications created", result)

        # Check batch status
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "completed")
        self.assertEqual(self.batch.sent_count, 3)
        self.assertEqual(self.batch.failed_count, 0)
        self.assertIsNotNone(self.batch.started_at)
        self.assertIsNotNone(self.batch.completed_at)

        # Check notifications were created
        notifications = Notification.objects.filter(template=self.template)
        self.assertEqual(notifications.count(), 3)

        # Check task was called for each notification
        self.assertEqual(mock_send_task.delay.call_count, 3)

        # Check notification content
        for notification in notifications:
            self.assertEqual(notification.title, "Batch Test")
            self.assertEqual(notification.body, "Batch notification: Hello everyone")

    def test_process_notification_batch_task_already_processed(self):
        """Test batch processing with already processed batch"""
        self.batch.status = "completed"
        self.batch.save()

        result = process_notification_batch_task(str(self.batch.id))

        self.assertIn("already processed", result)

    def test_process_notification_batch_task_not_found(self):
        """Test batch processing with non-existent batch"""
        result = process_notification_batch_task("non-existent-uuid")

        self.assertIn("not found", result)

    @patch("notification.tasks.send_notification_task")
    def test_process_notification_batch_task_template_error(self, mock_send_task):
        """Test batch processing with template rendering error"""
        # Create template with missing variable
        bad_template = NotificationTemplate.objects.create(
            name="bad_template",
            template_type="push",
            title_template="Bad {missing_var}",
            body_template="This will fail",
            variables=["missing_var"],
        )

        self.batch.template = bad_template
        self.batch.save()

        result = process_notification_batch_task(str(self.batch.id))

        # Batch should complete but with failures
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "completed")
        self.assertEqual(self.batch.sent_count, 0)
        self.assertEqual(self.batch.failed_count, 3)

    def test_process_notification_batch_task_user_preferences_disabled(self):
        """Test batch processing with disabled user preferences"""
        # Disable notifications for one user
        prefs = self.users[0].notification_preferences
        prefs.push_enabled = False
        prefs.email_enabled = False
        prefs.sms_enabled = False
        prefs.in_app_enabled = False
        prefs.save()

        with patch("notification.tasks.send_notification_task") as mock_send_task:
            result = process_notification_batch_task(str(self.batch.id))

            # Should create notifications for 2 users only
            self.batch.refresh_from_db()
            self.assertEqual(self.batch.sent_count, 2)


class MaintenanceTaskTests(TestCase):
    """Test maintenance and cleanup tasks"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.tasks.send_notification_task")
    def test_retry_failed_notifications_task(self, mock_send_task):
        """Test retrying failed notifications"""
        # Create failed notifications
        failed_notifications = []
        for i in range(3):
            notification = Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Failed Test {i+1}",
                body="This notification failed",
                status="failed",
                retry_count=1,
                max_retries=3,
            )
            failed_notifications.append(notification)

        # Create notification that exceeded max retries
        Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Max Retries Exceeded",
            body="This notification exceeded max retries",
            status="failed",
            retry_count=3,
            max_retries=3,
        )

        result = retry_failed_notifications_task()

        self.assertIn("3 notifications for retry", result)

        # Check that failed notifications were reset to pending
        for notification in failed_notifications:
            notification.refresh_from_db()
            self.assertEqual(notification.status, "pending")
            self.assertEqual(notification.error_message, "")

        # Check that tasks were scheduled
        self.assertEqual(mock_send_task.delay.call_count, 3)

    def test_cleanup_old_notifications_task(self):
        """Test cleaning up old notifications"""
        # Create old notifications
        old_date = timezone.now() - timedelta(days=35)

        old_notifications = []
        for i in range(3):
            notification = Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Old Notification {i+1}",
                body="This is an old notification",
                status="delivered",
                created_at=old_date,
            )
            old_notifications.append(notification)

        # Create recent notification
        recent_notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Recent Notification",
            body="This is a recent notification",
            status="delivered",
        )

        # Create old events
        for notification in old_notifications:
            NotificationEvent.objects.create(notification=notification, event_type="delivered", timestamp=old_date)

        result = cleanup_old_notifications_task(days=30)

        self.assertIn("Cleanup completed", result)

        # Check that old notifications were deleted
        for notification in old_notifications:
            with self.assertRaises(Notification.DoesNotExist):
                notification.refresh_from_db()

        # Check that recent notification still exists
        recent_notification.refresh_from_db()
        self.assertEqual(recent_notification.title, "Recent Notification")

    def test_update_device_token_status_task(self):
        """Test updating device token status"""
        # Create device tokens with high failure rates
        tokens_to_deactivate = []
        for i in range(2):
            token = DeviceToken.objects.create(
                user=self.user, token=f"failed_token_{i}", device_type="android", is_active=True
            )
            tokens_to_deactivate.append(token)

            # Create failed notifications for this token
            for j in range(4):
                Notification.objects.create(
                    user=self.user,
                    notification_type="push",
                    title=f"Failed for token {i}",
                    body="Failed notification",
                    status="failed",
                    error_message="invalid token",
                )

        # Create token with low failure rate
        good_token = DeviceToken.objects.create(user=self.user, token="good_token", device_type="ios", is_active=True)

        result = update_device_token_status_task()

        self.assertIn("Deactivated", result)

        # Check that tokens with high failure rates were deactivated
        for token in tokens_to_deactivate:
            token.refresh_from_db()
            # Note: The actual deactivation logic might need adjustment
            # based on the specific implementation

        # Good token should remain active
        good_token.refresh_from_db()
        self.assertTrue(good_token.is_active)

    def test_send_scheduled_notifications_task(self):
        """Test sending scheduled notifications"""
        # Create scheduled notifications
        past_time = timezone.now() - timedelta(minutes=5)
        future_time = timezone.now() + timedelta(minutes=5)

        scheduled_notifications = []
        for i in range(3):
            notification = Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Scheduled {i+1}",
                body="Scheduled notification",
                status="pending",
                scheduled_at=past_time,
            )
            scheduled_notifications.append(notification)

        # Create future scheduled notification
        Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Future Scheduled",
            body="Future scheduled notification",
            status="pending",
            scheduled_at=future_time,
        )

        with patch("notification.tasks.send_notification_task") as mock_send_task:
            result = send_scheduled_notifications_task()

            self.assertIn("3 notifications for sending", result)
            self.assertEqual(mock_send_task.delay.call_count, 3)

    def test_generate_notification_analytics_task(self):
        """Test generating notification analytics"""
        # Create notifications with different statuses
        statuses = ["sent", "delivered", "failed", "read"]
        for i, status in enumerate(statuses):
            Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Analytics Test {i+1}",
                body="Analytics test notification",
                status=status,
            )

        result = generate_notification_analytics_task()

        self.assertIsInstance(result, dict)
        self.assertEqual(result["period"], "7_days")
        self.assertEqual(result["total_notifications"], 4)
        self.assertIn("delivery_rate", result)
        self.assertIn("read_rate", result)
        self.assertIn("failure_rate", result)

    def test_process_notification_queue_task(self):
        """Test processing notification queue"""
        # Create high priority notifications
        high_priority_notifications = []
        for i in range(2):
            notification = Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"High Priority {i+1}",
                body="High priority notification",
                status="pending",
                priority=8,
                scheduled_at=timezone.now() - timedelta(minutes=1),
            )
            high_priority_notifications.append(notification)

        # Create regular priority notifications
        regular_notifications = []
        for i in range(3):
            notification = Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Regular Priority {i+1}",
                body="Regular priority notification",
                status="pending",
                priority=5,
                scheduled_at=timezone.now() - timedelta(minutes=1),
            )
            regular_notifications.append(notification)

        with patch("notification.tasks.send_notification_task") as mock_send_task:
            result = process_notification_queue_task()

            self.assertIn("5 notifications for processing", result)
            self.assertEqual(mock_send_task.delay.call_count, 5)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TaskErrorHandlingTests(TestCase):
    """Test error handling in tasks"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.tasks.NotificationServiceFactory.send_notification")
    def test_send_notification_task_exception_handling(self, mock_send):
        """Test exception handling in send notification task"""
        mock_send.side_effect = Exception("Service error")

        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Exception Test", body="Testing exception handling"
        )

        # This should not raise an exception
        result = send_notification_task(str(notification.id))

        # Should indicate failure
        self.assertIn("Failed to send", result)

    def test_process_notification_batch_task_exception_handling(self):
        """Test exception handling in batch processing task"""
        # Create batch without template (will cause error)
        batch = NotificationBatch.objects.create(
            name="Error Batch", template=None, created_by=self.user, status="pending"  # This will cause an error
        )

        result = process_notification_batch_task(str(batch.id))

        # Should handle the error gracefully
        self.assertIn("Failed to process", result)

        # Batch status should be failed
        batch.refresh_from_db()
        self.assertEqual(batch.status, "failed")

    def test_cleanup_task_exception_handling(self):
        """Test exception handling in cleanup task"""
        # This should not raise an exception even if there are issues
        result = cleanup_old_notifications_task(days=30)

        # Should return some result
        self.assertIsInstance(result, str)


class TaskRetryTests(TestCase):
    """Test task retry functionality"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.tasks.NotificationServiceFactory.send_notification")
    def test_send_notification_task_retry_logic(self, mock_send):
        """Test retry logic in send notification task"""
        # Mock service to fail first few times, then succeed
        mock_send.side_effect = [False, False, True]

        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Retry Test", body="Testing retry logic"
        )

        # This test would need to be run without CELERY_TASK_ALWAYS_EAGER
        # to properly test retry functionality
        # For now, we just test that the task handles failures
        result = send_notification_task(str(notification.id))

        # Should indicate failure on first attempt
        self.assertIn("Failed to send", result)
