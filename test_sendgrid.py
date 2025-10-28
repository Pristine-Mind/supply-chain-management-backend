#!/usr/bin/env python
"""
Test SendGrid email configuration.
This script tests if SendGrid is properly configured and can send emails.
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

from django.core.mail import send_mail
from django.conf import settings

def test_sendgrid_configuration():
    """Test SendGrid email configuration"""
    print("🧪 Testing SendGrid Email Configuration")
    print("=" * 50)
    
    # Check if SendGrid API key is set
    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    if sendgrid_key:
        print(f"✅ SendGrid API Key: Found (starts with: {sendgrid_key[:10]}...)")
    else:
        print("❌ SendGrid API Key: Not found in environment variables")
        print("   Please set SENDGRID_API_KEY environment variable")
        return False
    
    # Check email backend configuration
    print(f"📧 Email Backend: {settings.EMAIL_BACKEND}")
    print(f"📤 Default From Email: {settings.DEFAULT_FROM_EMAIL}")
    
    if hasattr(settings, 'ANYMAIL'):
        print(f"🔧 Anymail Config: {list(settings.ANYMAIL.keys())}")
    
    # Test sending a simple email
    print("\n📮 Sending test email...")
    try:
        result = send_mail(
            subject="🧪 SendGrid Test Email - Supply Chain Management",
            message="This is a test email to verify SendGrid configuration is working properly.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=["khatririshi2430@gmail.com"],  # Your email
            html_message="""
            <h2>🧪 SendGrid Test Email</h2>
            <p>This is a test email to verify SendGrid configuration is working properly.</p>
            <p><strong>System:</strong> Supply Chain Management Backend</p>
            <p><strong>Time:</strong> {}</p>
            <p>If you receive this email, SendGrid is configured correctly! 🎉</p>
            """.format(
                __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ),
            fail_silently=False,
        )
        
        print(f"✅ Email sent successfully! Send result: {result}")
        print("📬 Check your inbox at khatririshi2430@gmail.com")
        print("💡 If you don't receive the email, check:")
        print("   - Spam/Junk folder")
        print("   - SendGrid sender verification")
        print("   - SendGrid API key permissions")
        return True
        
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        print("💡 Common issues:")
        print("   - Invalid SendGrid API key")
        print("   - Sender email not verified in SendGrid")
        print("   - API key doesn't have mail sending permissions")
        return False

def show_sendgrid_setup_steps():
    """Show SendGrid setup steps"""
    print("\n📋 SendGrid Setup Checklist:")
    print("1. ✅ Create SendGrid account at https://sendgrid.com")
    print("2. ✅ Create API Key with 'Mail Send' permissions")
    print("3. ✅ Verify sender identity (mulyabazzar@gmail.com)")
    print("4. ✅ Set SENDGRID_API_KEY environment variable")
    print("5. ✅ Restart your Django application")
    
if __name__ == "__main__":
    success = test_sendgrid_configuration()
    show_sendgrid_setup_steps()
    
    if success:
        print("\n🎉 SendGrid is ready for production email sending!")
    else:
        print("\n⚠️  Please fix the SendGrid configuration before proceeding.")
    
    sys.exit(0 if success else 1)