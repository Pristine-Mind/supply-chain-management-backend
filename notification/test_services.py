"""
Comprehensive test cases for notification services
"""

import json
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    DeviceToken,
    Notification,
    NotificationEvent,
    NotificationTemplate,
    UserNotificationPreference,
)
from .services import (
    APNSService,
    DeliveryStatusTracker,
    EmailNotificationService,
    FCMService,
    NotificationServiceFactory,
    SMSNotificationService,
)

User = get_user_model()


class FCMServiceTests(TestCase):
    """Test FCM (Firebase Cloud Messaging) service"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        # Create device tokens
        self.android_token = DeviceToken.objects.create(
            user=self.user, token="android_fcm_token_123", device_type="android", device_id="android_device_1"
        )

        self.ios_token = DeviceToken.objects.create(
            user=self.user, token="ios_fcm_token_456", device_type="ios", device_id="ios_device_1"
        )

        self.web_token = DeviceToken.objects.create(
            user=self.user, token="web_fcm_token_789", device_type="web", device_id="web_browser_1"
        )

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_fcm_service_initialization(self, mock_init_app, mock_send):
        """Test FCM service initialization"""
        service = FCMService()
        self.assertIsInstance(service, FCMService)
        mock_init_app.assert_called_once()

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_send_notification_success(self, mock_init_app, mock_send):
        """Test successful notification sending"""
        mock_send.return_value = "message_id_123"

        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Test FCM Notification",
            body="This is a test FCM notification",
            action_url="https://example.com/action",
            icon_url="https://example.com/icon.png",
            priority=8,
        )

        service = FCMService()
        result = service.send_notification(notification)

        self.assertTrue(result)
        self.assertEqual(mock_send.call_count, 3)  # Called for each device token

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "sent")
        self.assertIsNotNone(notification.sent_at)

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_send_notification_no_tokens(self, mock_init_app, mock_send):
        """Test notification sending with no device tokens"""
        # Create user without device tokens
        user_no_tokens = User.objects.create_user(username="notokens", email="notokens@example.com", password="testpass123")

        notification = Notification.objects.create(
            user=user_no_tokens, notification_type="push", title="Test No Tokens", body="This should fail - no tokens"
        )

        service = FCMService()
        result = service.send_notification(notification)

        self.assertFalse(result)
        mock_send.assert_not_called()

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "failed")
        self.assertIn("No device tokens", notification.error_message)

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_send_notification_invalid_token(self, mock_init_app, mock_send):
        """Test notification sending with invalid token"""
        from firebase_admin import messaging
        from firebase_admin.exceptions import FirebaseError

        # Mock UnregisteredError for invalid token
        mock_send.side_effect = messaging.UnregisteredError("Invalid token")

        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Test Invalid Token", body="This should handle invalid token"
        )

        service = FCMService()
        result = service.send_notification(notification)

        self.assertFalse(result)

        # Check that invalid tokens are marked as inactive
        self.android_token.refresh_from_db()
        self.assertFalse(self.android_token.is_active)

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_send_bulk_notifications(self, mock_init_app, mock_send):
        """Test bulk notification sending"""
        mock_send.return_value = "message_id_bulk"

        notifications = []
        for i in range(3):
            notification = Notification.objects.create(
                user=self.user, notification_type="push", title=f"Bulk Test {i+1}", body=f"Bulk notification {i+1}"
            )
            notifications.append(notification)

        service = FCMService()
        result = service.send_bulk_notifications(notifications)

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 3)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["errors"]), 0)

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_notification_with_custom_data(self, mock_init_app, mock_send):
        """Test notification with custom event data"""
        mock_send.return_value = "message_id_custom"

        custom_data = {"order_id": 12345, "customer_name": "John Doe", "total_amount": 1500.0}

        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Order Confirmed",
            body="Your order has been confirmed",
            event_data=custom_data,
        )

        service = FCMService()
        result = service.send_notification(notification)

        self.assertTrue(result)

        # Verify the message data includes custom data
        call_args = mock_send.call_args_list[0][0][0]  # First call, first argument (message)
        message_data = call_args.data

        self.assertIn("order_id", message_data)
        self.assertEqual(message_data["order_id"], "12345")


class EmailNotificationServiceTests(TestCase):
    """Test email notification service"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_send_email_notification_success(self):
        """Test successful email notification sending"""
        notification = Notification.objects.create(
            user=self.user,
            notification_type="email",
            title="Test Email Notification",
            body="This is a test email notification",
        )

        service = EmailNotificationService()
        result = service.send_notification(notification)

        self.assertTrue(result)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "sent")

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Test Email Notification")
        self.assertEqual(mail.outbox[0].to, ["test@example.com"])

    def test_send_email_notification_no_email(self):
        """Test email notification with user having no email"""
        user_no_email = User.objects.create_user(username="noemail", password="testpass123")

        notification = Notification.objects.create(
            user=user_no_email, notification_type="email", title="Test No Email", body="This should fail - no email"
        )

        service = EmailNotificationService()
        result = service.send_notification(notification)

        self.assertFalse(result)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "failed")
        self.assertIn("no email address", notification.error_message)

    def test_send_bulk_email_notifications(self):
        """Test bulk email notification sending"""
        users = []
        notifications = []

        for i in range(3):
            user = User.objects.create_user(username=f"user{i}", email=f"user{i}@example.com", password="testpass123")
            users.append(user)

            notification = Notification.objects.create(
                user=user, notification_type="email", title=f"Bulk Email {i+1}", body=f"Bulk email notification {i+1}"
            )
            notifications.append(notification)

        service = EmailNotificationService()
        result = service.send_bulk_notifications(notifications)

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 3)
        self.assertEqual(result["failed"], 0)

        # Check that all emails were sent
        self.assertEqual(len(mail.outbox), 3)


