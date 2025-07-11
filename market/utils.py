import hashlib
import logging
from threading import Thread

import requests
from django.conf import settings

from .models import Notification

logger = logging.getLogger(__name__)


def generate_signature(data, signature_key):
    sorted_data = "".join([f"{k}={v}" for k, v in sorted(data.items())])
    return hashlib.sha512((sorted_data + signature_key).encode("utf-8")).hexdigest()


class SMSService:
    """
    Service class for sending SMS notifications using SparrowSMS API.
    """

    def __init__(self):
        self.token = settings.SMS_TOKEN
        self.api_url = settings.SMS_API_URL
        self.sender = settings.SMS_SENDER

    def send_sms(self, phone_number, message):
        """
        Send SMS using SparrowSMS API.

        Args:
            phone_number (str): The recipient's phone number
            message (str): The message content to send

        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        try:
            # Prepare the payload for SparrowSMS API
            payload = {"token": self.token, "from": self.sender, "to": phone_number, "text": message}

            # Make the API request
            response = requests.post(self.api_url, data=payload, timeout=30)

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("status") == "success":
                    logger.info(f"SMS sent successfully to {phone_number}")
                    return True
                else:
                    logger.error(f"SMS API error: {response_data}")
                    return False
            else:
                logger.error(f"SMS API request failed with status code: {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"SMS API request exception: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {str(e)}")
            return False

    def send_sms_async(self, phone_number, message):
        """
        Send SMS asynchronously to avoid blocking the main thread.

        Args:
            phone_number (str): The recipient's phone number
            message (str): The message content to send
        """

        def _send_sms():
            try:
                self.send_sms(phone_number, message)
            except Exception as e:
                logger.error(f"Error in async SMS sending: {str(e)}")

        # Start SMS sending in a separate thread
        thread = Thread(target=_send_sms)
        thread.daemon = True
        thread.start()

    def send_payment_confirmation_sms(self, payment):
        """
        Send payment confirmation SMS to the buyer.

        Args:
            payment: Payment object containing purchase details

        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        try:
            # Get buyer's phone number
            buyer = payment.purchase.buyer
            user_profile = buyer.user_profile

            if not user_profile.phone_number:
                logger.warning(f"No phone number found for user {buyer.username}")
                return False

            # Prepare the message
            message = (
                f"Payment Confirmation: Your payment of NPR {payment.amount} "
                f"for order #{payment.purchase.id} has been completed successfully. "
                f"Thank you for your purchase!"
            )

            # Send SMS asynchronously to avoid blocking payment processing
            self.send_sms_async(user_profile.phone_number, message)
            return True

        except Exception as e:
            logger.error(f"Error sending payment confirmation SMS: {str(e)}")
            return False

    def send_order_status_sms(self, payment, status_message):
        """
        Send order status update SMS to the buyer.

        Args:
            payment: Payment object containing purchase details
            status_message (str): Status message to send

        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        try:
            # Get buyer's phone number
            buyer = payment.purchase.buyer
            user_profile = buyer.user_profile

            if not user_profile.phone_number:
                logger.warning(f"No phone number found for user {buyer.username}")
                return False

            # Prepare the message
            message = f"Order Update: {status_message} " f"Order #{payment.purchase.id} - NPR {payment.amount}"

            # Send SMS asynchronously to avoid blocking order processing
            self.send_sms_async(user_profile.phone_number, message)
            return True

        except Exception as e:
            logger.error(f"Error sending order status SMS: {str(e)}")
            return False


# Create a global instance of the SMS service
sms_service = SMSService()


def notify_event(
    user,
    notif_type,
    message,
    via_in_app=False,
    via_email=False,
    via_sms=False,
    email_addr=None,
    sms_number=None,
    email_tpl=None,
    email_ctx=None,
    sms_body=None,
):
    # In-app
    if via_in_app:
        Notification.objects.create(
            user=user,
            notification_type=notif_type,
            channel=Notification.Channel.IN_APP,
            message=message,
        )

    # Email
    if via_email and email_addr and email_tpl and email_ctx is not None:
        Notification.objects.create(
            user=user,
            notification_type=notif_type,
            channel=Notification.Channel.EMAIL,
            message=message,
        )
        from .tasks import send_email

        send_email.delay(
            to_email=email_addr,
            subject=message[:50],
            template_name=email_tpl,
            context=email_ctx,
        )

    # SMS
    if via_sms and sms_number and sms_body:
        Notification.objects.create(
            user=user,
            notification_type=notif_type,
            channel=Notification.Channel.SMS,
            message=message,
        )
        from .tasks import send_sms

        send_sms.delay(to_number=sms_number, body=sms_body)
