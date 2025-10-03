import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import firebase_admin
import requests
from django.conf import settings
from django.utils import timezone
from firebase_admin import credentials, initialize_app, messaging
from firebase_admin.exceptions import FirebaseError

from .models import DeviceToken, Notification, NotificationEvent

logger = logging.getLogger(__name__)


class NotificationServiceInterface(ABC):
    """Abstract base class for notification services"""

    @abstractmethod
    def send_notification(self, notification: Notification) -> bool:
        """Send a single notification"""
        pass

    @abstractmethod
    def send_bulk_notifications(self, notifications: List[Notification]) -> Dict[str, Any]:
        """Send multiple notifications"""
        pass


class FCMService(NotificationServiceInterface):
    """Firebase Cloud Messaging service for push notifications"""

    def __init__(self):
        self._initialize_firebase()

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not firebase_admin._apps:
                # Initialize Firebase with service account key
                cred_path = getattr(settings, "FCM_SERVICE_ACCOUNT_KEY_PATH", None)
                if cred_path:
                    cred = credentials.Certificate(cred_path)
                    initialize_app(cred)
                else:
                    # Use default credentials (for production with service account)
                    initialize_app()
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

    def send_notification(self, notification: Notification) -> bool:
        """Send push notification via FCM"""
        try:
            # Get user's device tokens
            device_tokens = DeviceToken.objects.filter(
                user=notification.user, is_active=True, device_type__in=["android", "ios", "web"]
            ).values_list("token", flat=True)

            if not device_tokens:
                logger.warning(f"No device tokens found for user {notification.user.id}")
                notification.mark_as_failed("No device tokens available")
                return False

            # Create FCM message
            message_data = {
                "notification_id": str(notification.id),
                "action_url": notification.action_url or "",
                "created_at": notification.created_at.isoformat(),
            }

            # Add custom data from event_data
            if notification.event_data:
                message_data.update(notification.event_data)

            # Create notification payload
            fcm_notification = messaging.Notification(
                title=notification.title, body=notification.body, image=notification.icon_url
            )

            # Android specific configuration
            android_config = messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    icon="ic_notification", color="#FF6B35", sound="default", click_action=notification.action_url
                ),
            )

            # iOS specific configuration
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=notification.title, body=notification.body),
                        badge=1,
                        sound="default",
                        category="GENERAL",
                    )
                )
            )

            # Web push configuration
            webpush_config = messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=notification.title,
                    body=notification.body,
                    icon=notification.icon_url,
                    click_action=notification.action_url,
                )
            )

            success_count = 0
            failed_tokens = []

            # Send to each token individually for better error handling
            for token in device_tokens:
                try:
                    message = messaging.Message(
                        notification=fcm_notification,
                        data=message_data,
                        token=token,
                        android=android_config,
                        apns=apns_config,
                        webpush=webpush_config,
                    )

                    response = messaging.send(message)
                    success_count += 1
                    logger.info(f"Successfully sent notification to token: {token[:10]}...")

                except messaging.UnregisteredError:
                    # Token is invalid, mark as inactive
                    DeviceToken.objects.filter(token=token).update(is_active=False)
                    failed_tokens.append(token)
                    logger.warning(f"Invalid token removed: {token[:10]}...")

                except FirebaseError as e:
                    failed_tokens.append(token)
                    logger.error(f"FCM error for token {token[:10]}...: {e}")

            if success_count > 0:
                notification.mark_as_sent()
                self._log_event(notification, "sent", {"success_count": success_count, "failed_count": len(failed_tokens)})
                return True
            else:
                notification.mark_as_failed(f"Failed to send to all {len(device_tokens)} tokens")
                return False

        except Exception as e:
            logger.error(f"FCM service error: {e}")
            notification.mark_as_failed(str(e))
            return False

    def send_bulk_notifications(self, notifications: List[Notification]) -> Dict[str, Any]:
        """Send multiple notifications in batch"""
        results = {"total": len(notifications), "success": 0, "failed": 0, "errors": []}

        for notification in notifications:
            try:
                if self.send_notification(notification):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Notification {notification.id}: {str(e)}")

        return results

    def _log_event(self, notification: Notification, event_type: str, metadata: Dict = None):
        """Log notification event"""
        NotificationEvent.objects.create(notification=notification, event_type=event_type, metadata=metadata or {})


class APNSService(NotificationServiceInterface):
    """Apple Push Notification Service (for iOS devices)"""

    def __init__(self):
        self.team_id = getattr(settings, "APNS_TEAM_ID", "")
        self.key_id = getattr(settings, "APNS_KEY_ID", "")
        self.key_path = getattr(settings, "APNS_KEY_PATH", "")
        self.bundle_id = getattr(settings, "APNS_BUNDLE_ID", "")
        self.use_sandbox = getattr(settings, "APNS_USE_SANDBOX", True)

    def send_notification(self, notification: Notification) -> bool:
        """Send push notification via APNs (using FCM as primary service)"""
        # For this implementation, we'll use FCM which handles APNs internally
        # This method can be extended for direct APNs integration if needed
        fcm_service = FCMService()
        return fcm_service.send_notification(notification)

    def send_bulk_notifications(self, notifications: List[Notification]) -> Dict[str, Any]:
        """Send multiple notifications via APNs"""
        fcm_service = FCMService()
        return fcm_service.send_bulk_notifications(notifications)


