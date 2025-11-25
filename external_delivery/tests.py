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

    def test_validate_delivery_data_edge_cases(self):
        """Test delivery data validation edge cases"""
        business = ExternalBusiness.objects.create(
            business_name="Edge Case Test Business",
            business_email="edgecase@test.com",
            contact_person="Edge Tester",
            contact_phone="+1234567890",
            business_address="123 Edge St",
            max_delivery_value=Decimal("1000.00"),
        )

        # COD amount greater than package value
        invalid_cod_data = {
            "package_value": Decimal("100.00"),
            "is_cod": True,
            "cod_amount": Decimal("150.00"),  # Greater than package value
        }

        errors = validate_delivery_data(invalid_cod_data, business)
        self.assertTrue(any("COD amount cannot be greater" in error for error in errors))

        # Valid COD data
        valid_cod_data = {
            "package_value": Decimal("200.00"),
            "is_cod": True,
            "cod_amount": Decimal("180.00"),  # Less than package value
        }

        errors = validate_delivery_data(valid_cod_data, business)
        cod_errors = [error for error in errors if "COD amount cannot be greater" in error]
        self.assertEqual(len(cod_errors), 0)

        # Invalid string values
        invalid_string_data = {
            "package_value": "invalid",
            "is_cod": True,
            "cod_amount": "also_invalid",
        }

        errors = validate_delivery_data(invalid_string_data, business)
        self.assertTrue(any("Invalid package value" in error for error in errors))
        self.assertTrue(any("Invalid COD amount" in error for error in errors))


