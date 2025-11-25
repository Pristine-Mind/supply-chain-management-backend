import os

import django

# Django settings for testing
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import (
    ExternalBusiness,
    ExternalBusinessPlan,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
)
from .utils import calculate_delivery_stats, validate_delivery_data


class ExternalBusinessModelTest(TestCase):
    """Test external business model"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_create_external_business(self):
        """Test creating an external business"""
        business = ExternalBusiness.objects.create(
            business_name="Test Business",
            business_email="business@test.com",
            contact_person="John Doe",
            contact_phone="+1234567890",
            business_address="123 Test St",
            plan=ExternalBusinessPlan.STARTER,
        )

        self.assertEqual(business.business_name, "Test Business")
        self.assertTrue(business.api_key.startswith("ext_"))
        self.assertEqual(len(business.webhook_secret), 32)
        self.assertEqual(business.status, ExternalBusinessStatus.PENDING)

    def test_api_key_generation(self):
        """Test API key generation"""
        business = ExternalBusiness.objects.create(
            business_name="Test Business",
            business_email="business@test.com",
            contact_person="John Doe",
            contact_phone="+1234567890",
            business_address="123 Test St",
        )

        old_api_key = business.api_key
        new_api_key = business.generate_api_key()

        self.assertNotEqual(old_api_key, new_api_key)
        self.assertTrue(new_api_key.startswith("ext_"))

    def test_delivery_limits(self):
        """Test delivery limit checking"""
        business = ExternalBusiness.objects.create(
            business_name="Test Business",
            business_email="business@test.com",
            contact_person="John Doe",
            contact_phone="+1234567890",
            business_address="123 Test St",
            plan=ExternalBusinessPlan.FREE,
            status=ExternalBusinessStatus.APPROVED,
        )

        # Create 5 deliveries for this month
        for i in range(5):
            ExternalDelivery.objects.create(
                external_business=business,
                external_delivery_id=f"test_{i}",
                pickup_name="Test Pickup",
                pickup_phone="+1234567890",
                pickup_address="123 Pickup St",
                pickup_city="Test City",
                delivery_name="Test Delivery",
                delivery_phone="+1234567890",
                delivery_address="456 Delivery St",
                delivery_city="Test City",
                package_description="Test Package",
                package_weight=Decimal("1.0"),
                package_value=Decimal("100.0"),
            )

        # Should still be able to create (under limit)
        can_create, message = business.can_create_delivery()
        self.assertTrue(can_create)

        # Create 95 more deliveries to hit the limit
        for i in range(95):
            ExternalDelivery.objects.create(
                external_business=business,
                external_delivery_id=f"test_limit_{i}",
                pickup_name="Test Pickup",
                pickup_phone="+1234567890",
                pickup_address="123 Pickup St",
                pickup_city="Test City",
                delivery_name="Test Delivery",
                delivery_phone="+1234567890",
                delivery_address="456 Delivery St",
                delivery_city="Test City",
                package_description="Test Package",
                package_weight=Decimal("1.0"),
                package_value=Decimal("100.0"),
            )

        # Should now be at limit
        can_create, message = business.can_create_delivery()
        self.assertFalse(can_create)
        self.assertIn("limit exceeded", message)


class ExternalDeliveryModelTest(TestCase):
    """Test external delivery model"""

    def setUp(self):
        self.business = ExternalBusiness.objects.create(
            business_name="Test Business",
            business_email="business@test.com",
            contact_person="John Doe",
            contact_phone="+1234567890",
            business_address="123 Test St",
            status=ExternalBusinessStatus.APPROVED,
        )

    def test_create_external_delivery(self):
        """Test creating an external delivery"""
        delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="test_001",
            pickup_name="Test Pickup",
            pickup_phone="+1234567890",
            pickup_address="123 Pickup St",
            pickup_city="Test City",
            delivery_name="Test Delivery",
            delivery_phone="+1234567890",
            delivery_address="456 Delivery St",
            delivery_city="Test City",
            package_description="Test Package",
            package_weight=Decimal("1.0"),
            package_value=Decimal("100.0"),
        )

        self.assertEqual(delivery.external_business, self.business)
        self.assertTrue(delivery.tracking_number.startswith("EXT"))
        self.assertEqual(delivery.status, ExternalDeliveryStatus.PENDING)

    def test_delivery_fee_calculation(self):
        """Test delivery fee calculation"""
        delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="test_fee",
            pickup_name="Test Pickup",
            pickup_phone="+1234567890",
            pickup_address="123 Pickup St",
            pickup_city="Test City",
            delivery_name="Test Delivery",
            delivery_phone="+1234567890",
            delivery_address="456 Delivery St",
            delivery_city="Another City",  # Different city for higher fee
            package_description="Test Package",
            package_weight=Decimal("2.0"),
            package_value=Decimal("500.0"),
        )

        fees = delivery.calculate_delivery_fee()

        self.assertIn("delivery_fee", fees)
        self.assertIn("platform_commission", fees)
        self.assertIn("transporter_earnings", fees)

        # Check that platform commission is 20% of delivery fee
        expected_commission = fees["delivery_fee"] * Decimal("0.20")
        self.assertEqual(fees["platform_commission"], expected_commission)

    def test_delivery_cancellation(self):
        """Test delivery cancellation logic"""
        delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="test_cancel",
            pickup_name="Test Pickup",
            pickup_phone="+1234567890",
            pickup_address="123 Pickup St",
            pickup_city="Test City",
            delivery_name="Test Delivery",
            delivery_phone="+1234567890",
            delivery_address="456 Delivery St",
            delivery_city="Test City",
            package_description="Test Package",
            package_weight=Decimal("1.0"),
            package_value=Decimal("100.0"),
        )

        # Should be able to cancel when pending
        self.assertTrue(delivery.can_cancel())

        # Change status to picked up
        delivery.status = ExternalDeliveryStatus.PICKED_UP
        delivery.save()

        # Should not be able to cancel when picked up
        self.assertFalse(delivery.can_cancel())


class ExternalBusinessAPITest(APITestCase):
    """Test external business API endpoints"""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )
        self.client = APIClient()

    def test_register_external_business(self):
        """Test external business registration"""
        data = {
            "business_name": "Test API Business",
            "business_email": "api@test.com",
            "contact_person": "Jane Doe",
            "contact_phone": "+1234567890",
            "business_address": "789 API St",
            "website": "https://test.com",
        }

        response = self.client.post("/api/public/external-delivery/register/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check business was created
        business = ExternalBusiness.objects.get(business_email="api@test.com")
        self.assertEqual(business.business_name, "Test API Business")
        self.assertEqual(business.status, ExternalBusinessStatus.PENDING)


class ExternalDeliveryAPITest(APITestCase):
    """Test external delivery API endpoints"""

    def setUp(self):
        self.business = ExternalBusiness.objects.create(
            business_name="Test API Business",
            business_email="api@test.com",
            contact_person="Jane Doe",
            contact_phone="+1234567890",
            business_address="789 API St",
            status=ExternalBusinessStatus.APPROVED,
        )
        self.client = APIClient()
        # Set API key header
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

    def test_create_delivery_with_api_key(self):
        """Test creating delivery with API key"""
        data = {
            "external_delivery_id": "api_test_001",
            "pickup_name": "API Pickup",
            "pickup_phone": "+1234567890",
            "pickup_address": "123 API Pickup St",
            "pickup_city": "API City",
            "delivery_name": "API Delivery",
            "delivery_phone": "+1234567890",
            "delivery_address": "456 API Delivery St",
            "delivery_city": "API City",
            "package_description": "API Test Package",
            "package_weight": "1.5",
            "package_value": "200.00",
        }

        response = self.client.post("/api/external/deliveries/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check delivery was created
        delivery = ExternalDelivery.objects.get(external_delivery_id="api_test_001")
        self.assertEqual(delivery.external_business, self.business)
        self.assertIsNotNone(delivery.tracking_number)

    def test_list_deliveries_with_api_key(self):
        """Test listing deliveries with API key"""
        # Create a test delivery
        ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="list_test_001",
            pickup_name="Test Pickup",
            pickup_phone="+1234567890",
            pickup_address="123 Pickup St",
            pickup_city="Test City",
            delivery_name="Test Delivery",
            delivery_phone="+1234567890",
            delivery_address="456 Delivery St",
            delivery_city="Test City",
            package_description="Test Package",
            package_weight=Decimal("1.0"),
            package_value=Decimal("100.0"),
        )

        response = self.client.get("/api/external/deliveries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only see deliveries for this business
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["external_delivery_id"], "list_test_001")


class UtilityFunctionsTest(TestCase):
    """Test utility functions"""

    def test_calculate_delivery_stats(self):
        """Test delivery statistics calculation"""
        business = ExternalBusiness.objects.create(
            business_name="Stats Test Business",
            business_email="stats@test.com",
            contact_person="Stats Tester",
            contact_phone="+1234567890",
            business_address="123 Stats St",
        )

        # Create test deliveries with different statuses
        ExternalDelivery.objects.create(
            external_business=business,
            external_delivery_id="stats_001",
            pickup_name="Test",
            pickup_phone="+1234567890",
            pickup_address="123 St",
            pickup_city="City",
            delivery_name="Test",
            delivery_phone="+1234567890",
            delivery_address="456 St",
            delivery_city="City",
            package_description="Test",
            package_weight=Decimal("1.0"),
            package_value=Decimal("100.0"),
            status=ExternalDeliveryStatus.DELIVERED,
            platform_commission=Decimal("20.00"),
        )

        ExternalDelivery.objects.create(
            external_business=business,
            external_delivery_id="stats_002",
            pickup_name="Test",
            pickup_phone="+1234567890",
            pickup_address="123 St",
            pickup_city="City",
            delivery_name="Test",
            delivery_phone="+1234567890",
            delivery_address="456 St",
            delivery_city="City",
            package_description="Test",
            package_weight=Decimal("1.0"),
            package_value=Decimal("150.0"),
            status=ExternalDeliveryStatus.FAILED,
        )

        stats = calculate_delivery_stats(business)

        self.assertEqual(stats["total_deliveries"], 2)
        self.assertEqual(stats["successful_deliveries"], 1)
        self.assertEqual(stats["failed_deliveries"], 1)
        self.assertEqual(stats["total_revenue"], Decimal("20.00"))

    def test_validate_delivery_data(self):
        """Test delivery data validation"""
        business = ExternalBusiness.objects.create(
            business_name="Validation Test Business",
            business_email="validation@test.com",
            contact_person="Validation Tester",
            contact_phone="+1234567890",
            business_address="123 Validation St",
            max_delivery_value=Decimal("5000.00"),
            allowed_pickup_cities=["City A", "City B"],
            allowed_delivery_cities=["City X", "City Y"],
        )

        # Valid data
        valid_data = {
            "package_value": Decimal("1000.00"),
            "pickup_city": "City A",
            "delivery_city": "City X",
            "is_cod": False,
            "cod_amount": None,
        }

        errors = validate_delivery_data(valid_data, business)
        self.assertEqual(len(errors), 0)

        # Invalid data - exceeds value limit
        invalid_data = {
            "package_value": Decimal("6000.00"),
            "pickup_city": "City C",  # Not allowed
            "delivery_city": "City Z",  # Not allowed
            "is_cod": True,
            "cod_amount": None,  # COD without amount
        }

        errors = validate_delivery_data(invalid_data, business)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("exceeds maximum" in error for error in errors))
        self.assertTrue(any("not allowed" in error for error in errors))
        self.assertTrue(any("COD amount" in error for error in errors))


if __name__ == "__main__":
    # Run tests
    import unittest

    unittest.main()
