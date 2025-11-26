"""
Tests for middleware and permissions in external delivery system
"""

import time
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APITestCase, force_authenticate

from .middleware.auth import ExternalAPIAuthentication, ExternalAPIMiddleware
from .middleware.rate_limit import ExternalAPIRateLimit
from .models import (
    APIUsageLog,
    ExternalBusiness,
    ExternalBusinessPlan,
    ExternalBusinessStatus,
    RateLimitLog,
)
from .permissions import IsExternalBusinessOwner, IsInternalStaff


class ExternalAPIAuthenticationTest(TestCase):
    """Test external API authentication class"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.auth = ExternalAPIAuthentication()

        self.business = ExternalBusiness.objects.create(
            business_name="Auth Test Business",
            business_email="auth@test.com",
            contact_person="Auth User",
            contact_phone="+1234567890",
            business_address="123 Auth St",
            plan=ExternalBusinessPlan.STARTER,
            status=ExternalBusinessStatus.APPROVED,
        )

    def test_authentication_with_valid_api_key(self):
        """Test authentication with valid API key"""
        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = self.business.api_key

        user, token = self.auth.authenticate(request)

        self.assertIsInstance(user, AnonymousUser)
        self.assertIsNone(token)
        self.assertEqual(request.external_business, self.business)

    def test_authentication_with_invalid_api_key(self):
        """Test authentication with invalid API key"""
        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = "invalid_key"

        from rest_framework.exceptions import AuthenticationFailed

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(request)

    def test_authentication_without_api_key(self):
        """Test authentication without API key"""
        request = self.factory.get("/api/external/deliveries/")

        result = self.auth.authenticate(request)

        self.assertIsNone(result)

    def test_authentication_with_suspended_business(self):
        """Test authentication with suspended business"""
        self.business.status = ExternalBusinessStatus.SUSPENDED
        self.business.save()

        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = self.business.api_key

        from rest_framework.exceptions import AuthenticationFailed

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(request)

    def test_authentication_with_pending_business(self):
        """Test authentication with pending business"""
        self.business.status = ExternalBusinessStatus.PENDING
        self.business.save()

        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = self.business.api_key

        from rest_framework.exceptions import AuthenticationFailed

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(request)


class ExternalAPIMiddlewareTest(TestCase):
    """Test external API middleware"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.middleware = ExternalAPIMiddleware(lambda request: HttpResponse("OK"))

        self.business = ExternalBusiness.objects.create(
            business_name="Middleware Test Business",
            business_email="middleware@test.com",
            contact_person="Middleware User",
            contact_phone="+1234567890",
            business_address="123 Middleware St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
        )

    def test_middleware_processes_external_api_request(self):
        """Test middleware processes external API requests"""
        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = self.business.api_key

        response = self.middleware.process_request(request)

        self.assertIsNone(response)  # No early response
        self.assertEqual(request.external_business, self.business)
        self.assertTrue(hasattr(request, "start_time"))

    def test_middleware_ignores_non_external_requests(self):
        """Test middleware ignores non-external API requests"""
        request = self.factory.get("/api/internal/something/")
        request.META["HTTP_X_API_KEY"] = self.business.api_key

        response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertFalse(hasattr(request, "external_business"))

    def test_middleware_rejects_invalid_api_key(self):
        """Test middleware rejects invalid API key"""
        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = "invalid_key"

        response = self.middleware.process_request(request)

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)

    def test_middleware_logs_api_usage(self):
        """Test middleware logs API usage"""
        request = self.factory.get("/api/external/deliveries/")
        request.META["HTTP_X_API_KEY"] = self.business.api_key

        # Process request
        self.middleware.process_request(request)

        # Mock response
        response = HttpResponse("OK")
        response.status_code = 200

        # Process response (this should log usage)
        with patch("external_delivery.utils.log_api_usage") as mock_log:
            self.middleware.process_response(request, response)
            mock_log.assert_called_once()


