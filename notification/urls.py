from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "notification"

urlpatterns = [
    # Template Management
    path("templates/", views.NotificationTemplateListCreateView.as_view(), name="template-list-create"),
    path("templates/<uuid:pk>/", views.NotificationTemplateDetailView.as_view(), name="template-detail"),
    # Rule Management
    path("rules/", views.NotificationRuleListCreateView.as_view(), name="rule-list-create"),
    path("rules/<uuid:pk>/", views.NotificationRuleDetailView.as_view(), name="rule-detail"),
    # User Preferences
    path("preferences/", views.UserNotificationPreferenceView.as_view(), name="user-preferences"),
    # Device Token Management
    path("device-tokens/", views.DeviceTokenListCreateView.as_view(), name="device-token-list-create"),
    path("device-tokens/<int:pk>/", views.DeviceTokenDetailView.as_view(), name="device-token-detail"),
    path("device-tokens/update/", views.update_device_token, name="device-token-update"),
    # User Notifications
    path("my-notifications/", views.UserNotificationListView.as_view(), name="user-notifications"),
    path("my-notifications/<uuid:pk>/", views.NotificationDetailView.as_view(), name="notification-detail"),
    path("notifications/actions/", views.notification_actions, name="notification-actions"),
    path("notifications/stats/", views.notification_stats, name="notification-stats"),
    # Batch Notifications
    path("batches/", views.NotificationBatchListCreateView.as_view(), name="batch-list-create"),
    path("batches/<uuid:pk>/", views.NotificationBatchDetailView.as_view(), name="batch-detail"),
    path("bulk-create/", views.create_bulk_notifications, name="bulk-create"),
    # Event Triggers
    path("trigger-event/", views.trigger_notification_event, name="trigger-event"),
    # Analytics and Reporting
    path("analytics/", views.notification_analytics, name="analytics"),
    # Webhooks and Status Updates
    path("delivery-status/", views.delivery_status_webhook, name="delivery-status-webhook"),
    # System Health
    path("health/", views.system_health, name="system-health"),
]