class SMSNotificationServiceTests(TestCase):
    """Test SMS notification service"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        # Mock phone number attribute
        self.user.phone_number = "+9779800000001"
        self.user.save()

    @patch("notification.services.requests.post")
    @override_settings(
        SPARROWSMS_API_KEY="test_api_key", SPARROWSMS_SENDER_ID="TEST", SPARROWSMS_ENDPOINT="https://api.test.com/sms/"
    )
    def test_send_sms_notification_success(self, mock_post):
        """Test successful SMS notification sending"""
        # Mock successful SMS API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response_code": "200", "id": "sms_123456"}
        mock_post.return_value = mock_response

        notification = Notification.objects.create(
            user=self.user, notification_type="sms", title="Test SMS", body="This is a test SMS notification"
        )

        service = SMSNotificationService()
        result = service.send_notification(notification)

        self.assertTrue(result)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "sent")

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("token", call_args[1]["data"])
        self.assertIn("to", call_args[1]["data"])
        self.assertEqual(call_args[1]["data"]["to"], "+9779800000001")

    @patch("notification.services.requests.post")
    def test_send_sms_notification_no_phone(self, mock_post):
        """Test SMS notification with user having no phone number"""
        user_no_phone = User.objects.create_user(username="nophone", email="nophone@example.com", password="testpass123")

        notification = Notification.objects.create(
            user=user_no_phone, notification_type="sms", title="Test No Phone", body="This should fail - no phone"
        )

        service = SMSNotificationService()
        result = service.send_notification(notification)

        self.assertFalse(result)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "failed")
        self.assertIn("no phone number", notification.error_message)

        # Verify API was not called
        mock_post.assert_not_called()

    @patch("notification.services.requests.post")
    def test_send_sms_notification_api_error(self, mock_post):
        """Test SMS notification with API error"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response_code": "400", "error_message": "Invalid phone number"}
        mock_post.return_value = mock_response

        notification = Notification.objects.create(
            user=self.user, notification_type="sms", title="Test SMS Error", body="This should fail - API error"
        )

        service = SMSNotificationService()
        result = service.send_notification(notification)

        self.assertFalse(result)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "failed")
        self.assertIn("Invalid phone number", notification.error_message)


