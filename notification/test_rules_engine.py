"""
Comprehensive test cases for notification rules engine
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import (
    Notification,
    NotificationEvent,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .rules_engine import (
    EventDataBuilder,
    NotificationRulesEngine,
    trigger_delivery_event,
    trigger_order_event,
    trigger_payment_event,
    trigger_stock_event,
    trigger_user_event,
)

User = get_user_model()


class NotificationRulesEngineTests(TestCase):
    """Test notification rules engine"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        # Create user preferences
        UserNotificationPreference.objects.create(
            user=self.user, push_enabled=True, email_enabled=True, order_notifications=True
        )

        self.template = NotificationTemplate.objects.create(
            name="test_template",
            template_type="push",
            title_template="Order {status}",
            body_template="Your order #{order_number} is {status}. Amount: Rs. {amount}",
            variables=["status", "order_number", "amount"],
        )

        self.rule = NotificationRule.objects.create(
            name="Test Order Rule",
            trigger_event="order_created",
            template=self.template,
            target_users={"event_based": {"use_event_user": True}},
            is_active=True,
            priority=8,
        )

    def test_trigger_event_basic(self):
        """Test basic event triggering"""
        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        engine.trigger_event("order_created", event_data, self.user.id)

        # Check if notification was created
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)

        notification = notifications.first()
        self.assertEqual(notification.title, "Order created")
        self.assertEqual(notification.body, "Your order #ORD-123 is created. Amount: Rs. 1500.0")
        self.assertEqual(notification.rule, self.rule)
        self.assertEqual(notification.template, self.template)

    def test_trigger_event_with_conditions(self):
        """Test event triggering with conditions"""
        # Update rule to have conditions
        self.rule.conditions = [{"field": "amount", "operator": "gt", "value": 1000}]
        self.rule.save()

        engine = NotificationRulesEngine()

        # Test with amount > 1000 (should trigger)
        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        engine.trigger_event("order_created", event_data, self.user.id)

        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)

        # Test with amount <= 1000 (should not trigger)
        event_data["amount"] = 500.0
        event_data["order_number"] = "ORD-124"

        engine.trigger_event("order_created", event_data, self.user.id)

        # Should still be only 1 notification
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)

    def test_trigger_event_multiple_conditions(self):
        """Test event triggering with multiple conditions"""
        self.rule.conditions = [
            {"field": "amount", "operator": "gt", "value": 1000},
            {"field": "status", "operator": "eq", "value": "confirmed"},
        ]
        self.rule.save()

        engine = NotificationRulesEngine()

        # Test with both conditions met
        event_data = {"status": "confirmed", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        engine.trigger_event("order_created", event_data, self.user.id)

        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)

        # Test with only one condition met
        event_data = {
            "status": "pending",  # Different status
            "order_number": "ORD-124",
            "amount": 1500.0,
            "user_id": self.user.id,
        }

        engine.trigger_event("order_created", event_data, self.user.id)

        # Should still be only 1 notification
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)

    def test_trigger_event_inactive_rule(self):
        """Test event triggering with inactive rule"""
        self.rule.is_active = False
        self.rule.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        engine.trigger_event("order_created", event_data, self.user.id)

        # No notifications should be created
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 0)

    def test_trigger_event_no_matching_rules(self):
        """Test event triggering with no matching rules"""
        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        # Trigger different event
        engine.trigger_event("payment_received", event_data, self.user.id)

        # No notifications should be created
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 0)

    def test_trigger_event_with_delay(self):
        """Test event triggering with delay"""
        self.rule.delay_minutes = 30
        self.rule.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        with patch("notification.rules_engine.send_delayed_notification_task") as mock_task:
            engine.trigger_event("order_created", event_data, self.user.id)

            # Check that delayed task was called
            mock_task.apply_async.assert_called_once()

            # Check notification was created with future scheduled time
            notification = Notification.objects.get(user=self.user)
            self.assertGreater(notification.scheduled_at, timezone.now())

    def test_target_users_all_users(self):
        """Test targeting all users"""
        # Create additional users
        user2 = User.objects.create_user(username="user2", email="user2@example.com")
        user3 = User.objects.create_user(username="user3", email="user3@example.com")

        # Create preferences for new users
        for user in [user2, user3]:
            UserNotificationPreference.objects.create(user=user, push_enabled=True, order_notifications=True)

        # Update rule to target all users
        self.rule.target_users = {"all_users": True}
        self.rule.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0}

        engine.trigger_event("order_created", event_data)

        # Check that notifications were created for all users
        total_notifications = Notification.objects.count()
        self.assertEqual(total_notifications, 3)  # All 3 users

    def test_target_users_specific_ids(self):
        """Test targeting specific user IDs"""
        # Create additional users
        user2 = User.objects.create_user(username="user2", email="user2@example.com")
        user3 = User.objects.create_user(username="user3", email="user3@example.com")

        # Create preferences
        for user in [user2, user3]:
            UserNotificationPreference.objects.create(user=user, push_enabled=True, order_notifications=True)

        # Update rule to target specific users
        self.rule.target_users = {"user_ids": [self.user.id, user2.id]}
        self.rule.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0}

        engine.trigger_event("order_created", event_data)

        # Check that notifications were created for specific users only
        notifications = Notification.objects.all()
        self.assertEqual(notifications.count(), 2)

        user_ids = [n.user.id for n in notifications]
        self.assertIn(self.user.id, user_ids)
        self.assertIn(user2.id, user_ids)
        self.assertNotIn(user3.id, user_ids)

    def test_user_preferences_disabled(self):
        """Test with user preferences disabled"""
        # Disable all notifications for user
        prefs = self.user.notification_preferences
        prefs.push_enabled = False
        prefs.email_enabled = False
        prefs.sms_enabled = False
        prefs.in_app_enabled = False
        prefs.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        engine.trigger_event("order_created", event_data, self.user.id)

        # No notifications should be created
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 0)

    def test_user_quiet_hours(self):
        """Test user quiet hours"""
        # Set quiet hours
        prefs = self.user.notification_preferences
        prefs.quiet_hours_enabled = True
        prefs.quiet_start_time = "22:00:00"
        prefs.quiet_end_time = "08:00:00"
        prefs.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        # Mock current time to be in quiet hours
        with patch("django.utils.timezone.now") as mock_now:
            mock_time = timezone.now().replace(hour=23, minute=0, second=0)
            mock_now.return_value = mock_time

            with patch.object(prefs, "is_quiet_time", return_value=True):
                engine.trigger_event("order_created", event_data, self.user.id)

                # No notifications should be created during quiet hours
                notifications = Notification.objects.filter(user=self.user)
                self.assertEqual(notifications.count(), 0)

    def test_template_rendering_error(self):
        """Test handling of template rendering errors"""
        # Create template with missing variable
        template = NotificationTemplate.objects.create(
            name="error_template",
            template_type="push",
            title_template="Order {status}",
            body_template="Missing variable: {missing_var}",
            variables=["status", "missing_var"],
        )

        self.rule.template = template
        self.rule.save()

        engine = NotificationRulesEngine()

        event_data = {"status": "created", "order_number": "ORD-123", "amount": 1500.0, "user_id": self.user.id}

        engine.trigger_event("order_created", event_data, self.user.id)

        # No notifications should be created due to template error
        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 0)


