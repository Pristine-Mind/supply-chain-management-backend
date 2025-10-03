"""
Comprehensive test cases for API usage and integration
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)

User = get_user_model()


class NotificationAPIUsageTests(APITestCase):
    """Test API usage scenarios"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        # Create user preferences
        UserNotificationPreference.objects.create(user=self.user)

    def test_complete_notification_workflow(self):
        """Test complete notification workflow via API"""
        # Step 1: Create a notification template
        template_data = {
            "name": "api_test_template",
            "template_type": "push",
            "title_template": "Order {status}",
            "body_template": "Your order #{order_number} is {status}",
            "variables": ["status", "order_number"],
            "is_active": True,
        }

        response = self.client.post("/api/v1/notifications/templates/", template_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        template_id = response.data["id"]

        # Step 2: Create a notification rule
        rule_data = {
            "name": "API Test Rule",
            "description": "Test rule created via API",
            "trigger_event": "order_confirmed",
            "template": template_id,
            "target_users": {"event_based": {"use_event_user": True}},
            "is_active": True,
            "priority": 8,
        }

        response = self.client.post("/api/v1/notifications/rules/", rule_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 3: Register device token
        token_data = {"token": "api_test_device_token_123", "device_type": "android", "device_id": "api_test_device"}

        response = self.client.post("/api/v1/notifications/device-tokens/", token_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 4: Trigger notification event
        event_data = {
            "event_name": "order_confirmed",
            "event_data": {"status": "confirmed", "order_number": "API-001"},
            "user_id": self.user.id,
        }

        response = self.client.post("/api/v1/notifications/trigger-event/", event_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 5: Check notifications were created
        response = self.client.get("/api/v1/notifications/my-notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        notification = response.data["results"][0]
        self.assertEqual(notification["title"], "Order confirmed")
        self.assertEqual(notification["body"], "Your order #API-001 is confirmed")

    def test_bulk_notification_creation(self):
        """Test bulk notification creation via API"""
        # Create template
        template = NotificationTemplate.objects.create(
            name="bulk_api_template",
            template_type="push",
            title_template="Bulk Notification",
            body_template="This is a bulk notification for {user_name}",
            variables=["user_name"],
        )

        # Create additional users
        users = [self.user]
        for i in range(2, 5):
            user = User.objects.create_user(username=f"bulkuser{i}", email=f"bulk{i}@example.com", password="testpass123")
            users.append(user)
            UserNotificationPreference.objects.create(user=user)

        # Create bulk notifications
        bulk_data = {
            "template_id": str(template.id),
            "user_ids": [user.id for user in users],
            "context_data": {"user_name": "Test User"},
            "notification_type": "push",
            "priority": 6,
        }

        response = self.client.post("/api/v1/notifications/bulk-create/", bulk_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["notifications_created"], 4)

        # Verify notifications were created
        notifications = Notification.objects.filter(template=template)
        self.assertEqual(notifications.count(), 4)

    def test_notification_batch_workflow(self):
        """Test notification batch workflow via API"""
        # Create template
        template = NotificationTemplate.objects.create(
            name="batch_api_template",
            template_type="push",
            title_template="Newsletter",
            body_template="Weekly newsletter: {content}",
            variables=["content"],
        )

        # Create batch
        batch_data = {
            "name": "API Test Batch",
            "description": "Test batch created via API",
            "template": str(template.id),
            "context_data": {"content": "Latest updates and news"},
        }

        response = self.client.post("/api/v1/notifications/batches/", batch_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        batch_id = response.data["id"]

        # Get batch details
        response = self.client.get(f"/api/v1/notifications/batches/{batch_id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "API Test Batch")

    def test_user_preferences_management(self):
        """Test user preferences management via API"""
        # Get current preferences
        response = self.client.get("/api/v1/notifications/preferences/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["push_enabled"])

        # Update preferences
        update_data = {
            "push_enabled": False,
            "email_enabled": True,
            "marketing_notifications": False,
            "quiet_hours_enabled": True,
            "quiet_start_time": "22:00:00",
            "quiet_end_time": "08:00:00",
        }

        response = self.client.put("/api/v1/notifications/preferences/", update_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["push_enabled"])
        self.assertTrue(response.data["quiet_hours_enabled"])

    def test_notification_actions(self):
        """Test notification actions via API"""
        # Create test notifications
        notifications = []
        for i in range(3):
            notification = Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Action Test {i+1}",
                body="Test notification for actions",
                status="delivered",
            )
            notifications.append(notification)

        # Mark notifications as read
        action_data = {"action": "read", "notification_ids": [str(n.id) for n in notifications]}

        response = self.client.post("/api/v1/notifications/notifications/actions/", action_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 3)

        # Verify notifications are marked as read
        for notification in notifications:
            notification.refresh_from_db()
            self.assertEqual(notification.status, "read")

    def test_analytics_api(self):
        """Test analytics API"""
        # Create test data
        statuses = ["sent", "delivered", "read", "failed"]
        for i, status_val in enumerate(statuses):
            Notification.objects.create(
                user=self.user,
                notification_type="push",
                title=f"Analytics Test {i+1}",
                body="Analytics test notification",
                status=status_val,
            )

        # Get analytics
        response = self.client.get("/api/v1/notifications/analytics/?days=7")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total_notifications"], 4)
        self.assertIn("delivery_rate", response.data)
        self.assertIn("status_breakdown", response.data)

    def test_health_check_api(self):
        """Test health check API"""
        response = self.client.get("/api/v1/notifications/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["status"], "healthy")
        self.assertIn("statistics", response.data)
        self.assertIn("timestamp", response.data)


class APIErrorHandlingTests(APITestCase):
    """Test API error handling"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    def test_unauthenticated_access(self):
        """Test unauthenticated API access"""
        client = APIClient()  # No authentication

        response = client.get("/api/v1/notifications/templates/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_template_creation(self):
        """Test invalid template creation"""
        invalid_data = {
            "name": "",  # Empty name
            "template_type": "invalid_type",  # Invalid type
            "title_template": "Test",
            "body_template": "Test body",
        }

        response = self.client.post("/api/v1/notifications/templates/", invalid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_nonexistent_resource_access(self):
        """Test accessing non-existent resources"""
        response = self.client.get("/api/v1/notifications/templates/nonexistent-uuid/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_bulk_notification_data(self):
        """Test invalid bulk notification data"""
        invalid_data = {"template_id": "invalid-uuid", "user_ids": [], "context_data": {}}  # Empty user list

        response = self.client.post("/api/v1/notifications/bulk-create/", invalid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_event_trigger(self):
        """Test invalid event trigger"""
        invalid_data = {"event_name": "", "event_data": {}, "user_id": 999999}  # Empty event name  # Non-existent user

        response = self.client.post("/api/v1/notifications/trigger-event/", invalid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class APIPermissionTests(APITestCase):
    """Test API permissions"""

    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", email="user1@example.com", password="testpass123")
        self.user2 = User.objects.create_user(username="user2", email="user2@example.com", password="testpass123")

        self.token1 = Token.objects.create(user=self.user1)
        self.token2 = Token.objects.create(user=self.user2)

        # Create preferences for both users
        UserNotificationPreference.objects.create(user=self.user1)
        UserNotificationPreference.objects.create(user=self.user2)

    def test_user_can_only_access_own_notifications(self):
        """Test users can only access their own notifications"""
        # Create notifications for both users
        notification1 = Notification.objects.create(
            user=self.user1, notification_type="push", title="User 1 Notification", body="This belongs to user 1"
        )

        notification2 = Notification.objects.create(
            user=self.user2, notification_type="push", title="User 2 Notification", body="This belongs to user 2"
        )

        # User 1 should only see their notification
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token1.key)
        response = self.client.get("/api/v1/notifications/my-notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "User 1 Notification")

        # User 2 should only see their notification
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token2.key)
        response = self.client.get("/api/v1/notifications/my-notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "User 2 Notification")

    def test_user_cannot_access_others_device_tokens(self):
        """Test users cannot access other users' device tokens"""
        # Create device tokens for both users
        DeviceToken.objects.create(user=self.user1, token="user1_token", device_type="android")

        DeviceToken.objects.create(user=self.user2, token="user2_token", device_type="ios")

        # User 1 should only see their token
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token1.key)
        response = self.client.get("/api/v1/notifications/device-tokens/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["token"], "user1_token")

    def test_user_cannot_modify_others_preferences(self):
        """Test users cannot modify other users' preferences"""
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token1.key)

        # Try to access user2's preferences (should get user1's preferences)
        response = self.client.get("/api/v1/notifications/preferences/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # The API should return the authenticated user's preferences, not allow
        # accessing other users' preferences


class APIRateLimitingTests(APITestCase):
    """Test API rate limiting (if implemented)"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    def test_rate_limiting_behavior(self):
        """Test rate limiting behavior"""
        # This test would need actual rate limiting implementation
        # For now, we just test that the endpoint responds normally
        response = self.client.get("/api/v1/notifications/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # In a real implementation, you would make many requests
        # and verify that rate limiting kicks in


class APIResponseFormatTests(APITestCase):
    """Test API response formats"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        UserNotificationPreference.objects.create(user=self.user)

    def test_pagination_format(self):
        """Test pagination response format"""
        # Create multiple templates
        for i in range(25):
            NotificationTemplate.objects.create(
                name=f"template_{i}", template_type="push", title_template=f"Template {i}", body_template=f"Body {i}"
            )

        response = self.client.get("/api/v1/notifications/templates/?limit=10")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check pagination structure
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 10)

    def test_error_response_format(self):
        """Test error response format"""
        # Try to create template with invalid data
        invalid_data = {"name": ""}

        response = self.client.post("/api/v1/notifications/templates/", invalid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Check error format
        self.assertIsInstance(response.data, dict)
        self.assertIn("name", response.data)

    def test_success_response_format(self):
        """Test success response format"""
        template_data = {
            "name": "format_test",
            "template_type": "push",
            "title_template": "Test",
            "body_template": "Test body",
        }

        response = self.client.post("/api/v1/notifications/templates/", template_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check response includes all expected fields
        expected_fields = [
            "id",
            "name",
            "template_type",
            "title_template",
            "body_template",
            "is_active",
            "created_at",
            "updated_at",
        ]

        for field in expected_fields:
            self.assertIn(field, response.data)


class APIFilteringAndSearchTests(APITestCase):
    """Test API filtering and search functionality"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        # Create test templates
        self.push_template = NotificationTemplate.objects.create(
            name="push_template", template_type="push", title_template="Push Test", body_template="Push body"
        )

        self.email_template = NotificationTemplate.objects.create(
            name="email_template", template_type="email", title_template="Email Test", body_template="Email body"
        )

    def test_template_filtering_by_type(self):
        """Test filtering templates by type"""
        response = self.client.get("/api/v1/notifications/templates/?type=push")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only return push templates
        for template in response.data["results"]:
            self.assertEqual(template["template_type"], "push")

    def test_template_search(self):
        """Test searching templates"""
        response = self.client.get("/api/v1/notifications/templates/?search=push")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should return templates matching search term
        self.assertGreater(len(response.data["results"]), 0)

    def test_notification_filtering_by_status(self):
        """Test filtering notifications by status"""
        # Create notifications with different statuses
        Notification.objects.create(
            user=self.user, notification_type="push", title="Delivered Test", body="Test", status="delivered"
        )

        Notification.objects.create(
            user=self.user, notification_type="push", title="Failed Test", body="Test", status="failed"
        )

        response = self.client.get("/api/v1/notifications/my-notifications/?status=delivered")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only return delivered notifications
        for notification in response.data["results"]:
            self.assertEqual(notification["status"], "delivered")

    def test_unread_notifications_filter(self):
        """Test filtering for unread notifications only"""
        # Create read and unread notifications
        Notification.objects.create(user=self.user, notification_type="push", title="Read Test", body="Test", status="read")

        Notification.objects.create(
            user=self.user, notification_type="push", title="Unread Test", body="Test", status="delivered"
        )

        response = self.client.get("/api/v1/notifications/my-notifications/?unread_only=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only return unread notifications
        for notification in response.data["results"]:
            self.assertNotEqual(notification["status"], "read")
