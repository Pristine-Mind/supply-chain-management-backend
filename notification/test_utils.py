"""
Comprehensive test cases for notification utilities
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .utils import (
    NotificationHelper,
    NotificationRuleBuilder,
    NotificationTemplateBuilder,
    create_default_rules,
    create_default_templates,
    setup_notification_system,
)

User = get_user_model()


class NotificationHelperTests(TestCase):
    """Test notification helper utilities"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.utils.send_notification_task")
    def test_create_quick_notification(self, mock_task):
        """Test creating quick notification"""
        notification = NotificationHelper.create_quick_notification(
            user=self.user,
            title="Quick Test",
            body="This is a quick test notification",
            notification_type="push",
            action_url="https://example.com/action",
            icon_url="https://example.com/icon.png",
            priority=8,
            send_immediately=True,
        )

        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.title, "Quick Test")
        self.assertEqual(notification.body, "This is a quick test notification")
        self.assertEqual(notification.notification_type, "push")
        self.assertEqual(notification.action_url, "https://example.com/action")
        self.assertEqual(notification.icon_url, "https://example.com/icon.png")
        self.assertEqual(notification.priority, 8)
        self.assertEqual(notification.status, "pending")

        # Check that task was called for immediate sending
        mock_task.delay.assert_called_once_with(str(notification.id))

    @patch("notification.utils.send_notification_task")
    def test_create_quick_notification_no_immediate_send(self, mock_task):
        """Test creating quick notification without immediate sending"""
        notification = NotificationHelper.create_quick_notification(
            user=self.user,
            title="Delayed Test",
            body="This notification will not be sent immediately",
            send_immediately=False,
        )

        self.assertEqual(notification.title, "Delayed Test")

        # Task should not be called
        mock_task.delay.assert_not_called()

    @patch("notification.utils.send_notification_task")
    def test_send_notification_to_users(self, mock_task):
        """Test sending notifications to multiple users"""
        # Create additional users
        users = [self.user]
        for i in range(2, 5):
            user = User.objects.create_user(username=f"user{i}", email=f"user{i}@example.com", password="testpass123")
            users.append(user)

        user_ids = [user.id for user in users]

        notification_ids = NotificationHelper.send_notification_to_users(
            user_ids=user_ids,
            title="Bulk Test",
            body="This is a bulk notification",
            notification_type="push",
            context_data={"test": "data"},
            priority=7,
        )

        self.assertEqual(len(notification_ids), 4)

        # Check notifications were created
        notifications = Notification.objects.filter(title="Bulk Test")
        self.assertEqual(notifications.count(), 4)

        # Check task was called for each notification
        self.assertEqual(mock_task.delay.call_count, 4)

        # Check notification properties
        for notification in notifications:
            self.assertEqual(notification.title, "Bulk Test")
            self.assertEqual(notification.body, "This is a bulk notification")
            self.assertEqual(notification.notification_type, "push")
            self.assertEqual(notification.event_data, {"test": "data"})
            self.assertEqual(notification.priority, 7)

    def test_get_user_notification_summary(self):
        """Test getting user notification summary"""
        # Create notifications with different statuses
        notifications_data = [
            {"title": "Test 1", "status": "delivered", "notification_type": "push"},
            {"title": "Test 2", "status": "read", "notification_type": "push"},
            {"title": "Test 3", "status": "failed", "notification_type": "email"},
            {"title": "Test 4", "status": "pending", "notification_type": "sms"},
        ]

        for data in notifications_data:
            Notification.objects.create(
                user=self.user,
                title=data["title"],
                body="Test body",
                status=data["status"],
                notification_type=data["notification_type"],
            )

        summary = NotificationHelper.get_user_notification_summary(self.user, days=7)

        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["unread"], 3)  # delivered, failed, pending
        self.assertEqual(summary["read"], 1)  # read
        self.assertEqual(summary["period_days"], 7)

        # Check by_type breakdown
        self.assertEqual(summary["by_type"]["push"], 2)
        self.assertEqual(summary["by_type"]["email"], 1)
        self.assertEqual(summary["by_type"]["sms"], 1)

    def test_get_user_notification_summary_empty(self):
        """Test getting user notification summary with no notifications"""
        summary = NotificationHelper.get_user_notification_summary(self.user, days=7)

        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["unread"], 0)
        self.assertEqual(summary["read"], 0)
        self.assertEqual(summary["by_type"], {})

    def test_cleanup_inactive_device_tokens(self):
        """Test cleaning up inactive device tokens"""
        # Create device tokens with different last_used times
        old_date = timezone.now() - timedelta(days=35)
        recent_date = timezone.now() - timedelta(days=5)

        # Old token (should be deactivated)
        old_token = DeviceToken.objects.create(
            user=self.user, token="old_token_123", device_type="android", last_used=old_date, is_active=True
        )

        # Recent token (should remain active)
        recent_token = DeviceToken.objects.create(
            user=self.user, token="recent_token_456", device_type="ios", last_used=recent_date, is_active=True
        )

        count = NotificationHelper.cleanup_inactive_device_tokens(days=30)

        self.assertEqual(count, 1)

        # Check token statuses
        old_token.refresh_from_db()
        recent_token.refresh_from_db()

        self.assertFalse(old_token.is_active)
        self.assertTrue(recent_token.is_active)

    def test_get_notification_performance_metrics(self):
        """Test getting notification performance metrics"""
        # Create notifications with different statuses and times
        base_time = timezone.now()

        notifications_data = [
            {"status": "sent", "sent_at": base_time, "delivered_at": base_time + timedelta(seconds=10)},
            {"status": "delivered", "sent_at": base_time, "delivered_at": base_time + timedelta(seconds=15)},
            {"status": "read", "sent_at": base_time, "delivered_at": base_time + timedelta(seconds=5)},
            {"status": "failed"},
        ]

        for i, data in enumerate(notifications_data):
            notification = Notification.objects.create(
                user=self.user,
                title=f"Metrics Test {i+1}",
                body="Test body",
                notification_type="push",
                status=data["status"],
            )

            if "sent_at" in data:
                notification.sent_at = data["sent_at"]
            if "delivered_at" in data:
                notification.delivered_at = data["delivered_at"]
            notification.save()

        metrics = NotificationHelper.get_notification_performance_metrics(days=7)

        self.assertEqual(metrics["total_notifications"], 4)
        self.assertEqual(metrics["delivery_rate"], 25.0)  # 1 delivered out of 4
        self.assertEqual(metrics["read_rate"], 25.0)  # 1 read out of 4
        self.assertEqual(metrics["failure_rate"], 25.0)  # 1 failed out of 4
        self.assertGreater(metrics["avg_delivery_time"], 0)

        # Check status breakdown
        self.assertEqual(metrics["by_status"]["sent"], 1)
        self.assertEqual(metrics["by_status"]["delivered"], 1)
        self.assertEqual(metrics["by_status"]["read"], 1)
        self.assertEqual(metrics["by_status"]["failed"], 1)

        # Check type breakdown
        self.assertEqual(metrics["by_type"]["push"], 4)

    def test_get_notification_performance_metrics_empty(self):
        """Test getting performance metrics with no notifications"""
        metrics = NotificationHelper.get_notification_performance_metrics(days=7)

        self.assertEqual(metrics["total_notifications"], 0)
        self.assertEqual(metrics["delivery_rate"], 0)
        self.assertEqual(metrics["read_rate"], 0)
        self.assertEqual(metrics["failure_rate"], 0)
        self.assertEqual(metrics["avg_delivery_time"], 0)
        self.assertEqual(metrics["by_status"], {})
        self.assertEqual(metrics["by_type"], {})