class RateLimitMiddlewareTest(TestCase):
    """Test rate limiting middleware"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()

        # Mock get_response function
        def get_response(request):
            return HttpResponse("OK")

        self.middleware = ExternalAPIRateLimit(get_response)

        self.business = ExternalBusiness.objects.create(
            business_name="Rate Limit Test",
            business_email="ratelimit@test.com",
            contact_person="Rate User",
            contact_phone="+1234567890",
            business_address="123 Rate St",
            plan=ExternalBusinessPlan.FREE,  # Lower limits for testing
            status=ExternalBusinessStatus.APPROVED,
        )

    def test_rate_limit_allows_within_limits(self):
        """Test rate limiting allows requests within limits"""
        request = self.factory.get("/api/external/deliveries/")
        request.external_business = self.business
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)

    @patch("external_delivery.utils.log_rate_limit_exceeded")
    def test_rate_limit_blocks_over_limits(self, mock_log):
        """Test rate limiting blocks requests over limits"""
        # Create multiple rate limit logs to simulate exceeded limits
        from django.utils import timezone

        current_time = timezone.now()

        # Create logs for the current minute (simulate hitting minute limit)
        for i in range(20):  # FREE plan minute limit is 10
            RateLimitLog.objects.create(
                external_business=self.business,
                request_ip="127.0.0.1",
                endpoint="/api/external/deliveries/",
                request_count=1,
                time_window="minute",
            )

        request = self.factory.get("/api/external/deliveries/")
        request.external_business = self.business
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        response = self.middleware(request)

        self.assertEqual(response.status_code, 429)
        mock_log.assert_called_once()

    def test_rate_limit_different_ips(self):
        """Test rate limiting is per IP address"""
        request1 = self.factory.get("/api/external/deliveries/")
        request1.external_business = self.business
        request1.META["REMOTE_ADDR"] = "127.0.0.1"

        request2 = self.factory.get("/api/external/deliveries/")
        request2.external_business = self.business
        request2.META["REMOTE_ADDR"] = "192.168.1.1"

        response1 = self.middleware(request1)
        response2 = self.middleware(request2)

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)


class ExternalBusinessOwnerPermissionTest(TestCase):
    """Test IsExternalBusinessOwner permission"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.permission = IsExternalBusinessOwner()

        self.business = ExternalBusiness.objects.create(
            business_name="Permission Test",
            business_email="permission@test.com",
            contact_person="Permission User",
            contact_phone="+1234567890",
            business_address="123 Permission St",
            plan=ExternalBusinessPlan.STARTER,
            status=ExternalBusinessStatus.APPROVED,
        )

        self.other_business = ExternalBusiness.objects.create(
            business_name="Other Business",
            business_email="other@test.com",
            contact_person="Other User",
            contact_phone="+1234567891",
            business_address="456 Other St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
        )

    def test_permission_allows_business_owner(self):
        """Test permission allows business owner"""
        request = self.factory.get("/api/external/deliveries/")
        request.external_business = self.business
        request.user = AnonymousUser()

        # Mock view
        view = Mock()

        has_permission = self.permission.has_permission(request, view)

        self.assertTrue(has_permission)

    def test_permission_denies_different_business(self):
        """Test permission denies different business"""
        request = self.factory.get("/api/external/deliveries/")
        request.external_business = self.other_business
        request.user = AnonymousUser()

        # Mock view that expects self.business
        view = Mock()

        # Mock object-level permission check
        from .models import ExternalDelivery

        delivery = ExternalDelivery.objects.create(
            external_business=self.business,
            external_delivery_id="PERM_001",
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

        has_object_permission = self.permission.has_object_permission(request, view, delivery)

        self.assertFalse(has_object_permission)

    def test_permission_denies_without_external_business(self):
        """Test permission denies requests without external_business"""
        request = self.factory.get("/api/external/deliveries/")
        request.user = AnonymousUser()
        # No external_business attribute

        view = Mock()

        has_permission = self.permission.has_permission(request, view)

        self.assertFalse(has_permission)


class InternalStaffPermissionTest(TestCase):
    """Test IsInternalStaff permission"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.permission = IsInternalStaff()

        # Create staff user
        self.staff_user = User.objects.create_user(
            username="staffuser", email="staff@test.com", password="staffpass123", is_staff=True
        )

        # Create regular user
        self.regular_user = User.objects.create_user(
            username="regularuser", email="regular@test.com", password="regularpass123"
        )

    def test_permission_allows_staff_user(self):
        """Test permission allows staff users"""
        request = self.factory.get("/api/internal/dashboard/")
        request.user = self.staff_user

        view = Mock()

        has_permission = self.permission.has_permission(request, view)

        self.assertTrue(has_permission)

    def test_permission_denies_regular_user(self):
        """Test permission denies regular users"""
        request = self.factory.get("/api/internal/dashboard/")
        request.user = self.regular_user

        view = Mock()

        has_permission = self.permission.has_permission(request, view)

        self.assertFalse(has_permission)

    def test_permission_denies_anonymous_user(self):
        """Test permission denies anonymous users"""
        request = self.factory.get("/api/internal/dashboard/")
        request.user = AnonymousUser()

        view = Mock()

        has_permission = self.permission.has_permission(request, view)

        self.assertFalse(has_permission)


class PermissionIntegrationTest(APITestCase):
    """Integration tests for permissions with views"""

    def setUp(self):
        """Set up test data"""
        self.business = ExternalBusiness.objects.create(
            business_name="Integration Permission Test",
            business_email="intperm@test.com",
            contact_person="Int Perm User",
            contact_phone="+1234567890",
            business_address="123 Int St",
            plan=ExternalBusinessPlan.BUSINESS,
            status=ExternalBusinessStatus.APPROVED,
        )

        self.other_business = ExternalBusiness.objects.create(
            business_name="Other Integration Business",
            business_email="otherint@test.com",
            contact_person="Other Int User",
            contact_phone="+1234567891",
            business_address="456 Other St",
            plan=ExternalBusinessPlan.STARTER,
            status=ExternalBusinessStatus.APPROVED,
        )

        self.staff_user = User.objects.create_user(
            username="intstaff", email="intstaff@test.com", password="staffpass123", is_staff=True
        )

    def test_external_api_access_with_correct_business(self):
        """Test external API access with correct business API key"""
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        response = self.client.get("/api/external/deliveries/")

        # Should not get permission denied
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_external_api_access_with_wrong_business(self):
        """Test external API cannot access other business data"""
        # Create delivery for first business
        delivery_data = {
            "external_delivery_id": "PERM_TEST_001",
            "pickup_name": "Test Pickup",
            "pickup_address": "123 Pickup St",
            "pickup_city": "Kathmandu",
            "pickup_phone": "+9771234567",
            "delivery_name": "Test Customer",
            "delivery_address": "456 Delivery St",
            "delivery_city": "Lalitpur",
            "delivery_phone": "+9777654321",
            "package_description": "Test Package",
            "package_weight": 1.0,
            "delivery_fee": 100.00,
            "package_value": 1500.00,
        }

        # Create delivery as first business
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)
        response = self.client.post("/api/external/deliveries/", delivery_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Try to access deliveries as second business
        self.client.credentials(HTTP_X_API_KEY=self.other_business.api_key)
        response = self.client.get("/api/external/deliveries/")

        # Should only see own deliveries (empty list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_internal_api_access_staff_user(self):
        """Test internal API access for staff users"""
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get("/api/internal/external-delivery/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_internal_api_access_regular_user(self):
        """Test internal API denies regular users"""
        regular_user = User.objects.create_user(
            username="regularint", email="regularint@test.com", password="regularpass123"
        )

        self.client.force_authenticate(user=regular_user)

        response = self.client.get("/api/internal/external-delivery/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_access_with_api_key(self):
        """Test dashboard access with API key authentication"""
        self.client.credentials(HTTP_X_API_KEY=self.business.api_key)

        response = self.client.get("/api/external/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("business_info", response.data)
        self.assertEqual(response.data["business_info"]["id"], self.business.id)
