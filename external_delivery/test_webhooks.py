"""
Webhook testing for external delivery system
"""

import hashlib
import hmac
import json
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    ExternalBusiness,
    ExternalBusinessPlan,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
    WebhookEventType,
    WebhookLog,
)
from .utils import format_webhook_delivery_data, send_webhook_notification


class WebhookUtilsTest(TestCase):
    """Test webhook utility functions"""

    def setUp(self):
        """Set up test data"""
        self.business = ExternalBusiness.objects.create(
            business_name="Webhook Test Business",
            business_email="webhook@test.com",
            contact_person="Webhook User",
            contact_phone="+1234567890",
            business_address="123 Webhook St",
            plan=ExternalBusinessPlan.STARTER,
            status=ExternalBusinessStatus.APPROVED,
            webhook_url="https://test.com/webhook",
        )

        self.delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="WEBHOOK_001",
            pickup_name="Test Pickup",
            pickup_address="123 Pickup St",
            pickup_city="Kathmandu",
            pickup_phone="+9771234567",
            delivery_name="Test Customer",
            delivery_address="456 Delivery St",
            delivery_city="Lalitpur",
            delivery_phone="+9777654321",
            package_description="Test Package",
            package_weight=1.0,
            delivery_fee=100.00,
            package_value=1500.00,
        )

    def test_format_webhook_delivery_data(self):
        """Test webhook data formatting"""
        data = format_webhook_delivery_data(self.delivery)

        self.assertIn("id", data)
        self.assertIn("tracking_number", data)
        self.assertIn("external_delivery_id", data)
        self.assertIn("status", data)
        self.assertIn("pickup_name", data)
        self.assertIn("delivery_name", data)
        self.assertEqual(data["external_delivery_id"], "WEBHOOK_001")

    @patch("requests.post")
    def test_send_webhook_notification_success(self, mock_post):
        """Test successful webhook notification"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        data = format_webhook_delivery_data(self.delivery)
        result = send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_CREATED, data=data, delivery=self.delivery
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)

        # Check webhook was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Verify URL
        self.assertEqual(call_args[1]["url"], self.business.webhook_url)

        # Verify headers
        headers = call_args[1]["headers"]
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("X-Webhook-Signature", headers)

        # Verify signature
        payload = call_args[1]["data"]
        expected_signature = hmac.new(
            self.business.webhook_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.assertEqual(headers["X-Webhook-Signature"], f"sha256={expected_signature}")

    @patch("requests.post")
    def test_send_webhook_notification_failure(self, mock_post):
        """Test webhook notification failure"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        data = format_webhook_delivery_data(self.delivery)
        result = send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_CREATED, data=data, delivery=self.delivery
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 500)

    @patch("requests.post")
    def test_send_webhook_notification_timeout(self, mock_post):
        """Test webhook notification timeout"""
        # Mock timeout exception
        import requests

        mock_post.side_effect = requests.Timeout("Request timeout")

        data = format_webhook_delivery_data(self.delivery)
        result = send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_CREATED, data=data, delivery=self.delivery
        )

        self.assertFalse(result["success"])
        self.assertIn("timeout", result["error"].lower())

    def test_send_webhook_notification_no_url(self):
        """Test webhook notification with no URL configured"""
        self.business.webhook_url = ""
        self.business.save()

        data = format_webhook_delivery_data(self.delivery)
        result = send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_CREATED, data=data, delivery=self.delivery
        )

        self.assertFalse(result["success"])
        self.assertIn("No webhook URL", result["error"])


