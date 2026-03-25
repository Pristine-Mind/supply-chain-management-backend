#!/usr/bin/env python
"""
Quick diagnostic script for notification system
Run with: python manage.py shell < notification_diagnostic.py
"""

import os
from django.conf import settings
from django.contrib.auth import get_user_model
from notification.models import Notification
from notification.services import NotificationServiceFactory

User = get_user_model()

print("=" * 80)
print("NOTIFICATION SYSTEM DIAGNOSTIC REPORT")
print("=" * 80)

# 1. Check Email Configuration
print("\n1. EMAIL CONFIGURATION")
print("-" * 40)
print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
brevo_key = getattr(settings, "BREVO_API_KEY", "")
print(f"BREVO_API_KEY set: {bool(brevo_key)}")

# 2. Check SMS Configuration
print("\n2. SMS CONFIGURATION")
print("-" * 40)
sms_api = getattr(settings, "SPARROWSMS_API_KEY", "")
sms_sender = getattr(settings, "SPARROWSMS_SENDER_ID", "")
sms_endpoint = getattr(settings, "SPARROWSMS_ENDPOINT", "")
print(f"SPARROWSMS_API_KEY set: {bool(sms_api)}")
print(f"SPARROWSMS_SENDER_ID set: {bool(sms_sender)}")
print(f"SPARROWSMS_ENDPOINT: {sms_endpoint}")

# 3. Check FCM Configuration
print("\n3. FCM CONFIGURATION")
print("-" * 40)
fcm_path = getattr(settings, "FCM_SERVICE_ACCOUNT_KEY_PATH", "")
print(f"FCM_SERVICE_ACCOUNT_KEY_PATH: {fcm_path}")
print(f"FCM path exists: {os.path.exists(fcm_path) if fcm_path else False}")

# 4. Check Registered Services
print("\n4. REGISTERED SERVICES")
print("-" * 40)
print("Notification Services in Factory:")
for svc_type, svc_class in NotificationServiceFactory._services.items():
    class_name = svc_class.__name__ if svc_class else "None"
    status = "✓" if svc_class else "✗"
    print(f"  {status} {svc_type:12} -> {class_name}")

# 5. Check Database User Data
print("\n5. DATABASE USER DATA")
print("-" * 40)
total_users = User.objects.count()
users_with_email = User.objects.exclude(email__isnull=True).exclude(email__exact='').count()
users_with_phone = 0

# Try to check for phone_number field
try:
    from django.db.models import Q
    users_with_phone = User.objects.exclude(phone_number__isnull=True).exclude(phone_number__exact='').count()
except:
    users_with_phone = "N/A (phone_number field may not exist)"

print(f"Total users: {total_users}")
print(f"Users with email: {users_with_email}")
print(f"Users with phone number: {users_with_phone}")

# Hardcoded test values
HARDCODED_EMAIL = "khatririshi2430@gmail.com"
HARDCODED_PHONE = "984533509"

print(f"\n=== HARDCODED TEST VALUES ===")
print(f"Test Email: {HARDCODED_EMAIL}")
print(f"Test Phone: {HARDCODED_PHONE}")

if total_users > 0:
    sample_user = User.objects.first()
    print(f"\nSample user (ID: {sample_user.id}):")
    print(f"  Email: {sample_user.email}")
    if hasattr(sample_user, 'phone_number'):
        print(f"  Phone: {sample_user.phone_number}")

# 6. Check Notification Status
print("\n6. NOTIFICATION STATUS")
print("-" * 40)
from django.db.models import Count, Q

stats = Notification.objects.values('notification_type', 'status').annotate(count=Count('id')).order_by('notification_type', '-count')

if stats.exists():
    print("Notification distribution:")
    for stat in stats:
        print(f"  {stat['notification_type']:10} ({stat['status']:10}): {stat['count']:5} notifications")
else:
    print("  No notifications in database")

