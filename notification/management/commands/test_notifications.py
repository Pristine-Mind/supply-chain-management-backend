from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from notification.rules_engine import NotificationRulesEngine
from notification.utils import NotificationHelper

User = get_user_model()


class Command(BaseCommand):
    help = "Test notification system functionality"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            help="User ID to send test notification to",
        )
        parser.add_argument(
            "--event",
            type=str,
            help="Event name to trigger",
        )
        parser.add_argument(
            "--type",
            type=str,
            choices=["push", "email", "sms", "in_app"],
            default="push",
            help="Notification type",
        )

    def handle(self, *args, **options):
        user_id = options.get("user_id")
        event = options.get("event")
        notification_type = options.get("type")

        if user_id:
            self.test_direct_notification(user_id, notification_type)
        elif event:
            self.test_event_trigger(event)
        else:
            self.run_all_tests()

    def test_direct_notification(self, user_id, notification_type):
        """Test sending a direct notification to a user"""
        try:
            user = User.objects.get(id=user_id)

            notification = NotificationHelper.create_quick_notification(
                user=user,
                title="Test Notification",
                body=f"This is a test {notification_type} notification sent from management command.",
                notification_type=notification_type,
                priority=5,
                send_immediately=True,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Test {notification_type} notification sent to user {user.username} " f"(ID: {notification.id})"
                )
            )

        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error sending test notification: {e}"))

    def test_event_trigger(self, event_name):
        """Test triggering a notification event"""
        try:
            engine = NotificationRulesEngine()

            # Sample event data
            event_data = {
                "user_id": 1,  # Adjust based on your users
                "order_number": "TEST-001",
                "product_name": "Test Product",
                "customer_name": "Test Customer",
                "amount": 1000.0,
                "status": "confirmed",
            }

            engine.trigger_event(event_name, event_data)

            self.stdout.write(self.style.SUCCESS(f'Event "{event_name}" triggered successfully'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error triggering event: {e}"))

    def run_all_tests(self):
        """Run comprehensive tests"""
        self.stdout.write(self.style.SUCCESS("Running comprehensive notification tests..."))

        # Test 1: Check if system is properly configured
        self.test_system_configuration()

        # Test 2: Test template rendering
        self.test_template_rendering()

        # Test 3: Test user preferences
        self.test_user_preferences()

        # Test 4: Test device tokens
        self.test_device_tokens()

        self.stdout.write(self.style.SUCCESS("All tests completed!"))

    def test_system_configuration(self):
        """Test system configuration"""
        from notification.models import NotificationRule, NotificationTemplate

        templates_count = NotificationTemplate.objects.count()
        rules_count = NotificationRule.objects.count()

        self.stdout.write(f"Templates in system: {templates_count}")
        self.stdout.write(f"Rules in system: {rules_count}")

        if templates_count == 0:
            self.stdout.write(self.style.WARNING("No templates found. Run setup_notifications command first."))

        if rules_count == 0:
            self.stdout.write(self.style.WARNING("No rules found. Run setup_notifications command first."))

    def test_template_rendering(self):
        """Test template rendering"""
        from notification.models import NotificationTemplate

        try:
            template = NotificationTemplate.objects.filter(is_active=True).first()
            if template:
                context = {
                    "order_number": "TEST-001",
                    "customer_name": "Test Customer",
                    "product_name": "Test Product",
                    "amount": 1000.0,
                }

                rendered = template.render(context)
                self.stdout.write(f'Template "{template.name}" rendered successfully:')
                self.stdout.write(f'  Title: {rendered["title"]}')
                self.stdout.write(f'  Body: {rendered["body"]}')
            else:
                self.stdout.write(self.style.WARNING("No active templates found for testing"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Template rendering test failed: {e}"))

    def test_user_preferences(self):
        """Test user preferences"""
        from notification.models import UserNotificationPreference

        users_with_prefs = UserNotificationPreference.objects.count()
        total_users = User.objects.count()

        self.stdout.write(f"Users with preferences: {users_with_prefs}/{total_users}")

        if users_with_prefs < total_users:
            self.stdout.write(self.style.WARNING(f"{total_users - users_with_prefs} users missing notification preferences"))

    def test_device_tokens(self):
        """Test device tokens"""
        from notification.models import DeviceToken

        active_tokens = DeviceToken.objects.filter(is_active=True).count()
        total_tokens = DeviceToken.objects.count()

        self.stdout.write(f"Active device tokens: {active_tokens}/{total_tokens}")

        if active_tokens == 0:
            self.stdout.write(self.style.WARNING("No active device tokens found"))
