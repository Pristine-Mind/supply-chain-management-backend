# Notification System API Documentation

This document provides comprehensive documentation for the notification system APIs.

## Base URL
```
http://localhost:8000/api/v1/notifications/
```

## Authentication
All endpoints require authentication using Token Authentication:
```
Authorization: Token your_auth_token_here
```

---

## Template Management APIs

### List Templates
**GET** `/templates/`

List all notification templates with filtering and pagination.

**Query Parameters:**
- `type` (string): Filter by template type (`push`, `email`, `sms`, `in_app`)
- `active` (boolean): Filter by active status (`true`, `false`)
- `search` (string): Search by template name
- `limit` (integer): Number of results per page (default: 20)
- `offset` (integer): Pagination offset

**Response:**
```json
{
  "count": 10,
  "next": "http://localhost:8000/api/v1/notifications/templates/?limit=20&offset=20",
  "previous": null,
  "results": [
    {
      "id": "uuid-here",
      "name": "order_confirmed",
      "template_type": "push",
      "title_template": "Order #{order_number} Confirmed!",
      "body_template": "Your order has been confirmed and will be processed soon.",
      "action_url_template": "https://app.example.com/orders/{order_id}",
      "icon_url": "https://example.com/icon.png",
      "variables": ["order_number", "order_id"],
      "is_active": true,
      "created_at": "2024-01-01T10:00:00Z",
      "updated_at": "2024-01-01T10:00:00Z"
    }
  ]
}
```

### Create Template
**POST** `/templates/`

Create a new notification template.

**Request Body:**
```json
{
  "name": "order_confirmed",
  "template_type": "push",
  "title_template": "Order #{order_number} Confirmed!",
  "body_template": "Your order for {product_name} has been confirmed.",
  "action_url_template": "https://app.example.com/orders/{order_id}",
  "icon_url": "https://example.com/icon.png",
  "variables": ["order_number", "product_name", "order_id"],
  "is_active": true
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid-here",
  "name": "order_confirmed",
  "template_type": "push",
  "title_template": "Order #{order_number} Confirmed!",
  "body_template": "Your order for {product_name} has been confirmed.",
  "action_url_template": "https://app.example.com/orders/{order_id}",
  "icon_url": "https://example.com/icon.png",
  "variables": ["order_number", "product_name", "order_id"],
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:00:00Z"
}
```

### Get Template
**GET** `/templates/{id}/`

Retrieve a specific notification template.

**Response:** `200 OK`
```json
{
  "id": "uuid-here",
  "name": "order_confirmed",
  "template_type": "push",
  "title_template": "Order #{order_number} Confirmed!",
  "body_template": "Your order for {product_name} has been confirmed.",
  "action_url_template": "https://app.example.com/orders/{order_id}",
  "icon_url": "https://example.com/icon.png",
  "variables": ["order_number", "product_name", "order_id"],
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:00:00Z"
}
```

### Update Template
**PUT** `/templates/{id}/`

Update a notification template.

**Request Body:** Same as create template

**Response:** `200 OK` (Same structure as get template)

### Delete Template
**DELETE** `/templates/{id}/`

Delete a notification template.

**Response:** `204 No Content`

---

## Rule Management APIs

### List Rules
**GET** `/rules/`

List all notification rules with filtering and pagination.

**Query Parameters:**
- `event` (string): Filter by trigger event
- `active` (boolean): Filter by active status
- `search` (string): Search by rule name
- `limit` (integer): Number of results per page
- `offset` (integer): Pagination offset

