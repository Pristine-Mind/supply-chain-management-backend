#!/usr/bin/env python3
"""
Simple test script to verify external API authentication
"""
import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from rest_framework.test import APIClient
from external_delivery.models import ExternalBusiness, ExternalBusinessPlan, ExternalBusinessStatus

# Create test client
client = APIClient()

# Create or get test business
try:
    business = ExternalBusiness.objects.get(business_email="test@example.com")
    print(f"Found existing business: {business.business_name}")
except ExternalBusiness.DoesNotExist:
    business = ExternalBusiness.objects.create(
        business_name="Test Business",
        business_email="test@example.com",
        contact_person="Test User",
        contact_phone="+1234567890",
        business_address="123 Test St",
        plan=ExternalBusinessPlan.STARTER,
        status=ExternalBusinessStatus.APPROVED,
    )
    print(f"Created test business: {business.business_name}")

print(f"API Key: {business.api_key}")
print(f"Status: {business.status}")

# Test API authentication
client.credentials(HTTP_X_API_KEY=business.api_key)

# Test endpoint access
response = client.get("/api/external/deliveries/")
print(f"GET /api/external/deliveries/ - Status: {response.status_code}")

if response.status_code == 200:
    print("✅ Authentication successful!")
    print(f"Response: {response.data}")
else:
    print("❌ Authentication failed!")
    print(f"Response: {response.data}")

# Test creating a delivery
delivery_data = {
    "external_delivery_id": "TEST_001",
    "pickup_name": "Test Pickup",
    "pickup_address": "123 Pickup St",
    "pickup_city": "Kathmandu",
    "pickup_phone": "+9771234567",
    "delivery_name": "Test Customer",
    "delivery_address": "456 Delivery St",
    "delivery_city": "Lalitpur",
    "delivery_phone": "+9777654321",
    "package_description": "Test Package",
    "package_weight": 1.5,
    "delivery_fee": 150.00,
}

response = client.post("/api/external/deliveries/", delivery_data)
print(f"POST /api/external/deliveries/ - Status: {response.status_code}")

if response.status_code == 201:
    print("✅ Delivery creation successful!")
    print(f"Response: {response.data}")
else:
    print("❌ Delivery creation failed!")
    print(f"Response: {response.data}")
