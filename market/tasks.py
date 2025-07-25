import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.core.management import call_command
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from requests.exceptions import RequestException

from producer.models import Order, Sale


@shared_task
def send_email(to_email, subject, template_name, context):
    if context and isinstance(context, dict) and "sale_id" in context:
        try:
            context["sale_obj"] = Sale.objects.get(id=context["sale_id"])
        except Sale.DoesNotExist:
            context["sale_obj"] = None
    # Add Order object if needed
    if context and isinstance(context, dict) and "order_id" in context:
        try:
            context["order_obj"] = Order.objects.get(id=context["order_id"])
        except Order.DoesNotExist:
            context["order_obj"] = None
    html_message = render_to_string(template_name, context)
    send_mail(
        subject=subject,
        message=strip_tags(html_message),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        html_message=html_message,
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms(self, to_number: str, body: str) -> dict:
    """
    Send an SMS via SparrowSMS.
    Retries up to 3 times on failure, waiting 60s between attempts.
    Returns a dict with keys: code, status, message, sms_code.
    """
    payload = {
        "token": settings.SPARROWSMS_API_KEY,
        "from": settings.SPARROWSMS_SENDER_ID,
        "to": to_number,
        "text": body,
    }
    headers = {
        "Authorization": settings.SPARROWSMS_API_KEY,
        "Idempotency-Key": f"{to_number}",
        "Accept": "application/json",
        "Accept-Language": "en-us",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(settings.SPARROWSMS_ENDPOINT, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except RequestException as exc:
        if exc.response is not None:
            try:
                data = exc.response.json()
            except ValueError:
                raise Exception(exc)
        else:
            raise Exception(exc)

    code = str(data.get("response_code", ""))
    mapping = {
        "200": {"code": 200, "status": "success", "message": "Message sent successfully", "sms_code": "200"},
        "1007": {"code": 401, "status": "error", "message": "Invalid Receiver", "sms_code": "1007"},
        "1607": {"code": 401, "status": "error", "message": "Authentication Failure", "sms_code": "1607"},
        "1002": {"code": 401, "status": "error", "message": "Invalid Token", "sms_code": "1002"},
        "1011": {"code": 401, "status": "error", "message": "Unknown Receiver", "sms_code": "1011"},
    }

    result = mapping.get(
        code,
        {
            "code": 400,
            "status": "error",
            "message": data.get("message", "Unknown error"),
            "sms_code": code or "0000",
        },
    )

    if result["code"] != 200 and code not in mapping:
        raise Exception(f"SparrowSMS temporary error: {result}")

    return result


@shared_task
def update_recent_purchases():
    """
    Celery task to update recent_purchases_count for all marketplace products.
    This should be scheduled to run periodically (e.g., every hour).
    """
    from django.core.management import call_command

    call_command("update_recent_purchases")
    return "Successfully updated recent purchases count"