class WebhookLoggingTest(TestCase):
    """Test webhook logging functionality"""

    def setUp(self):
        """Set up test data"""
        self.business = ExternalBusiness.objects.create(
            business_name="Logging Test Business",
            business_email="logging@test.com",
            contact_person="Logging User",
            contact_phone="+1234567890",
            business_address="123 Logging St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
            webhook_url="https://test.com/webhook",
        )

        self.delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="LOG_001",
            pickup_name="Test Pickup",
            pickup_address="123 Pickup St",
            pickup_city="Kathmandu",
            pickup_phone="+9771234567",
            delivery_name="Test Customer",
            delivery_address="456 Delivery St",
            delivery_city="Lalitpur",
            delivery_phone="+9777654321",
            package_description="Test Package",
            package_weight=1.0,
            delivery_fee=100.00,
            package_value=1500.00,
        )

    @patch("requests.post")
    def test_webhook_logging_success(self, mock_post):
        """Test webhook logging for successful delivery"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        data = format_webhook_delivery_data(self.delivery)
        send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_CREATED, data=data, delivery=self.delivery
        )

        # Check webhook log was created
        webhook_log = WebhookLog.objects.filter(external_business=self.business, delivery=self.delivery).first()

        self.assertIsNotNone(webhook_log)
        self.assertEqual(webhook_log.event_type, WebhookEventType.DELIVERY_CREATED)
        self.assertTrue(webhook_log.success)
        self.assertEqual(webhook_log.response_status_code, 200)

    @patch("requests.post")
    def test_webhook_logging_failure(self, mock_post):
        """Test webhook logging for failed delivery"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response

        data = format_webhook_delivery_data(self.delivery)
        send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_FAILED, data=data, delivery=self.delivery
        )

        # Check webhook log was created
        webhook_log = WebhookLog.objects.filter(external_business=self.business, delivery=self.delivery).first()

        self.assertIsNotNone(webhook_log)
        self.assertEqual(webhook_log.event_type, WebhookEventType.DELIVERY_FAILED)
        self.assertFalse(webhook_log.success)
        self.assertEqual(webhook_log.response_status_code, 404)
        self.assertIn("Not Found", webhook_log.error_message)


class WebhookAPITest(APITestCase):
    """Test webhook-related API endpoints"""

    def setUp(self):
        """Set up test data"""
        self.business = ExternalBusiness.objects.create(
            business_name="API Webhook Test",
            business_email="apiwebhook@test.com",
            contact_person="API User",
            contact_phone="+1234567890",
            business_address="123 API St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
            webhook_url="https://test.com/webhook",
        )

    @patch("requests.post")
    def test_webhook_test_endpoint(self, mock_post):
        """Test webhook test endpoint"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        data = {"webhook_url": "https://test.com/webhook", "event_type": WebhookEventType.DELIVERY_CREATED}

        response = self.client.post("/api/external/webhook/test/", data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("Test webhook sent", response.data["message"])

    def test_webhook_test_endpoint_no_auth(self):
        """Test webhook test endpoint without authentication"""
        data = {"webhook_url": "https://test.com/webhook", "event_type": WebhookEventType.DELIVERY_CREATED}

        response = self.client.post("/api/external/webhook/test/", data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("requests.post")
    def test_webhook_test_endpoint_custom_url(self, mock_post):
        """Test webhook test endpoint with custom URL"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        data = {"webhook_url": "https://custom.com/webhook", "event_type": WebhookEventType.DELIVERY_UPDATED}

        response = self.client.post("/api/external/webhook/test/", data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify custom URL was used
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[1]["url"], "https://custom.com/webhook")


