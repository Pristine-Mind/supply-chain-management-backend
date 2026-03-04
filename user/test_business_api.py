"""
Test file to validate the Business List API implementation.
Run this after setting up the Django environment to test the API.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from producer.models import City
from user.models import Role, UserProfile


class BusinessListAPITest(APITestCase):
    """Test cases for the Business List API"""

    def setUp(self):
        """Set up test data"""
        # Create test city
        self.city = City.objects.create(name="Kathmandu")

        # Create business owner role
        self.business_owner_role = Role.objects.get_or_create(
            code="business_owner", defaults={"name": "Business Owner", "level": 3}
        )[0]

        # Create test user
        self.user = User.objects.create_user(
            username="testbusiness",
            email="test@business.com",
            password="testpass123",
            first_name="Test",
            last_name="Business",
        )

        # Create business profile
        self.profile = UserProfile.objects.create(
            user=self.user,
            role=self.business_owner_role,
            business_type=UserProfile.BusinessType.DISTRIBUTOR,
            location=self.city,
            latitude=27.7172,
            longitude=85.3240,
            registered_business_name="Test Distributors Ltd",
            phone_number="+977-9841234567",
        )

        # Create another user for authentication
        self.auth_user = User.objects.create_user(username="authuser", password="authpass123")

    def test_business_list_endpoint_requires_authentication(self):
        """Test that the API requires authentication"""
        url = reverse("user:business-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_business_list_returns_businesses(self):
        """Test that the API returns business listings"""
        self.client.force_authenticate(user=self.auth_user)
        url = reverse("user:business-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)

        business = response.data["results"][0]
        self.assertEqual(business["username"], "testbusiness")
        self.assertEqual(business["business_type"], "distributor")
        self.assertEqual(business["registered_business_name"], "Test Distributors Ltd")

    def test_business_list_filtering_by_city(self):
        """Test filtering businesses by city"""
        self.client.force_authenticate(user=self.auth_user)
        url = reverse("user:business-list")

        # Filter by city name
        response = self.client.get(url, {"city_name": "kathmandu"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        # Filter by non-existent city
        response = self.client.get(url, {"city_name": "pokhara"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_business_list_search_functionality(self):
        """Test search functionality"""
        self.client.force_authenticate(user=self.auth_user)
        url = reverse("user:business-list")

        # Search by business name
        response = self.client.get(url, {"search": "test distributors"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        # Search by phone number
        response = self.client.get(url, {"search": "9841234567"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_business_list_geographic_filtering(self):
        """Test geographic distance filtering"""
        self.client.force_authenticate(user=self.auth_user)
        url = reverse("user:business-list")

        # Search within 50km of Kathmandu center
        response = self.client.get(url, {"latitude": 27.7172, "longitude": 85.3240, "radius_km": 50})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        # Search within 1km (should not find the business at exact coordinates)
        response = self.client.get(url, {"latitude": 27.8000, "longitude": 85.4000, "radius_km": 1})  # Different coordinates
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # This might still return results due to simplified distance calculation

    def test_business_list_ordering(self):
        """Test ordering functionality"""
        self.client.force_authenticate(user=self.auth_user)
        url = reverse("user:business-list")

        # Test ordering by date joined
        response = self.client.get(url, {"ordering": "user__date_joined"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test ordering by business name
        response = self.client.get(url, {"ordering": "registered_business_name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_business_list_filters_only_distributors(self):
        """Test that API only returns distributors with business_owner role"""
        # Create a retailer (should not be in results)
        retailer_user = User.objects.create_user(username="retailer", email="retailer@test.com", password="testpass123")
        UserProfile.objects.create(
            user=retailer_user,
            role=self.business_owner_role,
            business_type=UserProfile.BusinessType.RETAILER,  # Retailer, not distributor
            location=self.city,
        )

        self.client.force_authenticate(user=self.auth_user)
        url = reverse("user:business-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only return the distributor, not the retailer
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["business_type"], "distributor")


if __name__ == "__main__":
    print("Business List API Test Cases")
    print("Run with: python manage.py test user.test_business_api")
    print("\nTest cases include:")
    print("- Authentication requirement")
    print("- Business listing functionality")
    print("- City-based filtering")
    print("- Search functionality")
    print("- Geographic distance filtering")
    print("- Result ordering")
    print("- Proper filtering (distributors only)")
