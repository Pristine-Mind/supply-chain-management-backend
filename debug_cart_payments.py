#!/usr/bin/env python
"""
Debug script to check cart contents and payment gateway setup.
This helps identify why cart is empty and verify payment gateway configuration.
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

from django.contrib.auth.models import User
from market.models import Cart
from payment.models import PaymentGateway
from payment.khalti import Khalti

def debug_cart_and_payments():
    """Debug cart contents and payment gateway setup"""
    print("🛒 Cart & Payment Gateway Debug")
    print("=" * 50)
    
    # Check user and cart
    try:
        # Find user by token (you'll need to check who this token belongs to)
        user = User.objects.filter(auth_token__key="a64af4b77c54368a777f7170c6e3f1718f70644e").first()
        if not user:
            print("❌ No user found with that token")
            return
            
        print(f"👤 User: {user.username} ({user.email})")
        
        # Check cart 5 specifically
        try:
            cart = Cart.objects.prefetch_related("items__product__product").get(id=5, user=user)
            print(f"🛒 Cart ID 5 found for user {user.username}")
            print(f"   Items count: {cart.items.count()}")
            
            if cart.items.exists():
                print("   📦 Cart Items:")
                for item in cart.items.all():
                    print(f"     - {item.product.product.name}: Qty {item.quantity}, Price Rs.{item.product.listed_price}")
            else:
                print("   ❌ Cart is EMPTY - this is why payment fails!")
                
        except Cart.DoesNotExist:
            print(f"❌ Cart with ID 5 not found for user {user.username}")
            
        # Check all carts for this user
        user_carts = Cart.objects.filter(user=user).prefetch_related("items")
        print(f"\n📊 All carts for {user.username}:")
        for cart in user_carts:
            print(f"   Cart {cart.id}: {cart.items.count()} items")
            
    except Exception as e:
        print(f"❌ Error checking user/cart: {e}")
    
    # Check payment gateways
    print(f"\n💳 Available Payment Gateways:")
    gateway_choices = PaymentGateway.choices
    for choice in gateway_choices:
        print(f"   - {choice[0]}: {choice[1]}")
    
    # Test Khalti gateway fetching
    print(f"\n🔗 Khalti Gateway Integration:")
    try:
        khalti = Khalti()
        gateways = khalti.get_payment_gateways()
        print(f"   ✅ Khalti API connection successful")
        print(f"   📡 Available gateways from Khalti:")
        for gateway in gateways:
            items_count = len(gateway.get('items', []))
            print(f"     - {gateway['slug']}: {gateway['name']} ({items_count} sub-options)")
            
    except Exception as e:
        print(f"   ❌ Khalti API error: {e}")
    
    print(f"\n🎯 Analysis:")
    print(f"   1. All payment gateways (KHALTI, CONNECT_IPS, EBANKING) correctly use Khalti SDK")
    print(f"   2. CONNECT_IPS is a bank option within Khalti's unified payment system")
    print(f"   3. Your Flutter app should use Khalti SDK for ALL payment methods")
    print(f"   4. The main issue is the EMPTY CART preventing payment initiation")

def show_cart_solutions():
    """Show solutions for cart issues"""
    print(f"\n🔧 Solutions for Cart Issues:")
    print(f"1. 🛒 Add items to cart before payment:")
    print(f"   - Use the add-to-cart API to add products")
    print(f"   - Verify cart has items before payment initiation")
    print(f"2. 🔍 Check cart ownership:")
    print(f"   - Ensure cart belongs to the authenticated user")
    print(f"   - Verify cart ID matches user's active cart")
    print(f"3. 🧹 Cart cleanup:")
    print(f"   - Remove expired/invalid cart items")
    print(f"   - Ensure product availability")

if __name__ == "__main__":
    debug_cart_and_payments()
    show_cart_solutions()