class WebhookSecurityTest(TestCase):
    """Test webhook security features"""

    def setUp(self):
        """Set up test data"""
        self.business = ExternalBusiness.objects.create(
            business_name="Security Test Business",
            business_email="security@test.com",
            contact_person="Security User",
            contact_phone="+1234567890",
            business_address="123 Security St",
            plan=ExternalBusinessPlan.ENTERPRISE,
            status=ExternalBusinessStatus.APPROVED,
            webhook_url="https://test.com/webhook",
        )

        self.delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="SEC_001",
            pickup_name="Test Pickup",
            pickup_address="123 Pickup St",
            pickup_city="Kathmandu",
            pickup_phone="+9771234567",
            delivery_name="Test Customer",
            delivery_address="456 Delivery St",
            delivery_city="Lalitpur",
            delivery_phone="+9777654321",
            package_description="Test Package",
            package_weight=1.0,
            delivery_fee=100.00,
        )

    def test_webhook_signature_generation(self):
        """Test HMAC signature generation for webhooks"""
        data = format_webhook_delivery_data(self.delivery)

        # Create webhook payload
        payload = {
            "event_type": WebhookEventType.DELIVERY_CREATED,
            "timestamp": timezone.now().isoformat(),
            "business_id": str(self.business.id),
            "data": data,
        }

        payload_json = json.dumps(payload, sort_keys=True, default=str)

        # Generate signature
        signature = hmac.new(
            self.business.webhook_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Verify signature format
        self.assertEqual(len(signature), 64)  # SHA256 hex digest length

        # Verify signature is deterministic
        signature2 = hmac.new(
            self.business.webhook_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        self.assertEqual(signature, signature2)

    def test_webhook_signature_verification(self):
        """Test webhook signature verification"""
        # Simulate incoming webhook payload
        payload = {
            "event_type": WebhookEventType.DELIVERY_DELIVERED,
            "timestamp": "2025-11-25T10:00:00Z",
            "business_id": str(self.business.id),
            "data": {"test": "data"},
        }

        payload_json = json.dumps(payload, sort_keys=True)

        # Generate correct signature
        correct_signature = hmac.new(
            self.business.webhook_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Generate incorrect signature
        wrong_secret = "wrong_secret"
        incorrect_signature = hmac.new(
            wrong_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Verify correct signature passes
        self.assertTrue(hmac.compare_digest(correct_signature, correct_signature))

        # Verify incorrect signature fails
        self.assertFalse(hmac.compare_digest(correct_signature, incorrect_signature))

    @patch("requests.post")
    def test_webhook_retry_mechanism(self, mock_post):
        """Test webhook retry mechanism for failed deliveries"""
        # Mock failed response (will trigger retry)
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        data = format_webhook_delivery_data(self.delivery)

        # Send webhook (should fail and create log)
        result = send_webhook_notification(
            business=self.business, event_type=WebhookEventType.DELIVERY_CREATED, data=data, delivery=self.delivery
        )

        self.assertFalse(result["success"])

        # Check that webhook log shows failure (ready for retry)
        webhook_log = WebhookLog.objects.filter(
            external_business=self.business, delivery=self.delivery, success=False
        ).first()

        self.assertIsNotNone(webhook_log)
        self.assertEqual(webhook_log.retry_count, 0)
        self.assertLessEqual(webhook_log.next_retry_at, timezone.now() + timezone.timedelta(minutes=5))


class WebhookIntegrationTest(APITestCase):
    """Integration tests for webhook system"""

    def setUp(self):
        """Set up test data"""
        self.business = ExternalBusiness.objects.create(
            business_name="Integration Test Business",
            business_email="integration@test.com",
            contact_person="Integration User",
            contact_phone="+1234567890",
            business_address="123 Integration St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
            webhook_url="https://integration.test.com/webhook",
        )

    @patch("requests.post")
    @patch("external_delivery.tasks.send_delivery_notifications.delay")
    def test_delivery_creation_triggers_webhook(self, mock_task, mock_post):
        """Test that creating delivery triggers webhook notification"""
        # Mock successful webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        delivery_data = {
            "external_delivery_id": "INTEGRATION_001",
            "pickup_name": "Integration Pickup",
            "pickup_address": "123 Pickup St",
            "pickup_city": "Kathmandu",
            "pickup_phone": "+9771234567",
            "delivery_name": "Integration Customer",
            "delivery_address": "456 Delivery St",
            "delivery_city": "Lalitpur",
            "delivery_phone": "+9777654321",
            "package_description": "Integration Package",
            "package_weight": 2.0,
            "delivery_fee": 200.00,
        }

        response = self.client.post("/api/external/deliveries/", delivery_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify that webhook notification task was queued
        mock_task.assert_called_once()

        # Verify delivery was created
        delivery = ExternalDelivery.objects.get(external_delivery_id="INTEGRATION_001")
        self.assertEqual(delivery.external_business, self.business)
        self.assertEqual(delivery.status, ExternalDeliveryStatus.PENDING)
