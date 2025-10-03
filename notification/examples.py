"""
Example usage of the notification system

This file demonstrates how to use various features of the notification system
in different scenarios within the supply chain management application.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .rules_engine import (
    NotificationRulesEngine,
    trigger_delivery_event,
    trigger_order_event,
    trigger_payment_event,
    trigger_stock_event,
    trigger_user_event,
)
from .services import NotificationServiceFactory
from .tasks import process_notification_batch_task
from .utils import (
    NotificationHelper,
    NotificationRuleBuilder,
    NotificationTemplateBuilder,
    create_default_rules,
    create_default_templates,
)

User = get_user_model()


def example_1_quick_notification():
    """
    Example 1: Send a quick notification to a user
    """
    print("=== Example 1: Quick Notification ===")

    # Get a user (assuming user exists)
    user = User.objects.first()
    if not user:
        print("No users found. Create a user first.")
        return

    # Send a quick notification
    notification = NotificationHelper.create_quick_notification(
        user=user,
        title="Welcome to Mulya Bazzar!",
        body="Start exploring fresh products from local producers.",
        notification_type="push",
        action_url="https://app.mulyabazzar.com/products",
        priority=8,
        send_immediately=True,
    )

    print(f"Quick notification sent to {user.username}")
    print(f"Notification ID: {notification.id}")
    print(f"Status: {notification.status}")


def example_2_template_based_notification():
    """
    Example 2: Create template and send template-based notification
    """
    print("\n=== Example 2: Template-Based Notification ===")

    # Create a notification template using builder pattern
    template = (
        NotificationTemplateBuilder()
        .name("order_update")
        .type("push")
        .title("Order Update: {status}")
        .body("Your order #{order_number} for {product_name} is now {status}. {additional_info}")
        .action_url("https://app.mulyabazzar.com/orders/{order_id}")
        .variables(["status", "order_number", "product_name", "additional_info", "order_id"])
        .active(True)
        .build()
    )

    print(f"Created template: {template.name}")

    # Use the template to create notifications
    users = User.objects.all()[:3]  # Get first 3 users

    for i, user in enumerate(users):
        context = {
            "status": "confirmed",
            "order_number": f"ORD-{1000 + i}",
            "product_name": f"Organic Vegetables Bundle {i+1}",
            "additional_info": "Expected delivery in 2-3 days.",
            "order_id": 1000 + i,
        }

        # Render template
        rendered = template.render(context)

        # Create notification
        notification = Notification.objects.create(
            user=user,
            notification_type=template.template_type,
            title=rendered["title"],
            body=rendered["body"],
            action_url=rendered["action_url"],
            template=template,
            event_data=context,
            priority=7,
        )

        print(f"Created notification for {user.username}: {rendered['title']}")


def example_3_event_driven_notifications():
    """
    Example 3: Set up event-driven notifications with rules
    """
    print("\n=== Example 3: Event-Driven Notifications ===")

    # Create template for order confirmation
    template = NotificationTemplate.objects.create(
        name="order_confirmation_v2",
        template_type="push",
        title_template="Order Confirmed! 🎉",
        body_template="Hi {customer_name}! Your order #{order_number} for {product_name} has been confirmed. Total: Rs. {total_amount}",
        variables=["customer_name", "order_number", "product_name", "total_amount"],
        action_url_template="https://app.mulyabazzar.com/orders/{order_id}",
        is_active=True,
    )

    # Create notification rule
    rule = (
        NotificationRuleBuilder()
        .name("Order Confirmation Rule V2")
        .description("Send notification when order is confirmed with amount > 500")
        .trigger("order_confirmed")
        .template(template)
        .conditions([{"field": "total_amount", "operator": "gt", "value": 500}])
        .target_users({"event_based": {"use_event_user": True}})
        .priority(9)
        .active(True)
        .build()
    )

    print(f"Created rule: {rule.name}")

    # Simulate order confirmation event
    user = User.objects.first()
    if user:
        # Mock order data
        order_data = {
            "order_id": 12345,
            "order_number": "ORD-12345",
            "customer_name": user.get_full_name() or user.username,
            "product_name": "Fresh Organic Vegetables",
            "total_amount": 750.0,
            "user_id": user.id,
            "status": "confirmed",
        }

        # Trigger the event
        engine = NotificationRulesEngine()
        engine.trigger_event("order_confirmed", order_data, user.id)

        print(f"Triggered order_confirmed event for user {user.username}")
        print(f"Order amount: Rs. {order_data['total_amount']} (above threshold)")


def example_4_user_preferences():
    """
    Example 4: Manage user notification preferences
    """
    print("\n=== Example 4: User Preferences ===")

    user = User.objects.first()
    if not user:
        print("No users found.")
        return

    # Get or create user preferences
    preferences, created = UserNotificationPreference.objects.get_or_create(
        user=user,
        defaults={
            "push_enabled": True,
            "email_enabled": True,
            "sms_enabled": False,
            "in_app_enabled": True,
            "order_notifications": True,
            "payment_notifications": True,
            "marketing_notifications": False,
            "delivery_notifications": True,
            "quiet_hours_enabled": True,
            "quiet_start_time": "22:00:00",
            "quiet_end_time": "08:00:00",
            "timezone": "Asia/Kathmandu",
        },
    )

    if created:
        print(f"Created preferences for {user.username}")
    else:
        print(f"Preferences already exist for {user.username}")

    print(f"Push notifications: {'Enabled' if preferences.push_enabled else 'Disabled'}")
    print(f"Email notifications: {'Enabled' if preferences.email_enabled else 'Disabled'}")
    print(f"Quiet hours: {'Enabled' if preferences.quiet_hours_enabled else 'Disabled'}")

    if preferences.quiet_hours_enabled:
        print(f"Quiet hours: {preferences.quiet_start_time} - {preferences.quiet_end_time}")


def example_5_device_token_management():
    """
    Example 5: Device token management for push notifications
    """
    print("\n=== Example 5: Device Token Management ===")

    user = User.objects.first()
    if not user:
        print("No users found.")
        return

    # Register device tokens for different platforms
    tokens = [
        {"token": "fcm_token_android_123456789", "device_type": "android", "device_id": "android_device_001"},
        {"token": "apns_token_ios_987654321", "device_type": "ios", "device_id": "ios_device_001"},
        {"token": "web_push_token_web_555666777", "device_type": "web", "device_id": "web_browser_001"},
    ]

    for token_data in tokens:
        device_token, created = DeviceToken.objects.get_or_create(
            user=user,
            token=token_data["token"],
            defaults={"device_type": token_data["device_type"], "device_id": token_data["device_id"], "is_active": True},
        )

        if created:
            print(f"Registered {token_data['device_type']} device token for {user.username}")
        else:
            print(f"{token_data['device_type']} device token already exists")

    # Show user's active tokens
    active_tokens = DeviceToken.objects.filter(user=user, is_active=True)
    print(f"\nActive device tokens for {user.username}: {active_tokens.count()}")
    for token in active_tokens:
        print(f"  - {token.device_type}: {token.token[:20]}...")


def example_6_batch_notifications():
    """
    Example 6: Send batch notifications to multiple users
    """
    print("\n=== Example 6: Batch Notifications ===")

    # Get template for batch notification
    template = NotificationTemplate.objects.filter(name="welcome_user").first()
    if not template:
        template = NotificationTemplate.objects.create(
            name="weekly_newsletter",
            template_type="push",
            title_template="Weekly Newsletter 📰",
            body_template="Hi {customer_name}! Check out this week's fresh arrivals and special offers.",
            variables=["customer_name"],
            is_active=True,
        )

    # Get users for batch notification
    users = User.objects.filter(is_active=True)[:5]  # First 5 active users

    if users.exists():
        # Create notification batch
        batch = NotificationBatch.objects.create(
            name="Weekly Newsletter - " + timezone.now().strftime("%Y-%m-%d"),
            description="Weekly newsletter with fresh arrivals and offers",
            template=template,
            context_data={
                "newsletter_date": timezone.now().strftime("%B %d, %Y"),
                "special_offer": "20% off on organic vegetables",
            },
            created_by=users.first(),  # Use first user as creator for demo
            scheduled_at=timezone.now(),
        )

        # Add target users
        batch.target_users.set(users)

        print(f"Created batch notification: {batch.name}")
        print(f"Target users: {batch.target_users.count()}")

        # Process batch (normally done by Celery)
        # process_notification_batch_task.delay(str(batch.id))
        print("Batch processing scheduled")
    else:
        print("No active users found for batch notification")


def example_7_notification_analytics():
    """
    Example 7: Get notification analytics and performance metrics
    """
    print("\n=== Example 7: Notification Analytics ===")

    from .utils import NotificationHelper

    # Get system-wide performance metrics
    metrics = NotificationHelper.get_notification_performance_metrics(days=7)

    print("=== Notification Performance (Last 7 days) ===")
    print(f"Total notifications: {metrics['total_notifications']}")
    print(f"Delivery rate: {metrics['delivery_rate']}%")
    print(f"Read rate: {metrics['read_rate']}%")
    print(f"Failure rate: {metrics['failure_rate']}%")
    print(f"Average delivery time: {metrics['avg_delivery_time']} seconds")

    print("\n=== By Status ===")
    for status, count in metrics["by_status"].items():
        print(f"  {status}: {count}")

    print("\n=== By Type ===")
    for notification_type, count in metrics["by_type"].items():
        print(f"  {notification_type}: {count}")

    # Get user-specific summary
    user = User.objects.first()
    if user:
        user_summary = NotificationHelper.get_user_notification_summary(user, days=7)
        print(f"\n=== User Summary for {user.username} ===")
        print(f"Total: {user_summary['total']}")
        print(f"Unread: {user_summary['unread']}")
        print(f"Read: {user_summary['read']}")


def example_8_custom_notification_service():
    """
    Example 8: Use notification services directly
    """
    print("\n=== Example 8: Custom Notification Service ===")

    user = User.objects.first()
    if not user:
        print("No users found.")
        return

    # Create a notification
    notification = Notification.objects.create(
        user=user,
        notification_type="push",
        title="Direct Service Test",
        body="This notification is sent using the service directly",
        priority=5,
    )

    # Get appropriate service
    service = NotificationServiceFactory.get_service("push")

    if service:
        print(f"Using service: {service.__class__.__name__}")

        # Send notification directly
        success = service.send_notification(notification)

        if success:
            print("Notification sent successfully via direct service call")
        else:
            print("Failed to send notification via direct service call")
    else:
        print("No service available for push notifications")


def example_9_setup_default_system():
    """
    Example 9: Set up default notification system
    """
    print("\n=== Example 9: Setup Default System ===")

    from .utils import setup_notification_system

    # Setup default templates and rules
    result = setup_notification_system()

    templates_created = len(result["templates"])
    rules_created = len(result["rules"])

    print(f"Default system setup completed:")
    print(f"  Templates created: {templates_created}")
    print(f"  Rules created: {rules_created}")

    # Show available templates
    all_templates = NotificationTemplate.objects.filter(is_active=True)
    print(f"\nAvailable templates ({all_templates.count()}):")
    for template in all_templates:
        print(f"  - {template.name} ({template.template_type})")

    # Show available rules
    all_rules = NotificationRule.objects.filter(is_active=True)
    print(f"\nActive rules ({all_rules.count()}):")
    for rule in all_rules:
        print(f"  - {rule.name} -> {rule.trigger_event}")


def example_10_real_world_scenario():
    """
    Example 10: Real-world scenario - Complete order flow
    """
    print("\n=== Example 10: Real-World Order Flow ===")

    user = User.objects.first()
    if not user:
        print("No users found.")
        return

    # Simulate complete order flow with notifications
    order_id = 98765
    order_number = f"ORD-{order_id}"

    print(f"Simulating order flow for {user.username}")
    print(f"Order: {order_number}")

    # Step 1: Order created
    print("\n1. Order Created")
    order_created_data = {
        "order_id": order_id,
        "order_number": order_number,
        "customer_name": user.get_full_name() or user.username,
        "product_name": "Organic Vegetable Bundle",
        "total_amount": 1200.0,
        "user_id": user.id,
        "status": "created",
    }

    engine = NotificationRulesEngine()
    engine.trigger_event("order_created", order_created_data, user.id)
    print("✓ Order creation notification triggered")

    # Step 2: Payment received
    print("\n2. Payment Received")
    payment_data = {
        "payment_id": 12345,
        "order_id": order_id,
        "user_id": user.id,
        "amount": 1200.0,
        "payment_method": "Khalti",
        "transaction_id": "TXN123456789",
        "status": "completed",
    }

    engine.trigger_event("payment_received", payment_data, user.id)
    print("✓ Payment confirmation notification triggered")

    # Step 3: Order confirmed
    print("\n3. Order Confirmed")
    order_confirmed_data = order_created_data.copy()
    order_confirmed_data["status"] = "confirmed"

    engine.trigger_event("order_confirmed", order_confirmed_data, user.id)
    print("✓ Order confirmation notification triggered")

    # Step 4: Order shipped
    print("\n4. Order Shipped")
    order_shipped_data = order_created_data.copy()
    order_shipped_data.update({"status": "shipped", "tracking_number": "TRK789456123"})

    engine.trigger_event("order_shipped", order_shipped_data, user.id)
    print("✓ Order shipped notification triggered")

    # Step 5: Order delivered
    print("\n5. Order Delivered")
    order_delivered_data = order_created_data.copy()
    order_delivered_data["status"] = "delivered"

    engine.trigger_event("order_delivered", order_delivered_data, user.id)
    print("✓ Order delivered notification triggered")

    # Show notifications created for this user
    recent_notifications = Notification.objects.filter(
        user=user, created_at__gte=timezone.now() - timedelta(minutes=5)
    ).order_by("-created_at")

    print(f"\n=== Notifications Created ({recent_notifications.count()}) ===")
    for notification in recent_notifications:
        print(f"  - {notification.title}")
        print(f"    {notification.body}")
        print(f"    Status: {notification.status}")
        print()


def run_all_examples():
    """Run all examples"""
    print("🚀 Running Notification System Examples")
    print("=" * 50)

    try:
        example_1_quick_notification()
        example_2_template_based_notification()
        example_3_event_driven_notifications()
        example_4_user_preferences()
        example_5_device_token_management()
        example_6_batch_notifications()
        example_7_notification_analytics()
        example_8_custom_notification_service()
        example_9_setup_default_system()
        example_10_real_world_scenario()

        print("\n" + "=" * 50)
        print("✅ All examples completed successfully!")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # This allows running examples from Django shell
    # python manage.py shell -c "from notification.examples import run_all_examples; run_all_examples()"
    run_all_examples()
