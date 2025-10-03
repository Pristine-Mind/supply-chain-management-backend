# Notification System

A comprehensive notification system for the supply chain management platform with push notifications, email, SMS, and in-app messaging capabilities.

## Features

- **Push Notification Service** - FCM/APNs integration for mobile and web push notifications
- **Notification Rules Engine** - Event-driven architecture for automatic notification triggers
- **Template System** - Dynamic notification templates with variable substitution
- **User Preference Management** - Granular user preferences for notification channels and types
- **Delivery Status Tracking** - Real-time tracking of notification delivery status
- **Batch Processing** - Efficient bulk notification processing with Celery
- **Analytics & Reporting** - Comprehensive analytics and reporting capabilities

## Installation

1. Install required dependencies:
```bash
poetry add firebase-admin pyfcm
```

2. Add to `INSTALLED_APPS` in settings.py:
```python
INSTALLED_APPS = [
    # ... other apps
    "notification.apps.NotificationConfig",
]
```

3. Configure notification settings in settings.py:
```python
# Firebase Cloud Messaging
FCM_SERVICE_ACCOUNT_KEY_PATH = os.environ.get("FCM_SERVICE_ACCOUNT_KEY_PATH")

# Apple Push Notification Service
APNS_TEAM_ID = os.environ.get("APNS_TEAM_ID")
APNS_KEY_ID = os.environ.get("APNS_KEY_ID")
APNS_KEY_PATH = os.environ.get("APNS_KEY_PATH")
APNS_BUNDLE_ID = os.environ.get("APNS_BUNDLE_ID")
APNS_USE_SANDBOX = os.environ.get("APNS_USE_SANDBOX", "True").lower() == "true"
```

4. Run migrations:
```bash
python manage.py makemigrations notification
python manage.py migrate
```

5. Include notification URLs in main urls.py:
```python
urlpatterns = [
    # ... other patterns
    path("api/v1/notifications/", include("notification.urls")),
]
```

## Quick Start

### 1. Create a Notification Template

```python
from notification.models import NotificationTemplate

template = NotificationTemplate.objects.create(
    name="order_confirmed",
    template_type="push",
    title_template="Order #{order_number} Confirmed!",
    body_template="Your order for {product_name} has been confirmed and will be processed soon.",
    variables=["order_number", "product_name", "customer_name"],
    is_active=True
)
```

### 2. Create a Notification Rule

```python
from notification.models import NotificationRule

rule = NotificationRule.objects.create(
    name="Order Confirmation Notification",
    description="Send notification when order is confirmed",
    trigger_event="order_confirmed",
    template=template,
    target_users={
        "event_based": {
            "use_event_user": True
        }
    },
    is_active=True,
    priority=8
)
```

### 3. Trigger Notifications

```python
from notification.rules_engine import trigger_order_event

# Trigger notification when order is confirmed
trigger_order_event(order_instance, 'confirmed')
```

### 4. Register Device Tokens

```python
from notification.models import DeviceToken

# Register user's device token for push notifications
DeviceToken.objects.create(
    user=user,
    token="device_token_here",
    device_type="android",  # or "ios", "web"
    device_id="unique_device_id"
)
```

## API Endpoints

### Template Management
- `GET /api/v1/notifications/templates/` - List templates
- `POST /api/v1/notifications/templates/` - Create template
- `GET /api/v1/notifications/templates/{id}/` - Get template
- `PUT /api/v1/notifications/templates/{id}/` - Update template
- `DELETE /api/v1/notifications/templates/{id}/` - Delete template

### Rule Management
- `GET /api/v1/notifications/rules/` - List rules
- `POST /api/v1/notifications/rules/` - Create rule
- `GET /api/v1/notifications/rules/{id}/` - Get rule
- `PUT /api/v1/notifications/rules/{id}/` - Update rule
- `DELETE /api/v1/notifications/rules/{id}/` - Delete rule

### User Preferences
- `GET /api/v1/notifications/preferences/` - Get user preferences
- `PUT /api/v1/notifications/preferences/` - Update user preferences

### Device Token Management
- `GET /api/v1/notifications/device-tokens/` - List user's device tokens
- `POST /api/v1/notifications/device-tokens/` - Register device token
- `POST /api/v1/notifications/device-tokens/update/` - Update device token

### User Notifications
- `GET /api/v1/notifications/my-notifications/` - List user's notifications
- `GET /api/v1/notifications/my-notifications/{id}/` - Get notification (marks as read)
- `POST /api/v1/notifications/notifications/actions/` - Bulk actions (mark as read/unread)
- `GET /api/v1/notifications/notifications/stats/` - Get user's notification statistics

### Bulk Operations
- `POST /api/v1/notifications/bulk-create/` - Create bulk notifications
- `GET /api/v1/notifications/batches/` - List notification batches
- `POST /api/v1/notifications/batches/` - Create notification batch

### Event Triggers
- `POST /api/v1/notifications/trigger-event/` - Manually trigger notification event

