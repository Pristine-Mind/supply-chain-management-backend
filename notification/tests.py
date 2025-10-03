"""
Main test module that imports all test cases from separate test files
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .rules_engine import EventDataBuilder, NotificationRulesEngine
from .services import FCMService, NotificationServiceFactory
from .test_api_usage import *
from .test_rules_engine import *

# Import all test cases from separate modules
from .test_services import *
from .test_tasks import *
from .test_utils import *
from .utils import NotificationHelper, NotificationTemplateBuilder

User = get_user_model()


class NotificationModelTests(TestCase):
    """Test notification models"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_notification_template_creation(self):
        """Test notification template creation"""
        template = NotificationTemplate.objects.create(
            name="test_template",
            template_type="push",
            title_template="Hello {name}!",
            body_template="Welcome to our app, {name}.",
            variables=["name"],
        )

        self.assertEqual(template.name, "test_template")
        self.assertEqual(template.template_type, "push")
        self.assertTrue(template.is_active)

    def test_template_rendering(self):
        """Test template rendering with context"""
        template = NotificationTemplate.objects.create(
            name="test_template",
            template_type="push",
            title_template="Hello {name}!",
            body_template="Your order #{order_id} is {status}.",
            variables=["name", "order_id", "status"],
        )

        context = {"name": "John", "order_id": "12345", "status": "confirmed"}

        rendered = template.render(context)

        self.assertEqual(rendered["title"], "Hello John!")
        self.assertEqual(rendered["body"], "Your order #12345 is confirmed.")

    def test_template_rendering_missing_variable(self):
        """Test template rendering with missing variable"""
        template = NotificationTemplate.objects.create(
            name="test_template",
            template_type="push",
            title_template="Hello {name}!",
            body_template="Your order #{order_id} is ready.",
            variables=["name", "order_id"],
        )

        context = {"name": "John"}  # Missing order_id

        with self.assertRaises(ValueError):
            template.render(context)

    def test_notification_rule_condition_evaluation(self):
        """Test notification rule condition evaluation"""
        template = NotificationTemplate.objects.create(
            name="test_template", template_type="push", title_template="Test", body_template="Test message"
        )

        rule = NotificationRule.objects.create(
            name="test_rule",
            trigger_event="order_created",
            template=template,
            conditions=[
                {"field": "amount", "operator": "gt", "value": 100},
                {"field": "status", "operator": "eq", "value": "confirmed"},
            ],
        )

        # Test matching conditions
        event_data = {"amount": 150, "status": "confirmed"}
        self.assertTrue(rule.evaluate_conditions(event_data))

        # Test non-matching conditions
        event_data = {"amount": 50, "status": "confirmed"}
        self.assertFalse(rule.evaluate_conditions(event_data))

    def test_user_notification_preferences(self):
        """Test user notification preferences"""
        preferences = UserNotificationPreference.objects.create(
            user=self.user,
            push_enabled=True,
            email_enabled=False,
            quiet_hours_enabled=True,
            quiet_start_time="22:00:00",
            quiet_end_time="08:00:00",
        )

        self.assertTrue(preferences.push_enabled)
        self.assertFalse(preferences.email_enabled)
        self.assertTrue(preferences.quiet_hours_enabled)

    def test_device_token_creation(self):
        """Test device token creation"""
        token = DeviceToken.objects.create(
            user=self.user, token="test_device_token_123", device_type="android", device_id="device_123"
        )

        self.assertEqual(token.user, self.user)
        self.assertEqual(token.device_type, "android")
        self.assertTrue(token.is_active)

    def test_notification_creation(self):
        """Test notification creation"""
        notification = Notification.objects.create(
            user=self.user,
            notification_type="push",
            title="Test Notification",
            body="This is a test notification",
            priority=5,
        )

        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.status, "pending")
        self.assertEqual(notification.priority, 5)

    def test_notification_status_updates(self):
        """Test notification status update methods"""
        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Test Notification", body="This is a test notification"
        )

        # Test mark as sent
        notification.mark_as_sent()
        self.assertEqual(notification.status, "sent")
        self.assertIsNotNone(notification.sent_at)

        # Test mark as delivered
        notification.mark_as_delivered()
        self.assertEqual(notification.status, "delivered")
        self.assertIsNotNone(notification.delivered_at)

        # Test mark as read
        notification.mark_as_read()
        self.assertEqual(notification.status, "read")
        self.assertIsNotNone(notification.read_at)