**Response:**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid-here",
      "name": "Order Confirmation Rule",
      "description": "Send notification when order is confirmed",
      "trigger_event": "order_confirmed",
      "conditions": [
        {
          "field": "amount",
          "operator": "gt",
          "value": 100
        }
      ],
      "template": "template-uuid",
      "template_name": "order_confirmed",
      "target_users": {
        "event_based": {
          "use_event_user": true
        }
      },
      "delay_minutes": 0,
      "is_active": true,
      "priority": 8,
      "created_at": "2024-01-01T10:00:00Z",
      "updated_at": "2024-01-01T10:00:00Z"
    }
  ]
}
```

### Create Rule
**POST** `/rules/`

Create a new notification rule.

**Request Body:**
```json
{
  "name": "Order Confirmation Rule",
  "description": "Send notification when order is confirmed",
  "trigger_event": "order_confirmed",
  "conditions": [
    {
      "field": "amount",
      "operator": "gt",
      "value": 100
    }
  ],
  "template": "template-uuid",
  "target_users": {
    "event_based": {
      "use_event_user": true
    }
  },
  "delay_minutes": 0,
  "is_active": true,
  "priority": 8
}
```

**Response:** `201 Created` (Same structure as list rules)

### Get Rule
**GET** `/rules/{id}/`

Retrieve a specific notification rule.

### Update Rule
**PUT** `/rules/{id}/`

Update a notification rule.

### Delete Rule
**DELETE** `/rules/{id}/`

Delete a notification rule.

---

## User Preferences APIs

### Get User Preferences
**GET** `/preferences/`

Get the authenticated user's notification preferences.

**Response:** `200 OK`
```json
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
  "timezone": "Asia/Kathmandu",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:00:00Z"
}
```

### Update User Preferences
**PUT** `/preferences/`

Update the authenticated user's notification preferences.

**Request Body:**
```json
{
  "push_enabled": true,
  "email_enabled": false,
  "sms_enabled": false,
  "in_app_enabled": true,
  "order_notifications": true,
  "payment_notifications": true,
  "marketing_notifications": false,
  "delivery_notifications": true,
  "quiet_hours_enabled": true,
  "quiet_start_time": "23:00:00",
  "quiet_end_time": "07:00:00",
  "timezone": "Asia/Kathmandu"
}
```

**Response:** `200 OK` (Updated preferences object)

---

## Device Token Management APIs

### List Device Tokens
**GET** `/device-tokens/`

List the authenticated user's device tokens.

**Response:** `200 OK`
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "token": "fcm_token_here",
      "device_type": "android",
      "device_id": "device_123",
      "is_active": true,
      "last_used": "2024-01-01T10:00:00Z",
      "created_at": "2024-01-01T09:00:00Z"
    }
  ]
}
```

### Register Device Token
**POST** `/device-tokens/`

Register a new device token for push notifications.

**Request Body:**
```json
{
  "token": "fcm_token_or_apns_token_here",
  "device_type": "android",
  "device_id": "unique_device_identifier"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "token": "fcm_token_or_apns_token_here",
  "device_type": "android",
  "device_id": "unique_device_identifier",
  "is_active": true,
  "last_used": "2024-01-01T10:00:00Z",
  "created_at": "2024-01-01T10:00:00Z"
}
```

### Update Device Token
**POST** `/device-tokens/update/`

Update or create a device token (handles duplicates automatically).

**Request Body:**
```json
{
  "token": "updated_token_here",
  "device_type": "ios",
  "device_id": "device_456"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "created": false,
  "token": {
    "id": 2,
    "token": "updated_token_here",
    "device_type": "ios",
    "device_id": "device_456",
    "is_active": true,
    "last_used": "2024-01-01T10:00:00Z",
    "created_at": "2024-01-01T10:00:00Z"
  }
}
```

### Get Device Token
**GET** `/device-tokens/{id}/`

Retrieve a specific device token.

### Update Device Token
**PUT** `/device-tokens/{id}/`

Update a device token.

### Delete Device Token
**DELETE** `/device-tokens/{id}/`

Delete a device token.

---

## User Notifications APIs

### List User Notifications
**GET** `/my-notifications/`

List notifications for the authenticated user.

**Query Parameters:**
- `type` (string): Filter by notification type
- `status` (string): Filter by status (`pending`, `sent`, `delivered`, `read`, `failed`)
- `unread_only` (boolean): Show only unread notifications
- `limit` (integer): Number of results per page
- `offset` (integer): Pagination offset