class ExternalBusinessAuthenticationTest(APITestCase):
    """Test authentication functionality for external businesses"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create approved business
        self.business = ExternalBusiness.objects.create(
            business_name="Test Auth Business",
            business_email="auth@test.com",
            contact_person="Auth User",
            contact_phone="+1234567890",
            business_address="123 Auth St",
            plan=ExternalBusinessPlan.STARTER,
            status=ExternalBusinessStatus.APPROVED,
        )

        # Create pending business
        self.pending_business = ExternalBusiness.objects.create(
            business_name="Pending Business",
            business_email="pending@test.com",
            contact_person="Pending User",
            contact_phone="+1234567891",
            business_address="123 Pending St",
            plan=ExternalBusinessPlan.FREE,
            status=ExternalBusinessStatus.PENDING,
        )

    def test_business_registration(self):
        """Test external business registration"""
        data = {
            "business_name": "New Test Business",
            "business_email": "new@test.com",
            "contact_person": "New User",
            "contact_phone": "+1234567892",
            "business_address": "123 New St",
            "website": "https://newtest.com",
            "webhook_url": "https://newtest.com/webhook",
        }

        response = self.client.post("/api/public/external-delivery/register/", data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("Registration submitted successfully", response.data["message"])

        # Check business was created
        business = ExternalBusiness.objects.get(business_email="new@test.com")
        self.assertEqual(business.status, ExternalBusinessStatus.PENDING)
        self.assertTrue(business.api_key.startswith("ext_"))

    def test_account_setup_success(self):
        """Test successful account setup"""
        data = {"api_key": self.business.api_key, "password": "SecurePass123!", "confirm_password": "SecurePass123!"}

        response = self.client.post("/api/public/external-delivery/auth/setup/", data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Account setup successful", response.data["message"])

        # Check user was created and linked
        self.business.refresh_from_db()
        self.assertIsNotNone(self.business.user)
        self.assertEqual(self.business.user.email, self.business.business_email)

    def test_account_setup_invalid_api_key(self):
        """Test account setup with invalid API key"""
        data = {"api_key": "invalid_key", "password": "SecurePass123!", "confirm_password": "SecurePass123!"}

        response = self.client.post("/api/public/external-delivery/auth/setup/", data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Invalid API key", response.data["error"])

    def test_account_setup_pending_business(self):
        """Test account setup for pending business"""
        data = {"api_key": self.pending_business.api_key, "password": "SecurePass123!", "confirm_password": "SecurePass123!"}

        response = self.client.post("/api/public/external-delivery/auth/setup/", data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("not approved", response.data["error"])

    def test_account_setup_password_mismatch(self):
        """Test account setup with password mismatch"""
        data = {"api_key": self.business.api_key, "password": "SecurePass123!", "confirm_password": "DifferentPass456!"}

        response = self.client.post("/api/public/external-delivery/auth/setup/", data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Passwords do not match", response.data["error"])

    def test_login_success(self):
        """Test successful login"""
        # Setup account first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="SecurePass123!"
        )
        self.business.user = user
        self.business.save()

        data = {"email": self.business.business_email, "password": "SecurePass123!"}

        response = self.client.post("/api/public/external-delivery/auth/login/", data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertIn("business", response.data)
        self.assertEqual(response.data["business"]["id"], self.business.id)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        # Setup account first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="SecurePass123!"
        )
        self.business.user = user
        self.business.save()

        data = {"email": self.business.business_email, "password": "WrongPassword!"}

        response = self.client.post("/api/public/external-delivery/auth/login/", data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("Invalid credentials", response.data["error"])

    def test_login_no_account_setup(self):
        """Test login without account setup"""
        data = {"email": self.business.business_email, "password": "SecurePass123!"}

        response = self.client.post("/api/public/external-delivery/auth/login/", data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("complete your account setup", response.data["error"])

    def test_login_business_not_found(self):
        """Test login with non-existent business"""
        data = {"email": "nonexistent@test.com", "password": "SecurePass123!"}

        response = self.client.post("/api/public/external-delivery/auth/login/", data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Business not found", response.data["error"])

    def test_token_refresh(self):
        """Test JWT token refresh"""
        # Setup account and login first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="SecurePass123!"
        )
        self.business.user = user
        self.business.save()

        # Login to get tokens
        login_data = {"email": self.business.business_email, "password": "SecurePass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        refresh_token = login_response.data["refresh_token"]

        # Test token refresh
        refresh_data = {"refresh_token": refresh_token}
        response = self.client.post("/api/public/external-delivery/auth/refresh/", refresh_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertIn("expires_in", response.data)

    def test_token_refresh_invalid_token(self):
        """Test token refresh with invalid token"""
        data = {"refresh_token": "invalid_refresh_token"}
        response = self.client.post("/api/public/external-delivery/auth/refresh/", data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("Invalid or expired", response.data["error"])

    def test_logout_success(self):
        """Test successful logout"""
        # Setup account and login first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="SecurePass123!"
        )
        self.business.user = user
        self.business.save()

        # Login to get tokens
        login_data = {"email": self.business.business_email, "password": "SecurePass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        access_token = login_response.data["access_token"]
        refresh_token = login_response.data["refresh_token"]

        # Test logout
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        logout_data = {"refresh_token": refresh_token}
        response = self.client.post("/api/public/external-delivery/auth/logout/", logout_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Successfully logged out", response.data["message"])

    def test_profile_access(self):
        """Test profile access with JWT token"""
        # Setup account and login first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="SecurePass123!"
        )
        self.business.user = user
        self.business.save()

        # Login to get token
        login_data = {"email": self.business.business_email, "password": "SecurePass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        access_token = login_response.data["access_token"]

        # Test profile access
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get("/api/public/external-delivery/auth/profile/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("business", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["business"]["id"], self.business.id)

    def test_change_password_success(self):
        """Test successful password change"""
        # Setup account and login first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="OldPass123!"
        )
        self.business.user = user
        self.business.save()

        # Login to get token
        login_data = {"email": self.business.business_email, "password": "OldPass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        access_token = login_response.data["access_token"]

        # Test password change
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        change_data = {"current_password": "OldPass123!", "new_password": "NewPass456!", "confirm_password": "NewPass456!"}
        response = self.client.post("/api/public/external-delivery/auth/change-password/", change_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Password changed successfully", response.data["message"])

        # Verify new password works
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass456!"))

    def test_change_password_wrong_current(self):
        """Test password change with wrong current password"""
        # Setup account and login first
        user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="OldPass123!"
        )
        self.business.user = user
        self.business.save()

        # Login to get token
        login_data = {"email": self.business.business_email, "password": "OldPass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        access_token = login_response.data["access_token"]

        # Test password change with wrong current password
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        change_data = {"current_password": "WrongOldPass!", "new_password": "NewPass456!", "confirm_password": "NewPass456!"}
        response = self.client.post("/api/public/external-delivery/auth/change-password/", change_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Current password is incorrect", response.data["error"])

    def test_password_reset_request(self):
        """Test password reset request"""
        data = {"email": self.business.business_email, "api_key": self.business.api_key}

        response = self.client.post("/api/public/external-delivery/auth/reset-password/", data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Password reset instructions", response.data["message"])

    def test_password_reset_invalid_email(self):
        """Test password reset with invalid email"""
        data = {"email": "nonexistent@test.com"}

        response = self.client.post("/api/public/external-delivery/auth/reset-password/", data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Business not found", response.data["error"])


class APIKeyAuthenticationTest(APITestCase):
    """Test API key authentication for external deliveries"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create approved business
        self.business = ExternalBusiness.objects.create(
            business_name="API Test Business",
            business_email="api@test.com",
            contact_person="API User",
            contact_phone="+1234567890",
            business_address="123 API St",
            plan=ExternalBusinessPlan.STARTER,
            status=ExternalBusinessStatus.APPROVED,
        )

        # Create suspended business
        self.suspended_business = ExternalBusiness.objects.create(
            business_name="Suspended Business",
            business_email="suspended@test.com",
            contact_person="Suspended User",
            contact_phone="+1234567891",
            business_address="123 Suspended St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.SUSPENDED,
        )

    def test_api_key_authentication_success(self):
        """Test successful API key authentication"""
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        # Test accessing external deliveries endpoint
        response = self.client.get("/api/external/deliveries/")

        # Should not get authentication error
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_key_authentication_invalid_key(self):
        """Test authentication with invalid API key"""
        self.client.credentials(HTTP_X_API_KEY="invalid_api_key")

        response = self.client.get("/api/external/deliveries/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_key_authentication_suspended_business(self):
        """Test authentication with suspended business API key"""
        self.client.credentials(HTTP_X_API_KEY=self.suspended_business.api_key)

        response = self.client.get("/api/external/deliveries/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_key_authentication_no_key(self):
        """Test authentication without API key"""
        response = self.client.get("/api/external/deliveries/")

        # Should use other authentication methods or deny access
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_create_delivery_with_api_key(self):
        """Test creating delivery with API key authentication"""
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        delivery_data = {
            "external_delivery_id": "API_TEST_001",
            "pickup_name": "API Test Pickup",
            "pickup_address": "123 Pickup St",
            "pickup_city": "Kathmandu",
            "pickup_phone": "+9771234567",
            "delivery_name": "API Test Customer",
            "delivery_address": "456 Delivery St",
            "delivery_city": "Lalitpur",
            "delivery_phone": "+9777654321",
            "package_description": "API Test Package",
            "package_weight": 1.5,
            "delivery_fee": 150.00,
            "package_value": 2000.00,
        }

        response = self.client.post("/api/external/deliveries/", delivery_data)

        # Should successfully create delivery
        print(response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("tracking_number", response.data)

    def test_dashboard_access_with_api_key(self):
        """Test dashboard access with API key"""
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        response = self.client.get("/api/external/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("business_info", response.data)


class MixedAuthenticationTest(APITestCase):
    """Test mixed authentication scenarios"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create business with user account
        self.business = ExternalBusiness.objects.create(
            business_name="Mixed Auth Business",
            business_email="mixed@test.com",
            contact_person="Mixed User",
            contact_phone="+1234567890",
            business_address="123 Mixed St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
        )

        # Create user account
        self.user = User.objects.create_user(
            username=f"ext_business_{self.business.id}", email=self.business.business_email, password="SecurePass123!"
        )
        self.business.user = self.user
        self.business.save()

    def test_jwt_and_api_key_both_work(self):
        """Test that both JWT and API key authentication work"""
        # Test API key
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)
        response1 = self.client.get("/api/external/deliveries/")
        self.assertNotEqual(response1.status_code, status.HTTP_401_UNAUTHORIZED)

        # Clear credentials
        self.client.credentials()

        # Login to get JWT token
        login_data = {"email": self.business.business_email, "password": "SecurePass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        access_token = login_response.data["access_token"]

        # Test JWT token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response2 = self.client.get("/api/external/dashboard/")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_api_key_takes_precedence(self):
        """Test that API key authentication takes precedence over JWT"""
        # Login to get JWT token
        login_data = {"email": self.business.business_email, "password": "SecurePass123!"}
        login_response = self.client.post("/api/public/external-delivery/auth/login/", login_data)
        access_token = login_response.data["access_token"]

        # Set both API key and JWT token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}", HTTP_X_API_KEY=self.business.api_key)

        response = self.client.get("/api/external/deliveries/")

        # Should work and use API key authentication
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_jwt_with_valid_api_key(self):
        """Test invalid JWT with valid API key"""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid_jwt_token", HTTP_X_API_KEY=self.business.api_key)

        response = self.client.get("/api/external/deliveries/")

        # Should work because API key is valid
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


if __name__ == "__main__":
    # Run tests
    import unittest

    unittest.main()