# 7. Show Recent Failed Notifications
print("\n7. RECENT FAILED NOTIFICATIONS")
print("-" * 40)
failed = Notification.objects.filter(status="failed").order_by("-updated_at")[:5]

if failed.exists():
    print(f"Found {failed.count()} failed notifications:")
    for notif in failed:
        print(f"\n  ID: {notif.id}")
        print(f"  Type: {notif.notification_type}")
        print(f"  User: {notif.user}")
        print(f"  Error: {notif.error_message}")
else:
    print("  No failed notifications")

# 8. Service Connectivity Test
print("\n8. SERVICE CONNECTIVITY TEST")
print("-" * 40)

# Test SMS Service
try:
    from notification.services import SMSNotificationService
    sms_service = SMSNotificationService()
    print(f"✓ SMS Service initialized")
    if not (sms_api and sms_sender and sms_endpoint):
        print(f"  ⚠ Warning: SMS configuration incomplete")
except Exception as e:
    print(f"✗ SMS Service error: {e}")

# Test Email Service
try:
    from notification.services import EmailNotificationService
    email_service = EmailNotificationService()
    print(f"✓ Email Service initialized")
    if not brevo_key:
        print(f"  ⚠ Warning: BREVO_API_KEY not configured")
except Exception as e:
    print(f"✗ Email Service error: {e}")

# Test In-App Service
try:
    from notification.services import InAppNotificationService
    inapp_service = InAppNotificationService()
    print(f"✓ In-App Service initialized")
except Exception as e:
    print(f"✗ In-App Service error: {e}")

print("\n" + "=" * 80)
print("END OF DIAGNOSTIC REPORT")
print("=" * 80)
print("\nRecommendations:")
print("1. Ensure CELERY is restarted after code changes: docker-compose restart celery")
print("2. Check user records have required fields (email, phone_number)")
print("3. Verify environment variables are loaded: docker-compose logs web | grep -i 'api_key'")
print("4. Monitor Celery logs: docker-compose logs -f celery-1 | grep -i notification")

# 9. Test with hardcoded values
print("\n9. TEST WITH HARDCODED VALUES")
print("-" * 40)

HARDCODED_EMAIL = "khatririshi2430@gmail.com"
HARDCODED_PHONE = "984533509"

if total_users > 0:
    test_user = User.objects.first()
    
    # Test In-App Notification
    print("\nTesting In-App Notification:")
    try:
        inapp = Notification.objects.create(
            user=test_user,
            notification_type="in_app",
            title="Test In-App",
            body="Testing hardcoded values - In-App"
        )
        result = NotificationServiceFactory.send_notification(inapp)
        inapp.refresh_from_db()
        print(f"  Status: {inapp.status} | Success: {result}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test Email Notification with hardcoded email
    print(f"\nTesting Email Notification (to {HARDCODED_EMAIL}):")
    try:
        email = Notification.objects.create(
            user=test_user,
            notification_type="email",
            title="Test Email",
            body="Testing hardcoded email address"
        )
        # Override with hardcoded email for testing
        test_user.email = HARDCODED_EMAIL
        result = NotificationServiceFactory.send_notification(email)
        email.refresh_from_db()
        print(f"  Status: {email.status} | Success: {result}")
        print(f"  Error: {email.error_message if not result else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test SMS Notification with hardcoded phone
    print(f"\nTesting SMS Notification (to {HARDCODED_PHONE}):")
    try:
        sms = Notification.objects.create(
            user=test_user,
            notification_type="sms",
            title="Test SMS",
            body="Testing hardcoded phone number"
        )
        # Override with hardcoded phone for testing
        test_user.phone_number = HARDCODED_PHONE
        result = NotificationServiceFactory.send_notification(sms)
        sms.refresh_from_db()
        print(f"  Status: {sms.status} | Success: {result}")
        print(f"  Error: {sms.error_message if not result else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n" + "=" * 80)
else:
    print("\nCannot test - no users in database")