**Response:** `200 OK`
```json
{
  "count": 15,
  "next": "http://localhost:8000/api/v1/notifications/my-notifications/?limit=20&offset=20",
  "previous": null,
  "results": [
    {
      "id": "notification-uuid",
      "notification_type": "push",
      "title": "Order Confirmed",
      "body": "Your order #ORD-123 has been confirmed.",
      "action_url": "https://app.example.com/orders/123",
      "icon_url": "https://example.com/icon.png",
      "status": "delivered",
      "priority": 8,
      "created_at": "2024-01-01T10:00:00Z",
      "read_at": null
    }
  ]
}
```

### Get Notification
**GET** `/my-notifications/{id}/`

Retrieve a specific notification (automatically marks as read).

**Response:** `200 OK`
```json
{
  "id": "notification-uuid",
  "user": 1,
  "user_name": "John Doe",
  "notification_type": "push",
  "title": "Order Confirmed",
  "body": "Your order #ORD-123 has been confirmed.",
  "action_url": "https://app.example.com/orders/123",
  "icon_url": "https://example.com/icon.png",
  "template": "template-uuid",
  "template_name": "order_confirmed",
  "rule": "rule-uuid",
  "rule_name": "Order Confirmation Rule",
  "event_data": {
    "order_id": 123,
    "order_number": "ORD-123"
  },
  "status": "read",
  "priority": 8,
  "scheduled_at": "2024-01-01T10:00:00Z",
  "sent_at": "2024-01-01T10:00:05Z",
  "delivered_at": "2024-01-01T10:00:10Z",
  "read_at": "2024-01-01T10:05:00Z",
  "error_message": "",
  "retry_count": 0,
  "max_retries": 3,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:05:00Z"
}
```

### Notification Actions
**POST** `/notifications/actions/`

Perform bulk actions on notifications.

**Request Body:**
```json
{
  "action": "read",
  "notification_ids": [
    "notification-uuid-1",
    "notification-uuid-2"
  ]
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "updated_count": 2,
  "action": "read"
}
```

### Notification Statistics
**GET** `/notifications/stats/`

Get notification statistics for the authenticated user.

**Query Parameters:**
- `days` (integer): Number of days to analyze (default: 30)

**Response:** `200 OK`
```json
{
  "total": 50,
  "sent": 48,
  "delivered": 45,
  "failed": 2,
  "read": 30,
  "delivery_rate": 90.0,
  "read_rate": 60.0,
  "failure_rate": 4.0
}
```

---

## Bulk Operations APIs

### Create Bulk Notifications
**POST** `/bulk-create/`

Create notifications for multiple users.

**Request Body:**
```json
{
  "template_id": "template-uuid",
  "user_ids": [1, 2, 3, 4, 5],
  "context_data": {
    "product_name": "Special Offer",
    "discount": "20%"
  },
  "notification_type": "push",
  "priority": 5,
  "scheduled_at": "2024-01-01T15:00:00Z"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "notifications_created": 5,
  "notification_ids": [
    "notification-uuid-1",
    "notification-uuid-2",
    "notification-uuid-3",
    "notification-uuid-4",
    "notification-uuid-5"
  ]
}
```

### List Notification Batches
**GET** `/batches/`

List notification batches.

**Response:** `200 OK`
```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "batch-uuid",
      "name": "Weekly Newsletter",
      "description": "Weekly newsletter with updates",
      "template": "template-uuid",
      "template_name": "newsletter_template",
      "status": "completed",
      "total_count": 100,
      "sent_count": 98,
      "failed_count": 2,
      "scheduled_at": "2024-01-01T10:00:00Z",
      "started_at": "2024-01-01T10:00:05Z",
      "completed_at": "2024-01-01T10:02:30Z",
      "context_data": {
        "newsletter_date": "January 1, 2024"
      },
      "created_by": 1,
      "created_by_name": "Admin User",
      "target_user_count": 100,
      "created_at": "2024-01-01T09:30:00Z",
      "updated_at": "2024-01-01T10:02:30Z"
    }
  ]
}
```

### Create Notification Batch
**POST** `/batches/`

Create a new notification batch.