class APNSServiceTests(TestCase):
    """Test APNS (Apple Push Notification Service)"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.services.FCMService.send_notification")
    def test_apns_service_delegates_to_fcm(self, mock_fcm_send):
        """Test that APNS service delegates to FCM service"""
        mock_fcm_send.return_value = True

        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Test APNS", body="This is a test APNS notification"
        )

        service = APNSService()
        result = service.send_notification(notification)

        self.assertTrue(result)
        mock_fcm_send.assert_called_once_with(notification)


class NotificationServiceFactoryTests(TestCase):
    """Test notification service factory"""

    def test_get_push_service(self):
        """Test getting push notification service"""
        service = NotificationServiceFactory.get_service("push")
        self.assertIsInstance(service, FCMService)

    def test_get_email_service(self):
        """Test getting email notification service"""
        service = NotificationServiceFactory.get_service("email")
        self.assertIsInstance(service, EmailNotificationService)

    def test_get_sms_service(self):
        """Test getting SMS notification service"""
        service = NotificationServiceFactory.get_service("sms")
        self.assertIsInstance(service, SMSNotificationService)

    def test_get_invalid_service(self):
        """Test getting invalid notification service"""
        service = NotificationServiceFactory.get_service("invalid")
        self.assertIsNone(service)

    def test_get_in_app_service(self):
        """Test getting in-app notification service (not implemented)"""
        service = NotificationServiceFactory.get_service("in_app")
        self.assertIsNone(service)

    @patch("notification.services.FCMService.send_notification")
    def test_send_notification_via_factory(self, mock_send):
        """Test sending notification via factory"""
        mock_send.return_value = True

        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        notification = Notification.objects.create(
            user=user, notification_type="push", title="Factory Test", body="Testing factory pattern"
        )

        result = NotificationServiceFactory.send_notification(notification)

        self.assertTrue(result)
        mock_send.assert_called_once_with(notification)

    def test_send_notification_invalid_type(self):
        """Test sending notification with invalid type"""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        notification = Notification.objects.create(
            user=user, notification_type="invalid", title="Invalid Test", body="Testing invalid type"
        )

        result = NotificationServiceFactory.send_notification(notification)

        self.assertFalse(result)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "failed")
        self.assertIn("No service available", notification.error_message)


class DeliveryStatusTrackerTests(TestCase):
    """Test delivery status tracker"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        self.notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Status Test", body="Testing status tracking", status="sent"
        )

    def test_update_delivery_status_delivered(self):
        """Test updating notification status to delivered"""
        DeliveryStatusTracker.update_delivery_status(
            str(self.notification.id), "delivered", {"delivery_time": "2024-01-01T10:00:00Z"}
        )

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, "delivered")
        self.assertIsNotNone(self.notification.delivered_at)

        # Check that event was logged
        events = NotificationEvent.objects.filter(notification=self.notification)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().event_type, "delivered")

    def test_update_delivery_status_failed(self):
        """Test updating notification status to failed"""
        DeliveryStatusTracker.update_delivery_status(str(self.notification.id), "failed", {"error": "Network timeout"})

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, "failed")
        self.assertIn("Network timeout", self.notification.error_message)

    def test_update_delivery_status_read(self):
        """Test updating notification status to read"""
        DeliveryStatusTracker.update_delivery_status(str(self.notification.id), "read")

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, "read")
        self.assertIsNotNone(self.notification.read_at)

    def test_update_delivery_status_invalid_notification(self):
        """Test updating status for non-existent notification"""
        # This should not raise an exception
        DeliveryStatusTracker.update_delivery_status("invalid-uuid", "delivered")

        # Original notification should be unchanged
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, "sent")

    def test_get_delivery_stats(self):
        """Test getting delivery statistics"""
        # Create additional notifications with different statuses
        notifications_data = [
            {"status": "delivered"},
            {"status": "delivered"},
            {"status": "failed"},
            {"status": "read"},
        ]

        for data in notifications_data:
            Notification.objects.create(
                user=self.user, notification_type="push", title="Stats Test", body="Testing stats", status=data["status"]
            )

        stats = DeliveryStatusTracker.get_delivery_stats(user_id=self.user.id, days=30)

        self.assertEqual(stats["total"], 5)  # Including the one from setUp
        self.assertEqual(stats["delivered"], 2)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["read"], 1)
        self.assertEqual(stats["delivery_rate"], 40.0)  # 2/5 * 100
        self.assertEqual(stats["read_rate"], 20.0)  # 1/5 * 100
        self.assertEqual(stats["failure_rate"], 20.0)  # 1/5 * 100

    def test_get_delivery_stats_no_user(self):
        """Test getting delivery statistics for all users"""
        stats = DeliveryStatusTracker.get_delivery_stats(days=30)

        self.assertGreaterEqual(stats["total"], 1)  # At least the notification from setUp
        self.assertIn("delivery_rate", stats)
        self.assertIn("read_rate", stats)
        self.assertIn("failure_rate", stats)

    def test_get_delivery_stats_empty(self):
        """Test getting delivery statistics with no notifications"""
        # Delete all notifications
        Notification.objects.all().delete()

        stats = DeliveryStatusTracker.get_delivery_stats(days=30)

        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["delivery_rate"], 0)
        self.assertEqual(stats["read_rate"], 0)
        self.assertEqual(stats["failure_rate"], 0)