class NotificationServiceTests(TestCase):
    """Test notification services"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.services.messaging.send")
    @patch("notification.services.initialize_app")
    def test_fcm_service_send_notification(self, mock_init_app, mock_send):
        """Test FCM service send notification"""
        # Create device token
        DeviceToken.objects.create(user=self.user, token="test_fcm_token", device_type="android")

        # Create notification
        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Test FCM", body="Test FCM notification"
        )

        # Mock FCM response
        mock_send.return_value = "message_id_123"

        # Test FCM service
        fcm_service = FCMService()
        result = fcm_service.send_notification(notification)

        self.assertTrue(result)
        mock_send.assert_called_once()

    def test_notification_service_factory(self):
        """Test notification service factory"""
        push_service = NotificationServiceFactory.get_service("push")
        email_service = NotificationServiceFactory.get_service("email")
        sms_service = NotificationServiceFactory.get_service("sms")
        invalid_service = NotificationServiceFactory.get_service("invalid")

        self.assertIsInstance(push_service, FCMService)
        self.assertIsNotNone(email_service)
        self.assertIsNotNone(sms_service)
        self.assertIsNone(invalid_service)


class NotificationRulesEngineTests(TestCase):
    """Test notification rules engine"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        self.template = NotificationTemplate.objects.create(
            name="test_template",
            template_type="push",
            title_template="Order {status}",
            body_template="Your order #{order_id} is {status}.",
            variables=["status", "order_id"],
        )

        self.rule = NotificationRule.objects.create(
            name="test_rule",
            trigger_event="order_created",
            template=self.template,
            target_users={"event_based": {"use_event_user": True}},
            is_active=True,
        )

    def test_rules_engine_trigger_event(self):
        """Test rules engine event triggering"""
        engine = NotificationRulesEngine()

        event_data = {"order_id": "12345", "status": "created", "user_id": self.user.id}

        # Trigger event
        engine.trigger_event("order_created", event_data, self.user.id)

        # Check if notification was created
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)

        notification = notifications.first()
        self.assertEqual(notification.title, "Order created")
        self.assertEqual(notification.body, "Your order #12345 is created.")

    def test_event_data_builder(self):
        """Test event data builder"""
        # Mock order object
        order = MagicMock()
        order.id = 123
        order.user.id = self.user.id
        order.total_amount = 1500.0
        order.status = "confirmed"
        order.created_at = timezone.now()
        order.user.get_full_name.return_value = "Test User"

        event_data = EventDataBuilder.order_event(order, "confirmed")

        self.assertEqual(event_data["event_category"], "order")
        self.assertEqual(event_data["event_type"], "confirmed")
        self.assertEqual(event_data["order_id"], 123)
        self.assertEqual(event_data["user_id"], self.user.id)
        self.assertEqual(event_data["total_amount"], 1500.0)