class NotificationTemplateBuilderTests(TestCase):
    """Test notification template builder"""

    def test_template_builder_basic(self):
        """Test basic template building"""
        template = (
            NotificationTemplateBuilder()
            .name("test_template")
            .type("push")
            .title("Hello {name}!")
            .body("Welcome {name} to our app.")
            .variables(["name"])
            .active(True)
            .build()
        )

        self.assertEqual(template.name, "test_template")
        self.assertEqual(template.template_type, "push")
        self.assertEqual(template.title_template, "Hello {name}!")
        self.assertEqual(template.body_template, "Welcome {name} to our app.")
        self.assertEqual(template.variables, ["name"])
        self.assertTrue(template.is_active)

    def test_template_builder_full_features(self):
        """Test template builder with all features"""
        template = (
            NotificationTemplateBuilder()
            .name("full_template")
            .type("email")
            .title("Order Update: {status}")
            .body("Your order #{order_number} is {status}.")
            .action_url("https://example.com/orders/{order_id}")
            .icon("https://example.com/icon.png")
            .variables(["status", "order_number", "order_id"])
            .active(False)
            .build()
        )

        self.assertEqual(template.name, "full_template")
        self.assertEqual(template.template_type, "email")
        self.assertEqual(template.action_url_template, "https://example.com/orders/{order_id}")
        self.assertEqual(template.icon_url, "https://example.com/icon.png")
        self.assertFalse(template.is_active)

    def test_template_builder_chaining(self):
        """Test template builder method chaining"""
        builder = NotificationTemplateBuilder()

        # Test that each method returns the builder instance
        self.assertIs(builder.name("test"), builder)
        self.assertIs(builder.type("push"), builder)
        self.assertIs(builder.title("Title"), builder)
        self.assertIs(builder.body("Body"), builder)
        self.assertIs(builder.action_url("URL"), builder)
        self.assertIs(builder.icon("Icon"), builder)
        self.assertIs(builder.variables(["var"]), builder)
        self.assertIs(builder.active(True), builder)


