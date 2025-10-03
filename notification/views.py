import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    DeviceToken,
    Notification,
    NotificationBatch,
    NotificationEvent,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .rules_engine import NotificationRulesEngine
from .serializers import (
    BulkNotificationSerializer,
    DeviceTokenSerializer,
    DeviceTokenUpdateSerializer,
    NotificationActionSerializer,
    NotificationBatchSerializer,
    NotificationEventSerializer,
    NotificationListSerializer,
    NotificationRuleSerializer,
    NotificationSerializer,
    NotificationStatsSerializer,
    NotificationTemplateSerializer,
    TriggerEventSerializer,
    UserNotificationPreferenceSerializer,
)
from .services import DeliveryStatusTracker
from .tasks import process_notification_batch_task, send_notification_task

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationTemplatePagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


# Template Management APIs
class NotificationTemplateListCreateView(generics.ListCreateAPIView):
    """List and create notification templates"""

    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationTemplatePagination

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by template type
        template_type = self.request.query_params.get("type")
        if template_type:
            queryset = queryset.filter(template_type=template_type)

        # Filter by active status
        is_active = self.request.query_params.get("active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Search by name
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")


class NotificationTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a notification template"""

    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]


# Rule Management APIs
class NotificationRuleListCreateView(generics.ListCreateAPIView):
    """List and create notification rules"""

    queryset = NotificationRule.objects.all()
    serializer_class = NotificationRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationTemplatePagination

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by trigger event
        trigger_event = self.request.query_params.get("event")
        if trigger_event:
            queryset = queryset.filter(trigger_event=trigger_event)

        # Filter by active status
        is_active = self.request.query_params.get("active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Search by name
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-priority", "-created_at")


class NotificationRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a notification rule"""

    queryset = NotificationRule.objects.all()
    serializer_class = NotificationRuleSerializer
    permission_classes = [permissions.IsAuthenticated]


# User Preference APIs
class UserNotificationPreferenceView(APIView):
    """Get and update user notification preferences"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get user's notification preferences"""
        try:
            preferences = request.user.notification_preferences
        except UserNotificationPreference.DoesNotExist:
            preferences = UserNotificationPreference.objects.create(user=request.user)

        serializer = UserNotificationPreferenceSerializer(preferences)
        return Response(serializer.data)

    def put(self, request):
        """Update user's notification preferences"""
        try:
            preferences = request.user.notification_preferences
        except UserNotificationPreference.DoesNotExist:
            preferences = UserNotificationPreference.objects.create(user=request.user)

        serializer = UserNotificationPreferenceSerializer(preferences, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Device Token Management APIs
class DeviceTokenListCreateView(generics.ListCreateAPIView):
    """List and create device tokens for the authenticated user"""

    serializer_class = DeviceTokenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user, is_active=True)


class DeviceTokenDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a device token"""

    serializer_class = DeviceTokenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def update_device_token(request):
    """Update or create device token"""
    serializer = DeviceTokenUpdateSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data["token"]
        device_type = serializer.validated_data["device_type"]
        device_id = serializer.validated_data.get("device_id", "")

        # Update or create token
        device_token, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={"user": request.user, "device_type": device_type, "device_id": device_id, "is_active": True},
        )

        response_serializer = DeviceTokenSerializer(device_token)
        return Response({"success": True, "created": created, "token": response_serializer.data})

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Notification APIs
class UserNotificationListView(generics.ListAPIView):
    """List notifications for the authenticated user"""

    serializer_class = NotificationListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationTemplatePagination

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)

        # Filter by notification type
        notification_type = self.request.query_params.get("type")
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by read status
        unread_only = self.request.query_params.get("unread_only")
        if unread_only and unread_only.lower() == "true":
            queryset = queryset.filter(read_at__isnull=True)

        return queryset.order_by("-created_at")


class NotificationDetailView(generics.RetrieveAPIView):
    """Retrieve a specific notification"""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        """Mark notification as read when retrieved"""
        notification = self.get_object()
        if notification.status != "read":
            notification.mark_as_read()
        return super().retrieve(request, *args, **kwargs)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def notification_actions(request):
    """Perform actions on notifications (mark as read, etc.)"""
    serializer = NotificationActionSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        action = serializer.validated_data["action"]
        notification_ids = serializer.validated_data["notification_ids"]

        notifications = Notification.objects.filter(id__in=notification_ids, user=request.user)

        updated_count = 0
        for notification in notifications:
            if action == "read":
                notification.mark_as_read()
                updated_count += 1
            elif action == "unread":
                notification.status = "delivered"
                notification.read_at = None
                notification.save(update_fields=["status", "read_at", "updated_at"])
                updated_count += 1

        return Response({"success": True, "updated_count": updated_count, "action": action})

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def notification_stats(request):
    """Get notification statistics for the user"""
    days = int(request.query_params.get("days", 30))
    stats = DeliveryStatusTracker.get_delivery_stats(user_id=request.user.id, days=days)

    serializer = NotificationStatsSerializer(stats)
    return Response(serializer.data)


# Batch Notification APIs
class NotificationBatchListCreateView(generics.ListCreateAPIView):
    """List and create notification batches"""

    queryset = NotificationBatch.objects.all()
    serializer_class = NotificationBatchSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationTemplatePagination

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at")

    def perform_create(self, serializer):
        """Create batch and schedule processing"""
        batch = serializer.save()

        # Schedule batch processing
        process_notification_batch_task.delay(str(batch.id))


class NotificationBatchDetailView(generics.RetrieveAPIView):
    """Retrieve notification batch details"""

    queryset = NotificationBatch.objects.all()
    serializer_class = NotificationBatchSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_bulk_notifications(request):
    """Create bulk notifications"""
    serializer = BulkNotificationSerializer(data=request.data)
    if serializer.is_valid():
        template_id = serializer.validated_data["template_id"]
        user_ids = serializer.validated_data["user_ids"]
        context_data = serializer.validated_data["context_data"]
        notification_type = serializer.validated_data["notification_type"]
        priority = serializer.validated_data["priority"]
        scheduled_at = serializer.validated_data.get("scheduled_at", timezone.now())

        try:
            template = NotificationTemplate.objects.get(id=template_id)
            users = User.objects.filter(id__in=user_ids)

            # Create notifications
            notifications_created = []
            for user in users:
                try:
                    rendered_content = template.render(context_data)

                    notification = Notification.objects.create(
                        user=user,
                        notification_type=notification_type,
                        title=rendered_content["title"],
                        body=rendered_content["body"],
                        action_url=rendered_content.get("action_url"),
                        icon_url=rendered_content.get("icon_url"),
                        template=template,
                        event_data=context_data,
                        priority=priority,
                        scheduled_at=scheduled_at,
                    )

                    notifications_created.append(notification.id)

                    # Schedule sending
                    if scheduled_at <= timezone.now():
                        send_notification_task.delay(str(notification.id))

                except Exception as e:
                    logger.error(f"Error creating notification for user {user.id}: {e}")
                    continue

            return Response(
                {
                    "success": True,
                    "notifications_created": len(notifications_created),
                    "notification_ids": notifications_created,
                }
            )

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Event Trigger APIs
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def trigger_notification_event(request):
    """Trigger a notification event"""
    serializer = TriggerEventSerializer(data=request.data)
    if serializer.is_valid():
        event_name = serializer.validated_data["event_name"]
        event_data = serializer.validated_data["event_data"]
        user_id = serializer.validated_data.get("user_id")

        try:
            # Trigger the event
            engine = NotificationRulesEngine()
            engine.trigger_event(event_name, event_data, user_id)

            return Response({"success": True, "message": f"Event {event_name} triggered successfully"})

        except Exception as e:
            logger.error(f"Error triggering event {event_name}: {e}")
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Analytics and Reporting APIs
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def notification_analytics(request):
    """Get notification analytics"""
    days = int(request.query_params.get("days", 7))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    # Overall statistics
    total_notifications = Notification.objects.filter(created_at__gte=start_date, created_at__lt=end_date).count()

    # Status breakdown
    status_stats = (
        Notification.objects.filter(created_at__gte=start_date, created_at__lt=end_date)
        .values("status")
        .annotate(count=Count("id"))
    )

    # Type breakdown
    type_stats = (
        Notification.objects.filter(created_at__gte=start_date, created_at__lt=end_date)
        .values("notification_type")
        .annotate(count=Count("id"))
    )

    # Daily breakdown
    daily_stats = []
    for i in range(days):
        day_start = start_date + timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        day_count = Notification.objects.filter(created_at__gte=day_start, created_at__lt=day_end).count()

        daily_stats.append({"date": day_start.date().isoformat(), "count": day_count})

    return Response(
        {
            "period": f"{days}_days",
            "total_notifications": total_notifications,
            "status_breakdown": list(status_stats),
            "type_breakdown": list(type_stats),
            "daily_stats": daily_stats,
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def delivery_status_webhook(request):
    """Webhook endpoint for delivery status updates"""
    notification_id = request.data.get("notification_id")
    status_update = request.data.get("status")
    metadata = request.data.get("metadata", {})

    if not notification_id or not status_update:
        return Response({"error": "notification_id and status are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        DeliveryStatusTracker.update_delivery_status(notification_id, status_update, metadata)

        return Response({"success": True, "message": "Status updated successfully"})

    except Exception as e:
        logger.error(f"Error updating delivery status: {e}")
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Admin APIs
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def system_health(request):
    """Get notification system health status"""
    # Check recent notification processing
    recent_notifications = Notification.objects.filter(created_at__gte=timezone.now() - timedelta(hours=1))

    pending_count = recent_notifications.filter(status="pending").count()
    failed_count = recent_notifications.filter(status="failed").count()
    total_count = recent_notifications.count()

    # Check active device tokens
    active_tokens = DeviceToken.objects.filter(is_active=True).count()

    # Check active rules
    active_rules = NotificationRule.objects.filter(is_active=True).count()

    health_status = "healthy"
    if failed_count > total_count * 0.1:  # More than 10% failure rate
        health_status = "degraded"
    if pending_count > 100:  # Too many pending notifications
        health_status = "degraded"

    return Response(
        {
            "status": health_status,
            "statistics": {
                "recent_notifications": total_count,
                "pending_notifications": pending_count,
                "failed_notifications": failed_count,
                "active_device_tokens": active_tokens,
                "active_rules": active_rules,
            },
            "timestamp": timezone.now().isoformat(),
        }
    )