class NotificationUtilsTests(TestCase):
    """Test notification utilities"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_notification_helper_quick_notification(self):
        """Test notification helper quick notification"""
        notification = NotificationHelper.create_quick_notification(
            user=self.user,
            title="Quick Test",
            body="This is a quick test notification",
            notification_type="push",
            send_immediately=False,
        )

        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.title, "Quick Test")
        self.assertEqual(notification.notification_type, "push")

    def test_notification_template_builder(self):
        """Test notification template builder"""
        template = (
            NotificationTemplateBuilder()
            .name("builder_test")
            .type("push")
            .title("Hello {name}!")
            .body("Welcome {name}")
            .variables(["name"])
            .active(True)
            .build()
        )

        self.assertEqual(template.name, "builder_test")
        self.assertEqual(template.template_type, "push")
        self.assertTrue(template.is_active)

    def test_notification_rule_builder(self):
        """Test notification rule builder"""
        template = NotificationTemplate.objects.create(
            name="test_template", template_type="push", title_template="Test", body_template="Test message"
        )

        rule = (
            NotificationRuleBuilder()
            .name("builder_rule")
            .trigger("test_event")
            .template(template)
            .priority(8)
            .active(True)
            .build()
        )

        self.assertEqual(rule.name, "builder_rule")
        self.assertEqual(rule.trigger_event, "test_event")
        self.assertEqual(rule.template, template)
        self.assertEqual(rule.priority, 8)


class NotificationAPITests(APITestCase):
    """Test notification APIs"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        # Create user preferences
        UserNotificationPreference.objects.create(user=self.user)

    def test_get_user_preferences(self):
        """Test get user notification preferences"""
        url = "/api/v1/notifications/preferences/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["push_enabled"])

    def test_update_user_preferences(self):
        """Test update user notification preferences"""
        url = "/api/v1/notifications/preferences/"
        data = {"push_enabled": False, "email_enabled": True, "marketing_notifications": False}

        response = self.client.put(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["push_enabled"])
        self.assertTrue(response.data["email_enabled"])

    def test_register_device_token(self):
        """Test device token registration"""
        url = "/api/v1/notifications/device-tokens/"
        data = {"token": "test_device_token_123", "device_type": "android", "device_id": "device_123"}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["token"], "test_device_token_123")

    def test_get_user_notifications(self):
        """Test get user notifications"""
        # Create test notification
        Notification.objects.create(user=self.user, notification_type="push", title="Test Notification", body="Test body")

        url = "/api/v1/notifications/my-notifications/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_mark_notification_as_read(self):
        """Test mark notification as read"""
        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Test Notification", body="Test body"
        )

        url = "/api/v1/notifications/notifications/actions/"
        data = {"action": "read", "notification_ids": [str(notification.id)]}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 1)

        # Check notification status
        notification.refresh_from_db()
        self.assertEqual(notification.status, "read")

    def test_notification_stats(self):
        """Test notification statistics"""
        # Create test notifications
        Notification.objects.create(
            user=self.user, notification_type="push", title="Test 1", body="Test body", status="delivered"
        )
        Notification.objects.create(
            user=self.user, notification_type="push", title="Test 2", body="Test body", status="read"
        )

        url = "/api/v1/notifications/notifications/stats/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

    def test_create_bulk_notifications(self):
        """Test bulk notification creation"""
        template = NotificationTemplate.objects.create(
            name="bulk_test",
            template_type="push",
            title_template="Bulk Test",
            body_template="This is a bulk test notification",
            variables=[],
        )

        url = "/api/v1/notifications/bulk-create/"
        data = {"template_id": str(template.id), "user_ids": [self.user.id], "context_data": {}, "notification_type": "push"}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["notifications_created"], 1)

    def test_trigger_notification_event(self):
        """Test trigger notification event"""
        # Create template and rule
        template = NotificationTemplate.objects.create(
            name="api_test",
            template_type="push",
            title_template="API Test",
            body_template="API test notification",
            variables=[],
        )

        NotificationRule.objects.create(
            name="api_test_rule",
            trigger_event="api_test",
            template=template,
            target_users={"event_based": {"use_event_user": True}},
            is_active=True,
        )

        url = "/api/v1/notifications/trigger-event/"
        data = {"event_name": "api_test", "event_data": {}, "user_id": self.user.id}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class NotificationTaskTests(TestCase):
    """Test notification Celery tasks"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.services.FCMService.send_notification")
    def test_send_notification_task(self, mock_send):
        """Test send notification task"""
        from .tasks import send_notification_task

        mock_send.return_value = True

        notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Task Test", body="Task test notification"
        )

        result = send_notification_task(str(notification.id))

        self.assertIn("sent successfully", result)
        mock_send.assert_called_once()

    def test_cleanup_old_notifications_task(self):
        """Test cleanup old notifications task"""
        from .tasks import cleanup_old_notifications_task

        # Create old notification
        old_notification = Notification.objects.create(
            user=self.user, notification_type="push", title="Old Notification", body="Old notification", status="delivered"
        )

        # Make it old
        old_notification.created_at = timezone.now() - timezone.timedelta(days=35)
        old_notification.save()

        result = cleanup_old_notifications_task(days=30)

        self.assertIn("Cleanup completed", result)

        # Check if notification was deleted
        self.assertFalse(Notification.objects.filter(id=old_notification.id).exists())
