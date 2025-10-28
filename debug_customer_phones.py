#!/usr/bin/env python
"""
Debug script to check customer phone number availability.
This helps identify why SMS notifications aren't being sent to buyers.
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
from user.models import UserProfile
from payment.models import PaymentTransaction, PaymentTransactionStatus

def debug_customer_phone_numbers():
    """Debug customer phone number availability"""
    print("🔍 Debugging Customer Phone Number Availability")
    print("=" * 60)
    
    # Check recent payment transactions
    recent_payments = PaymentTransaction.objects.filter(
        status=PaymentTransactionStatus.COMPLETED
    ).order_by('-completed_at')[:5]
    
    print(f"📊 Checking {recent_payments.count()} recent completed payments:")
    print()
    
    for payment in recent_payments:
        print(f"🔍 Payment {payment.order_number}:")
        print(f"   User: {payment.user.username} ({payment.user.email})")
        print(f"   Customer Name: {payment.customer_name}")
        print(f"   Customer Email: {payment.customer_email}")
        print(f"   Customer Phone (from payment): {payment.customer_phone or 'None'}")
        
        # Check user profile phone
        try:
            profile_phone = None
            if hasattr(payment.user, 'user_profile') and payment.user.user_profile:
                profile_phone = payment.user.user_profile.phone_number
            print(f"   Profile Phone: {profile_phone or 'None'}")
        except Exception as e:
            print(f"   Profile Phone: Error - {e}")
        
        # Check direct user phone field
        try:
            direct_phone = getattr(payment.user, 'phone_number', None)
            print(f"   Direct User Phone: {direct_phone or 'None'}")
        except Exception as e:
            print(f"   Direct User Phone: Error - {e}")
        
        # Determine if SMS would be sent
        customer_phone = None
        if payment.customer_phone:
            customer_phone = payment.customer_phone
            source = "payment"
        elif hasattr(payment.user, 'user_profile') and payment.user.user_profile and payment.user.user_profile.phone_number:
            customer_phone = payment.user.user_profile.phone_number
            source = "profile"
        elif hasattr(payment.user, 'phone_number') and payment.user.phone_number:
            customer_phone = payment.user.phone_number
            source = "direct"
        
        if customer_phone:
            print(f"   ✅ SMS would be sent to: {customer_phone} (from {source})")
        else:
            print(f"   ❌ SMS would NOT be sent - no phone number found")
        
        print()
    
    # Check all users with profiles
    print("👥 User Profile Phone Number Summary:")
    total_users = User.objects.count()
    users_with_profiles = User.objects.filter(user_profile__isnull=False).count()
    users_with_phone = User.objects.filter(user_profile__phone_number__isnull=False).exclude(user_profile__phone_number='').count()
    
    print(f"   Total Users: {total_users}")
    print(f"   Users with Profiles: {users_with_profiles}")
    print(f"   Users with Phone Numbers: {users_with_phone}")
    print(f"   Phone Coverage: {(users_with_phone/total_users*100):.1f}%")

if __name__ == "__main__":
    debug_customer_phone_numbers()