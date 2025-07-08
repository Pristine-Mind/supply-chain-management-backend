import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from requests.exceptions import RequestException

from producer.models import Sale, Order


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
        "Idempotency-Key": f"{to_number}-{self.request.id}",
        "Accept": "application/json",
        "Accept-Language": "en-us",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(settings.SPARROWSMS_ENDPOINT, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except RequestException as exc:
        # Try to parse SparrowSMS error response
        if exc.response is not None:
            try:
                data = exc.response.json()
            except ValueError:
                # Non-JSON body, treat as temporary network error
                raise self.retry(exc=exc)
        else:
            # No response at all, network issue
            raise self.retry(exc=exc)

    # Map SparrowSMS response codes to a uniform result
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

    # Retry on unexpected/temporary errors
    if result["code"] != 200 and code not in mapping:
        raise self.retry(exc=Exception(f"SparrowSMS temporary error: {result}"))

    return result

    # try:
    #     response = requests.post(
    #         url="https://sms.sociair.com/api/sms",
    #         headers={
    #             "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIyIiwianRpIjoiMzdjMDMzOWViYzVhYzA4MzM0YTZlNDdmMzk3NTk1MzBjY2E0YTE3YmIwM2U1MGQxZTQ1NWE3NzczNDFhZTdiNjYwMzY0OTRkY2MwZTY1N2UiLCJpYXQiOjE3MzAwOTQwOTcuNjczMzU5LCJuYmYiOjE3MzAwOTQwOTcuNjczMzYzLCJleHAiOjE3NjE2MzAwOTcuNjYxNDI1LCJzdWIiOiIxMzYxIiwic2NvcGVzIjpbXX0.u1TwO2PK7xbPYA_C3NzH818VAJG_P3xtnizMAa-Zj1822TGPFrx_ROWO8TcVUU38eOueGNmO37zmjPKF_TbnW8PkF3FcQWBcF1hH6CR8NTPymMceUFCoomBjZ57qEJWPfMmZbOobslQrExuaQIfTWkvDVyR046DVCnp6yTX9u38TuNtKX9Oc43pNVkHYm9uvWohHvXwAx42oiUDh9NziPxkqTHTUAOiZ8ghLsaen7HgIj-lszfG32m3w5MgGsGiLo-9DwhRSObLP3IdpR1Dtk48wOo-qp_9_RRgRrwkZmalu8rEro95uPya1HQ1q57iGJXNs03hhQml8CxeKJjvUVKNoPhGAEoh3LzjeOd7j2WbYiCjvIXVcZBA8CuJtSMesjMDtbJMgik2U1Am6GfW4TCya5pDArpctrrvJ4DXZmmUo0h6IE9MI1Om-dvxMonxt-BJQrpVWCzbtSZg3f9nelMv7tCPFwK8NZ6zvzojeThTQWEyl96cVLpKc0DdqdR1fMa5hOfnaFxAdCktfwhAvt1B5IeEcQnuuCGB2hWYQqBiyw46_oMiGdhIEDZj6l4DWxFppc-VvGSPu66SRgW-I0Spn22a5ksSVRi-Ts1jQZTwu_LaUaxnMnylnO0RHBFrTZ-URc9S3DK4UhQBpyS4MmBFDIp8GQvhuwZswCsLbJ1o",
    #             "Content-Type": "application/json",
    #             "Accept": "application/json",
    #         },
    #         json={"message": body, "mobile": to_number},
    #     )
    #     response.raise_for_status()
    #     return response.json()
    # except requests.exceptions.RequestException as e:
    #     error_message = e.response.json().get("message") if e.response else str(e)
    #     raise Exception(error_message)