### Analytics
- `GET /api/v1/notifications/analytics/` - Get notification analytics
- `GET /api/v1/notifications/health/` - System health check

## Event-Driven Notifications

The system automatically triggers notifications based on model changes:

### Supported Events
- `order_created` - When a new order is created
- `order_confirmed` - When an order is confirmed
- `order_shipped` - When an order is shipped
- `order_delivered` - When an order is delivered
- `order_cancelled` - When an order is cancelled
- `payment_received` - When payment is successful
- `payment_failed` - When payment fails
- `stock_low` - When product stock is low
- `stock_out` - When product is out of stock
- `delivery_assigned` - When delivery is assigned to transporter
- `delivery_completed` - When delivery is completed
- `user_registered` - When a new user registers

### Custom Events

You can trigger custom events programmatically:

```python
from notification.rules_engine import NotificationRulesEngine

engine = NotificationRulesEngine()
engine.trigger_event('custom_event', {
    'user_id': user.id,
    'message': 'Custom notification message',
    'data': {'key': 'value'}
})
```

## Notification Templates

Templates support variable substitution using Python's string formatting:

```python
title_template = "Hello {customer_name}!"
body_template = "Your order #{order_number} for {product_name} is {status}."
variables = ["customer_name", "order_number", "product_name", "status"]
```

### Template Types
- `push` - Push notifications (FCM/APNs)
- `email` - Email notifications
- `sms` - SMS notifications
- `in_app` - In-app notifications

## User Preferences

Users can control their notification preferences:

```python
{
    "push_enabled": true,
    "email_enabled": true,
    "sms_enabled": false,
    "in_app_enabled": true,
    "order_notifications": true,
    "payment_notifications": true,
    "marketing_notifications": false,
    "delivery_notifications": true,
    "quiet_hours_enabled": true,
    "quiet_start_time": "22:00:00",
    "quiet_end_time": "08:00:00",
    "timezone": "Asia/Kathmandu"
}
```

## Batch Processing

For sending notifications to multiple users:

```python
from notification.models import NotificationBatch

batch = NotificationBatch.objects.create(
    name="Weekly Newsletter",
    template=template,
    context_data={
        "newsletter_title": "Weekly Updates",
        "content": "This week's highlights..."
    },
    created_by=admin_user
)

# Add target users
batch.target_users.set(User.objects.filter(is_active=True))

# Processing will be handled automatically by Celery
```

## Celery Tasks

The system includes several Celery tasks for background processing:

- `send_notification_task` - Send individual notifications
- `process_notification_batch_task` - Process notification batches
- `retry_failed_notifications_task` - Retry failed notifications
- `cleanup_old_notifications_task` - Clean up old notifications
- `send_scheduled_notifications_task` - Send scheduled notifications
- `generate_notification_analytics_task` - Generate analytics reports

## Configuration Examples

### Firebase Configuration

1. Download your Firebase service account key JSON file
2. Set the environment variable:
```bash
export FCM_SERVICE_ACCOUNT_KEY_PATH="/path/to/service-account-key.json"
```

### SMS Configuration (SparrowSMS)

```bash
export SPARROWSMS_API_KEY="your_api_key"
export SPARROWSMS_SENDER_ID="your_sender_id"
export SPARROWSMS_ENDPOINT="https://api.sparrowsms.com/v2/sms/"
```

### Email Configuration

Email notifications use Django's email backend (already configured with SendGrid).

## Monitoring and Analytics

### Health Check

```bash
curl -X GET "http://localhost:8000/api/v1/notifications/health/"
```

### Analytics

```bash
curl -X GET "http://localhost:8000/api/v1/notifications/analytics/?days=7"
```

## Security Considerations

1. **Device Token Security** - Device tokens are masked in admin interface
2. **User Permissions** - Users can only access their own notifications and preferences
3. **Rate Limiting** - Consider implementing rate limiting for notification APIs
4. **Data Privacy** - Notification content should not contain sensitive information

## Troubleshooting

### Common Issues

1. **Notifications not sending**
   - Check Celery worker is running
   - Verify Firebase/APNS credentials
   - Check notification rule conditions

2. **Device tokens not working**
   - Verify token format and device type
   - Check if token is marked as active
   - Ensure Firebase project configuration

3. **Template rendering errors**
   - Verify all required variables are provided
   - Check template syntax

### Logs

Monitor notification logs:
```bash
# Django logs
tail -f logs/django.log | grep notification

# Celery logs
tail -f logs/celery.log | grep notification
```

## Performance Optimization

1. **Database Indexing** - Models include appropriate database indexes
2. **Batch Processing** - Use batch operations for bulk notifications
3. **Celery Queues** - Consider separate queues for different notification types
4. **Cleanup Tasks** - Regular cleanup of old notifications and events

## Testing

Run notification tests:
```bash
python manage.py test notification
```

## Contributing

1. Follow the existing code style
2. Add tests for new features
3. Update documentation
4. Ensure all lint checks pass