class EmailNotificationService(NotificationServiceInterface):
    """Email notification service"""

    def send_notification(self, notification: Notification) -> bool:
        """Send email notification"""
        try:
            from django.conf import settings
            from django.core.mail import send_mail

            subject = notification.title
            message = notification.body
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
            recipient_list = [notification.user.email]

            if not notification.user.email:
                notification.mark_as_failed("User has no email address")
                return False

            send_mail(
                subject=subject, message=message, from_email=from_email, recipient_list=recipient_list, fail_silently=False
            )

            notification.mark_as_sent()
            self._log_event(notification, "sent")
            return True

        except Exception as e:
            logger.error(f"Email service error: {e}")
            notification.mark_as_failed(str(e))
            return False

    def send_bulk_notifications(self, notifications: List[Notification]) -> Dict[str, Any]:
        """Send multiple email notifications"""
        results = {"total": len(notifications), "success": 0, "failed": 0, "errors": []}

        for notification in notifications:
            try:
                if self.send_notification(notification):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Notification {notification.id}: {str(e)}")

        return results

    def _log_event(self, notification: Notification, event_type: str, metadata: Dict = None):
        """Log notification event"""
        NotificationEvent.objects.create(notification=notification, event_type=event_type, metadata=metadata or {})


class SMSNotificationService(NotificationServiceInterface):
    """SMS notification service"""

    def __init__(self):
        self.api_key = getattr(settings, "SPARROWSMS_API_KEY", "")
        self.sender_id = getattr(settings, "SPARROWSMS_SENDER_ID", "")
        self.endpoint = getattr(settings, "SPARROWSMS_ENDPOINT", "")

    def send_notification(self, notification: Notification) -> bool:
        """Send SMS notification"""
        try:
            # Check if user has phone number
            if not hasattr(notification.user, "phone_number") or not notification.user.phone_number:
                notification.mark_as_failed("User has no phone number")
                return False

            # Prepare SMS data
            sms_data = {
                "token": self.api_key,
                "from": self.sender_id,
                "to": str(notification.user.phone_number),
                "text": f"{notification.title}\n{notification.body}",
            }

            # Send SMS via SparrowSMS API
            response = requests.post(self.endpoint, data=sms_data, timeout=30)

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("response_code") == "200":
                    notification.mark_as_sent()
                    self._log_event(notification, "sent", {"sms_id": response_data.get("id")})
                    return True
                else:
                    error_msg = response_data.get("error_message", "Unknown SMS error")
                    notification.mark_as_failed(error_msg)
                    return False
            else:
                notification.mark_as_failed(f"SMS API error: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"SMS service error: {e}")
            notification.mark_as_failed(str(e))
            return False

    def send_bulk_notifications(self, notifications: List[Notification]) -> Dict[str, Any]:
        """Send multiple SMS notifications"""
        results = {"total": len(notifications), "success": 0, "failed": 0, "errors": []}

        for notification in notifications:
            try:
                if self.send_notification(notification):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Notification {notification.id}: {str(e)}")

        return results

    def _log_event(self, notification: Notification, event_type: str, metadata: Dict = None):
        """Log notification event"""
        NotificationEvent.objects.create(notification=notification, event_type=event_type, metadata=metadata or {})


class NotificationServiceFactory:
    """Factory class to get appropriate notification service"""

    _services = {
        "push": FCMService,
        "email": EmailNotificationService,
        "sms": SMSNotificationService,
        "in_app": None,  # In-app notifications are handled differently
    }

    @classmethod
    def get_service(cls, notification_type: str) -> Optional[NotificationServiceInterface]:
        """Get notification service instance"""
        service_class = cls._services.get(notification_type)
        if service_class:
            return service_class()
        return None

    @classmethod
    def send_notification(cls, notification: Notification) -> bool:
        """Send notification using appropriate service"""
        service = cls.get_service(notification.notification_type)
        if service:
            return service.send_notification(notification)
        else:
            logger.error(f"No service available for notification type: {notification.notification_type}")
            notification.mark_as_failed(f"No service available for type: {notification.notification_type}")
            return False


class DeliveryStatusTracker:
    """Track delivery status of notifications"""

    @staticmethod
    def update_delivery_status(notification_id: str, status: str, metadata: Dict = None):
        """Update delivery status of a notification"""
        try:
            notification = Notification.objects.get(id=notification_id)

            if status == "delivered":
                notification.mark_as_delivered()
            elif status == "failed":
                error_msg = metadata.get("error", "Delivery failed") if metadata else "Delivery failed"
                notification.mark_as_failed(error_msg)
            elif status == "read":
                notification.mark_as_read()

            # Log the event
            NotificationEvent.objects.create(notification=notification, event_type=status, metadata=metadata or {})

        except Notification.DoesNotExist:
            logger.error(f"Notification not found: {notification_id}")
        except Exception as e:
            logger.error(f"Error updating delivery status: {e}")

    @staticmethod
    def get_delivery_stats(user_id: Optional[int] = None, days: int = 30) -> Dict[str, Any]:
        """Get delivery statistics"""
        from datetime import timedelta

        from django.db.models import Count, Q

        queryset = Notification.objects.filter(created_at__gte=timezone.now() - timedelta(days=days))

        if user_id:
            queryset = queryset.filter(user_id=user_id)

        stats = queryset.aggregate(
            total=Count("id"),
            sent=Count("id", filter=Q(status="sent")),
            delivered=Count("id", filter=Q(status="delivered")),
            failed=Count("id", filter=Q(status="failed")),
            read=Count("id", filter=Q(status="read")),
        )

        # Calculate rates
        total = stats["total"]
        if total > 0:
            stats["delivery_rate"] = round((stats["delivered"] / total) * 100, 2)
            stats["read_rate"] = round((stats["read"] / total) * 100, 2)
            stats["failure_rate"] = round((stats["failed"] / total) * 100, 2)
        else:
            stats["delivery_rate"] = 0
            stats["read_rate"] = 0
            stats["failure_rate"] = 0

        return stats
