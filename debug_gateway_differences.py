#!/usr/bin/env python
"""
Debug script to test different payment gateways.
This helps identify why KHALTI works but CONNECT_IPS doesn't.
"""

import os
import sys
import django

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Configure Django settings
_ = os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()

from payment.khalti import Khalti
from payment.models import PaymentGateway
from django.conf import settings

def test_khalti_gateway_initiation():
    """Test payment initiation for different gateways"""
    print("🧪 Testing Khalti Payment Gateway Initiation")
    print("=" * 60)
    
    khalti = Khalti()
    
    # Test parameters
    test_amount = 100.0  # Rs. 100
    test_return_url = "https://yourapp.com/payment/return"
    test_purchase_order_id = "TEST-12345"
    test_purchase_order_name = "Test Order"
    
    print(f"📊 Test Parameters:")
    print(f"   Amount: Rs. {test_amount}")
    print(f"   Return URL: {test_return_url}")
    print(f"   Purchase Order ID: {test_purchase_order_id}")
    print(f"   Purchase Order Name: {test_purchase_order_name}")
    print()
    
    # Test each gateway
    gateways_to_test = [
        ("KHALTI", None),
        ("CONNECT_IPS", None),
        ("SCT", None),
        ("MOBILE_BANKING", "KHUMALIPATI"),  # Example bank
        ("EBANKING", "SCB"),  # Example bank
    ]
    
    for gateway, bank in gateways_to_test:
        print(f"🔍 Testing Gateway: {gateway}" + (f" with bank: {bank}" if bank else ""))
        print("-" * 40)
        
        try:
            # Test the initiate method directly
            result = khalti.initiate(
                amount=test_amount,
                return_url=test_return_url,
                gateway=gateway,
                bank=bank
            )
            
            print(f"   ✅ Success!")
            print(f"   Response type: {type(result)}")
            
            if isinstance(result, dict):
                print(f"   Payment URL: {result.get('payment_url', 'Not found')}")
                print(f"   PIDX: {result.get('pidx', 'Not found')}")
                if 'full_response' in result:
                    response_keys = list(result['full_response'].keys())
                    print(f"   Full response keys: {response_keys}")
            else:
                print(f"   Result: {result}")
                
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            
        print()

def test_khalti_payload_differences():
    """Test what payload is sent for different gateways"""
    print("🔍 Testing Khalti API Payload Differences")
    print("=" * 50)
    
    khalti = Khalti()
    
    # Mock the requests.post to see what payload is sent
    import requests
    original_post = requests.post
    
    def mock_post(url, json=None, headers=None, **kwargs):
        print(f"📤 Khalti API Call:")
        print(f"   URL: {url}")
        print(f"   Payload: {json}")
        print(f"   Headers: {headers}")
        print()
        
        # Return a mock success response
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "payment_url": f"https://test.khalti.com/payment/{json.get('modes', [''])[0].lower()}",
                    "pidx": f"test-pidx-{json.get('modes', [''])[0].lower()}",
                }
            def __str__(self):
                return '{"payment_url": "mock_url", "pidx": "mock_pidx"}'
            @property
            def text(self):
                return self.__str__()
        
        return MockResponse()
    
    # Temporarily replace requests.post
    requests.post = mock_post
    
    try:
        gateways = ["KHALTI", "CONNECT_IPS", "SCT", "MOBILE_BANKING", "EBANKING"]
        
        for gateway in gateways:
            print(f"🎯 Gateway: {gateway}")
            try:
                khalti.initiate(
                    amount=100.0,
                    return_url="https://test.com/return",
                    gateway=gateway,
                    bank="SCB" if gateway in ["MOBILE_BANKING", "EBANKING"] else None
                )
            except Exception as e:
                print(f"   Error: {e}")
            print()
            
    finally:
        # Restore original requests.post
        requests.post = original_post

def check_khalti_api_response_formats():
    """Check if different gateways return different response formats"""
    print("📋 Expected Khalti API Behavior:")
    print("=" * 40)
    print("✅ KHALTI gateway:")
    print("   - Should return standard payment_url + pidx")
    print("   - Direct wallet payment flow")
    print()
    print("✅ CONNECT_IPS gateway:")
    print("   - Should return standard payment_url + pidx")
    print("   - Bank transfer payment flow")
    print()
    print("✅ MOBILE_BANKING/EBANKING:")
    print("   - Should return standard payment_url + pidx")
    print("   - Requires 'bank' parameter")
    print()
    print("🤔 Potential Issues:")
    print("   1. Different response format for non-KHALTI gateways")
    print("   2. Missing bank parameter for banking gateways")
    print("   3. Different payment_url handling in frontend")
    print("   4. Gateway-specific validation in Khalti API")

if __name__ == "__main__":
    print("🚀 Gateway Debugging Session")
    print("=" * 60)
    
    test_khalti_payload_differences()
    test_khalti_gateway_initiation()
    check_khalti_api_response_formats()
    
    print("💡 Next Steps:")
    print("1. Run this script to see actual API payloads")
    print("2. Check Khalti API response for different gateways")
    print("3. Verify Flutter app handles all response formats")
    print("4. Test with valid bank parameters for banking gateways")