**Request Body:**
```json
{
  "name": "Weekly Newsletter",
  "description": "Weekly newsletter with updates and offers",
  "template": "template-uuid",
  "context_data": {
    "newsletter_date": "January 8, 2024",
    "featured_products": "Organic Vegetables"
  },
  "scheduled_at": "2024-01-08T10:00:00Z"
}
```

**Response:** `201 Created` (Batch object)

### Get Notification Batch
**GET** `/batches/{id}/`

Retrieve a specific notification batch.

---

## Event Trigger APIs

### Trigger Event
**POST** `/trigger-event/`

Manually trigger a notification event.

**Request Body:**
```json
{
  "event_name": "order_confirmed",
  "event_data": {
    "order_id": 123,
    "order_number": "ORD-123",
    "customer_name": "John Doe",
    "product_name": "Organic Vegetables",
    "total_amount": 1500.0,
    "status": "confirmed"
  },
  "user_id": 1
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Event order_confirmed triggered successfully"
}
```

---

## Analytics APIs

### Notification Analytics
**GET** `/analytics/`

Get comprehensive notification analytics.

**Query Parameters:**
- `days` (integer): Number of days to analyze (default: 7)

**Response:** `200 OK`
```json
{
  "period": "7_days",
  "total_notifications": 500,
  "status_breakdown": [
    {"status": "delivered", "count": 450},
    {"status": "failed", "count": 25},
    {"status": "pending", "count": 25}
  ],
  "type_breakdown": [
    {"notification_type": "push", "count": 400},
    {"notification_type": "email", "count": 75},
    {"notification_type": "sms", "count": 25}
  ],
  "daily_stats": [
    {"date": "2024-01-01", "count": 75},
    {"date": "2024-01-02", "count": 80},
    {"date": "2024-01-03", "count": 65}
  ]
}
```

---

## System Health APIs

### System Health Check
**GET** `/health/`

Check the health of the notification system.

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "statistics": {
    "recent_notifications": 150,
    "pending_notifications": 5,
    "failed_notifications": 3,
    "active_device_tokens": 1250,
    "active_rules": 15
  },
  "timestamp": "2024-01-01T10:00:00Z"
}
```

---

## Webhook APIs

### Delivery Status Webhook
**POST** `/delivery-status/`

Webhook endpoint for external services to update notification delivery status.

**Request Body:**
```json
{
  "notification_id": "notification-uuid",
  "status": "delivered",
  "metadata": {
    "delivery_time": "2024-01-01T10:00:10Z",
    "provider": "FCM"
  }
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Status updated successfully"
}
```

---

## Error Responses

### Common Error Codes

**400 Bad Request**
```json
{
  "error": "Invalid request data",
  "details": {
    "field_name": ["This field is required."]
  }
}
```

**401 Unauthorized**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**403 Forbidden**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

**404 Not Found**
```json
{
  "detail": "Not found."
}
```

**500 Internal Server Error**
```json
{
  "error": "Internal server error",
  "message": "An unexpected error occurred"
}
```

---

## Rate Limiting

The API implements rate limiting to prevent abuse:
- **Anonymous users**: 100 requests per hour
- **Authenticated users**: 1000 requests per hour
- **Bulk operations**: 10 requests per minute

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1641024000
```

---

## Pagination

List endpoints support pagination with the following parameters:
- `limit`: Number of results per page (default: 20, max: 100)
- `offset`: Number of results to skip

Pagination response format:
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/v1/notifications/templates/?limit=20&offset=20",
  "previous": null,
  "results": []
}
```

---

## Filtering and Search

Most list endpoints support filtering and search:
- Use query parameters for filtering
- Use `search` parameter for text search
- Multiple filters can be combined

Example:
```
GET /api/v1/notifications/templates/?type=push&active=true&search=order
```

---

## Best Practices

1. **Authentication**: Always include authentication token in headers
2. **Error Handling**: Check response status codes and handle errors appropriately
3. **Rate Limiting**: Respect rate limits and implement exponential backoff
4. **Pagination**: Use pagination for large datasets
5. **Webhooks**: Implement proper webhook validation for delivery status updates
6. **Testing**: Use the test endpoints to verify integration before production