class EventDataBuilderTests(TestCase):
    """Test event data builder"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_order_event_builder(self):
        """Test order event data builder"""
        # Mock order object
        order = MagicMock()
        order.id = 123
        order.order_number = "ORD-123"
        order.user = self.user
        order.producer_id = 456
        order.total_amount = 1500.0
        order.status = "confirmed"
        order.created_at = timezone.now()
        order.user.get_full_name.return_value = "Test User"

        event_data = EventDataBuilder.order_event(order, "confirmed")

        self.assertEqual(event_data["event_category"], "order")
        self.assertEqual(event_data["event_type"], "confirmed")
        self.assertEqual(event_data["order_id"], 123)
        self.assertEqual(event_data["order_number"], "ORD-123")
        self.assertEqual(event_data["user_id"], self.user.id)
        self.assertEqual(event_data["producer_id"], 456)
        self.assertEqual(event_data["total_amount"], 1500.0)
        self.assertEqual(event_data["status"], "confirmed")
        self.assertEqual(event_data["customer_name"], "Test User")
        self.assertIn("created_at", event_data)

    def test_payment_event_builder(self):
        """Test payment event data builder"""
        # Mock payment object
        payment = MagicMock()
        payment.id = 789
        payment.user = self.user
        payment.amount = 1500.0
        payment.status = "completed"
        payment.payment_method = "Khalti"
        payment.transaction_id = "TXN123456"
        payment.created_at = timezone.now()

        event_data = EventDataBuilder.payment_event(payment, "received")

        self.assertEqual(event_data["event_category"], "payment")
        self.assertEqual(event_data["event_type"], "received")
        self.assertEqual(event_data["payment_id"], 789)
        self.assertEqual(event_data["user_id"], self.user.id)
        self.assertEqual(event_data["amount"], 1500.0)
        self.assertEqual(event_data["status"], "completed")
        self.assertEqual(event_data["payment_method"], "Khalti")
        self.assertEqual(event_data["transaction_id"], "TXN123456")

    def test_delivery_event_builder(self):
        """Test delivery event data builder"""
        # Mock delivery object
        delivery = MagicMock()
        delivery.id = 999
        delivery.customer_id = self.user.id
        delivery.transporter_id = 555
        delivery.status = "in_transit"
        delivery.pickup_location = "Warehouse A"
        delivery.delivery_location = "Customer Address"
        delivery.estimated_delivery_time = "2024-01-01T15:00:00Z"
        delivery.tracking_number = "TRK123456"

        event_data = EventDataBuilder.delivery_event(delivery, "assigned")

        self.assertEqual(event_data["event_category"], "delivery")
        self.assertEqual(event_data["event_type"], "assigned")
        self.assertEqual(event_data["delivery_id"], 999)
        self.assertEqual(event_data["user_id"], self.user.id)
        self.assertEqual(event_data["transporter_id"], 555)
        self.assertEqual(event_data["status"], "in_transit")
        self.assertEqual(event_data["pickup_location"], "Warehouse A")
        self.assertEqual(event_data["delivery_location"], "Customer Address")
        self.assertEqual(event_data["tracking_number"], "TRK123456")

    def test_stock_event_builder(self):
        """Test stock event data builder"""
        # Mock product object
        product = MagicMock()
        product.id = 777
        product.name = "Organic Tomatoes"
        product.stock_quantity = 5
        product.low_stock_threshold = 10
        product.producer_id = 888
        product.category = "Vegetables"

        event_data = EventDataBuilder.stock_event(product, "low")

        self.assertEqual(event_data["event_category"], "inventory")
        self.assertEqual(event_data["event_type"], "low")
        self.assertEqual(event_data["product_id"], 777)
        self.assertEqual(event_data["product_name"], "Organic Tomatoes")
        self.assertEqual(event_data["current_stock"], 5)
        self.assertEqual(event_data["threshold"], 10)
        self.assertEqual(event_data["producer_id"], 888)
        self.assertEqual(event_data["category"], "Vegetables")

    def test_user_event_builder(self):
        """Test user event data builder"""
        event_data = EventDataBuilder.user_event(self.user, "registered")

        self.assertEqual(event_data["event_category"], "user")
        self.assertEqual(event_data["event_type"], "registered")
        self.assertEqual(event_data["user_id"], self.user.id)
        self.assertEqual(event_data["username"], "testuser")
        self.assertEqual(event_data["email"], "test@example.com")
        self.assertEqual(event_data["user_type"], "")  # Default empty
        self.assertIn("created_at", event_data)


class ConvenienceFunctionTests(TestCase):
    """Test convenience functions for triggering events"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("notification.rules_engine.NotificationRulesEngine.trigger_event")
    def test_trigger_order_event(self, mock_trigger):
        """Test trigger_order_event convenience function"""
        # Mock order object
        order = MagicMock()
        order.id = 123
        order.order_number = "ORD-123"
        order.user = self.user
        order.total_amount = 1500.0
        order.status = "confirmed"
        order.created_at = timezone.now()
        order.user.get_full_name.return_value = "Test User"

        trigger_order_event(order, "confirmed")

        mock_trigger.assert_called_once()
        args, kwargs = mock_trigger.call_args

        self.assertEqual(args[0], "order_confirmed")
        self.assertEqual(args[1]["event_category"], "order")
        self.assertEqual(args[1]["order_id"], 123)

    @patch("notification.rules_engine.NotificationRulesEngine.trigger_event")
    def test_trigger_payment_event(self, mock_trigger):
        """Test trigger_payment_event convenience function"""
        # Mock payment object
        payment = MagicMock()
        payment.id = 789
        payment.user = self.user
        payment.amount = 1500.0
        payment.status = "completed"
        payment.created_at = timezone.now()

        trigger_payment_event(payment, "received")

        mock_trigger.assert_called_once()
        args, kwargs = mock_trigger.call_args

        self.assertEqual(args[0], "payment_received")
        self.assertEqual(args[1]["event_category"], "payment")
        self.assertEqual(args[1]["payment_id"], 789)

    @patch("notification.rules_engine.NotificationRulesEngine.trigger_event")
    def test_trigger_delivery_event(self, mock_trigger):
        """Test trigger_delivery_event convenience function"""
        # Mock delivery object
        delivery = MagicMock()
        delivery.id = 999
        delivery.customer_id = self.user.id
        delivery.status = "assigned"

        trigger_delivery_event(delivery, "assigned")

        mock_trigger.assert_called_once()
        args, kwargs = mock_trigger.call_args

        self.assertEqual(args[0], "delivery_assigned")
        self.assertEqual(args[1]["event_category"], "delivery")
        self.assertEqual(args[1]["delivery_id"], 999)

    @patch("notification.rules_engine.NotificationRulesEngine.trigger_event")
    def test_trigger_stock_event(self, mock_trigger):
        """Test trigger_stock_event convenience function"""
        # Mock product object
        product = MagicMock()
        product.id = 777
        product.name = "Organic Tomatoes"
        product.stock_quantity = 5

        trigger_stock_event(product, "low")

        mock_trigger.assert_called_once()
        args, kwargs = mock_trigger.call_args

        self.assertEqual(args[0], "stock_low")
        self.assertEqual(args[1]["event_category"], "inventory")
        self.assertEqual(args[1]["product_id"], 777)

    @patch("notification.rules_engine.NotificationRulesEngine.trigger_event")
    def test_trigger_user_event(self, mock_trigger):
        """Test trigger_user_event convenience function"""
        trigger_user_event(self.user, "registered")

        mock_trigger.assert_called_once()
        args, kwargs = mock_trigger.call_args

        self.assertEqual(args[0], "user_registered")
        self.assertEqual(args[1]["event_category"], "user")
        self.assertEqual(args[1]["user_id"], self.user.id)
