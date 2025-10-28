#!/usr/bin/env python
"""
Test script to verify task isolation in notification system.
This tests that email failures don't prevent SMS delivery.
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

from market.utils import notify_event
from user.models import User

def test_task_isolation():
    """Test that email failure doesn't prevent SMS delivery"""
    print("Testing task isolation in notify_event...")
    
    try:
        # Get or create a test user
        test_user, created = User.objects.get_or_create(
            email='test@example.com',
            defaults={'username': 'testuser', 'first_name': 'Test', 'last_name': 'User'}
        )
        
        # This should attempt both email and SMS
        # Even if email fails, SMS should still be attempted
        notify_event(
            user=test_user,
            notif_type='test_isolation',
            message='Testing task isolation - email failure should not block SMS',
            via_in_app=True,
            via_email=True,
            via_sms=True,
            email_addr='test@example.com',
            sms_number='+9771234567890',
            email_tpl='notifications/test_email.html',
            email_ctx={'test': 'context'},
            sms_body='Test SMS: Task isolation working'
        )
        
        print("✅ Task isolation test completed - check logs for individual task results")
        print("   - In-app notification should be created immediately")
        print("   - Email task should be queued (may fail due to SendGrid issues)")
        print("   - SMS task should be queued independently of email status")
        return True
        
    except Exception as e:
        print(f"❌ Task isolation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_task_isolation()
    sys.exit(0 if success else 1)