class NotificationRuleBuilderTests(TestCase):
    """Test notification rule builder"""

    def setUp(self):
        self.template = NotificationTemplate.objects.create(
            name="test_template", template_type="push", title_template="Test", body_template="Test message"
        )

    def test_rule_builder_basic(self):
        """Test basic rule building"""
        rule = (
            NotificationRuleBuilder()
            .name("test_rule")
            .description("Test rule description")
            .trigger("order_created")
            .template(self.template)
            .priority(8)
            .active(True)
            .build()
        )

        self.assertEqual(rule.name, "test_rule")
        self.assertEqual(rule.description, "Test rule description")
        self.assertEqual(rule.trigger_event, "order_created")
        self.assertEqual(rule.template, self.template)
        self.assertEqual(rule.priority, 8)
        self.assertTrue(rule.is_active)

    def test_rule_builder_with_template_name(self):
        """Test rule builder with template name instead of instance"""
        rule = (
            NotificationRuleBuilder()
            .name("template_name_rule")
            .trigger("payment_received")
            .template("test_template")  # Using template name
            .build()
        )

        self.assertEqual(rule.template, self.template)

    def test_rule_builder_full_features(self):
        """Test rule builder with all features"""
        conditions = [{"field": "amount", "operator": "gt", "value": 1000}]

        target_users = {"event_based": {"use_event_user": True}}

        rule = (
            NotificationRuleBuilder()
            .name("full_rule")
            .description("Full featured rule")
            .trigger("order_confirmed")
            .template(self.template)
            .conditions(conditions)
            .target_users(target_users)
            .delay(30)
            .priority(9)
            .active(False)
            .build()
        )

        self.assertEqual(rule.conditions, conditions)
        self.assertEqual(rule.target_users, target_users)
        self.assertEqual(rule.delay_minutes, 30)
        self.assertEqual(rule.priority, 9)
        self.assertFalse(rule.is_active)

    def test_rule_builder_chaining(self):
        """Test rule builder method chaining"""
        builder = NotificationRuleBuilder()

        # Test that each method returns the builder instance
        self.assertIs(builder.name("test"), builder)
        self.assertIs(builder.description("desc"), builder)
        self.assertIs(builder.trigger("event"), builder)
        self.assertIs(builder.template(self.template), builder)
        self.assertIs(builder.conditions([]), builder)
        self.assertIs(builder.target_users({}), builder)
        self.assertIs(builder.delay(0), builder)
        self.assertIs(builder.priority(5), builder)
        self.assertIs(builder.active(True), builder)


