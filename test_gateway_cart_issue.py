#!/usr/bin/env python
"""
Comprehensive test to replicate the exact Flutter scenario.
This tests payment initiation for both KHALTI and CONNECT_IPS with the same cart.
"""

import os
import sys
import django
import json

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Configure Django settings
_ = os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from market.models import Cart, MarketplaceProduct, Product
from payment.views import initiate_payment

def replicate_flutter_scenario():
    """Replicate the exact Flutter scenario to identify the difference"""
    print("🔄 Replicating Flutter Payment Scenario")
    print("=" * 50)
    
    # Find the user with the token from Flutter logs
    token_key = "a64af4b77c54368a777f7170c6e3f1718f70644e"
    
    try:
        token = Token.objects.get(key=token_key)
        user = token.user
        print(f"👤 Found user: {user.username} ({user.email})")
    except Token.DoesNotExist:
        print("❌ Token not found - creating test scenario")
        # Create a test user and token for testing
        user = User.objects.create_user(
            username="test_user_debug",
            email="test@example.com",
            password="testpass123"
        )
        token = Token.objects.create(user=user, key=token_key)
        print(f"👤 Created test user: {user.username}")
    
    # Check cart 5
    print(f"\n🛒 Checking Cart ID 5 for user {user.username}:")
    try:
        cart = Cart.objects.prefetch_related("items__product__product").get(id=5, user=user)
        print(f"   ✅ Cart found: {cart.items.count()} items")
        
        for item in cart.items.all():
            print(f"   📦 {item.product.product.name}: Qty {item.quantity}, Price Rs.{item.product.listed_price}")
            
    except Cart.DoesNotExist:
        print(f"   ❌ Cart 5 not found for user {user.username}")
        print(f"   🔍 Available carts for this user:")
        user_carts = Cart.objects.filter(user=user)
        for cart in user_carts:
            print(f"      Cart {cart.id}: {cart.items.count()} items")
        
        # Create a test cart with items for testing
        print(f"   🆕 Creating test cart with items...")
        try:
            # Get or create a test product
            test_product = Product.objects.first()
            if test_product:
                marketplace_product = MarketplaceProduct.objects.filter(product=test_product).first()
                if marketplace_product:
                    cart = Cart.objects.create(user=user)
                    cart.items.create(product=marketplace_product, quantity=2)
                    # Update to cart ID 5 for testing
                    cart.id = 5
                    cart.save()
                    print(f"   ✅ Created test cart with ID 5")
                else:
                    print(f"   ❌ No marketplace products available")
            else:
                print(f"   ❌ No products available for testing")
        except Exception as e:
            print(f"   ❌ Error creating test cart: {e}")
    
    # Test payment initiation with both gateways
    request_factory = RequestFactory()
    
    # Test data from Flutter logs
    test_data = {
        "cart_id": 5,
        "return_url": "https://yourapp.com/payment/return",
        "customer_name": "Rishi khatri",
        "customer_email": "khatririshi2430@gmail.com",
        "customer_phone": "9845333509",
        "shipping_cost": "100.00"
    }
    
    gateways_to_test = ["KHALTI", "CONNECT_IPS"]
    
    for gateway in gateways_to_test:
        print(f"\n💳 Testing Payment Initiation with {gateway}:")
        print("-" * 40)
        
        # Prepare request data
        request_data = test_data.copy()
        request_data["gateway"] = gateway
        
        # Create mock request
        request = request_factory.post(
            '/api/v1/payments/initiate/',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        request.user = user
        
        try:
            # Mock the request.data attribute
            request.data = request_data
            
            # Call the initiate_payment function
            response = initiate_payment(request)
            
            print(f"   Status Code: {response.status_code}")
            print(f"   Response: {response.data}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Additional debugging
    print(f"\n🔍 Additional Analysis:")
    print(f"   - User authentication: {'✅ Valid' if user.is_authenticated else '❌ Invalid'}")
    print(f"   - Token validity: {'✅ Valid' if token else '❌ Invalid'}")
    
    # Check if there are any gateway-specific validation differences
    from payment.models import PaymentGateway
    valid_gateways = [choice[0] for choice in PaymentGateway.choices]
    print(f"   - Valid gateways: {valid_gateways}")
    print(f"   - KHALTI valid: {'✅' if 'KHALTI' in valid_gateways else '❌'}")
    print(f"   - CONNECT_IPS valid: {'✅' if 'CONNECT_IPS' in valid_gateways else '❌'}")

if __name__ == "__main__":
    replicate_flutter_scenario()
    
    print(f"\n💡 Hypothesis:")
    print(f"   If both gateways show 'Cart is empty', the issue is cart-related")
    print(f"   If only CONNECT_IPS shows 'Cart is empty', there's gateway-specific logic")
    print(f"   If both work, the issue might be timing or session-related in Flutter")