class DefaultSystemSetupTests(TestCase):
    """Test default system setup functions"""

    def test_create_default_templates(self):
        """Test creating default templates"""
        templates = create_default_templates()

        self.assertGreater(len(templates), 0)

        # Check that some expected templates were created
        template_names = [t.name for t in templates]
        self.assertIn("order_created", template_names)
        self.assertIn("order_confirmed", template_names)
        self.assertIn("payment_received", template_names)
        self.assertIn("welcome_user", template_names)

        # Check template properties
        order_template = NotificationTemplate.objects.get(name="order_created")
        self.assertEqual(order_template.template_type, "push")
        self.assertIn("order_number", order_template.variables)
        self.assertTrue(order_template.is_active)

    def test_create_default_templates_idempotent(self):
        """Test that creating default templates is idempotent"""
        # Create templates first time
        templates1 = create_default_templates()
        initial_count = len(templates1)

        # Create templates second time
        templates2 = create_default_templates()

        # Should not create duplicates
        self.assertEqual(len(templates2), 0)

        # Total count should remain the same
        total_templates = NotificationTemplate.objects.count()
        self.assertEqual(total_templates, initial_count)

    def test_create_default_rules(self):
        """Test creating default rules"""
        rules = create_default_rules()

        self.assertGreater(len(rules), 0)

        # Check that some expected rules were created
        rule_names = [r.name for r in rules]
        self.assertIn("Order Creation Notification", rule_names)
        self.assertIn("Payment Success Notification", rule_names)
        self.assertIn("Welcome New User", rule_names)

        # Check rule properties
        order_rule = NotificationRule.objects.get(name="Order Creation Notification")
        self.assertEqual(order_rule.trigger_event, "order_created")
        self.assertTrue(order_rule.is_active)
        self.assertIsNotNone(order_rule.template)

    def test_create_default_rules_idempotent(self):
        """Test that creating default rules is idempotent"""
        # Create rules first time
        rules1 = create_default_rules()
        initial_count = len(rules1)

        # Create rules second time
        rules2 = create_default_rules()

        # Should not create duplicates
        self.assertEqual(len(rules2), 0)

        # Total count should remain the same
        total_rules = NotificationRule.objects.count()
        self.assertEqual(total_rules, initial_count)

    def test_setup_notification_system(self):
        """Test complete notification system setup"""
        result = setup_notification_system()

        self.assertIn("templates", result)
        self.assertIn("rules", result)

        templates_created = len(result["templates"])
        rules_created = len(result["rules"])

        self.assertGreater(templates_created, 0)
        self.assertGreater(rules_created, 0)

        # Check that templates and rules are properly linked
        for rule in NotificationRule.objects.all():
            self.assertIsNotNone(rule.template)
            self.assertTrue(rule.template.is_active)

    def test_setup_notification_system_idempotent(self):
        """Test that system setup is idempotent"""
        # Setup first time
        result1 = setup_notification_system()

        # Setup second time
        result2 = setup_notification_system()

        # Second setup should not create new items
        self.assertEqual(len(result2["templates"]), 0)
        self.assertEqual(len(result2["rules"]), 0)


class UtilityIntegrationTests(TestCase):
    """Integration tests for utility functions"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_end_to_end_notification_creation(self):
        """Test end-to-end notification creation using utilities"""
        # Setup system
        setup_result = setup_notification_system()
        self.assertGreater(len(setup_result["templates"]), 0)
        self.assertGreater(len(setup_result["rules"]), 0)

        # Create quick notification
        notification = NotificationHelper.create_quick_notification(
            user=self.user, title="Integration Test", body="Testing end-to-end flow", send_immediately=False
        )

        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.title, "Integration Test")

        # Get user summary
        summary = NotificationHelper.get_user_notification_summary(self.user)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["unread"], 1)

        # Get performance metrics
        metrics = NotificationHelper.get_notification_performance_metrics()
        self.assertEqual(metrics["total_notifications"], 1)

    @patch("notification.utils.send_notification_task")
    def test_bulk_operations_with_utilities(self, mock_task):
        """Test bulk operations using utility functions"""
        # Create multiple users
        users = [self.user]
        for i in range(2, 6):
            user = User.objects.create_user(username=f"user{i}", email=f"user{i}@example.com", password="testpass123")
            users.append(user)

        user_ids = [user.id for user in users]

        # Send bulk notifications
        notification_ids = NotificationHelper.send_notification_to_users(
            user_ids=user_ids, title="Bulk Integration Test", body="Testing bulk operations", priority=7
        )

        self.assertEqual(len(notification_ids), 5)

        # Verify notifications were created
        notifications = Notification.objects.filter(title="Bulk Integration Test")
        self.assertEqual(notifications.count(), 5)

        # Verify all users have notifications
        for user in users:
            user_notifications = notifications.filter(user=user)
            self.assertEqual(user_notifications.count(), 1)

        # Verify task was called for each notification
        self.assertEqual(mock_task.delay.call_count, 5)

    def test_template_and_rule_builders_integration(self):
        """Test template and rule builders working together"""
        # Create template using builder
        template = (
            NotificationTemplateBuilder()
            .name("integration_template")
            .type("push")
            .title("Integration {action}")
            .body("Integration test for {action} with {details}")
            .variables(["action", "details"])
            .build()
        )

        # Create rule using builder
        rule = (
            NotificationRuleBuilder()
            .name("Integration Rule")
            .trigger("integration_test")
            .template(template)
            .target_users({"event_based": {"use_event_user": True}})
            .priority(8)
            .build()
        )

        # Verify they work together
        self.assertEqual(rule.template, template)
        self.assertEqual(rule.trigger_event, "integration_test")

        # Test template rendering
        context = {"action": "testing", "details": "builder integration"}
        rendered = template.render(context)

        self.assertEqual(rendered["title"], "Integration testing")
        self.assertEqual(rendered["body"], "Integration test for testing with builder integration")
