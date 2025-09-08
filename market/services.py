import uuid

import requests
from django.conf import settings


class SparrowSMS:
    def __init__(self):
        # Load from your Django settings
        self.api_url = settings.SPARROWSMS_ENDPOINT
        self.sender = settings.SPARROWSMS_SENDER_ID
        self.api_key = settings.SPARROWSMS_API_KEY
        self.message = None
        self.recipient = None

    def set_message(self, message: str):
        self.message = message

    def set_recipient(self, phone: str):
        self.recipient = phone

    def send_message(self) -> dict:
        """
        Send the SMS via SparrowSMS REST API.
        Returns a dict with keys: code, status, message, sms_code
        """
        if not all([self.api_url, self.sender, self.api_key, self.recipient, self.message]):
            raise ValueError("API credentials, recipient, and message must all be set.")

        payload = {
            "token": self.api_key,
            "to": self.recipient,
            "text": self.message,
            "from": self.sender,
        }

        headers = {
            "Authorization": self.api_key,
            "Idempotency-Key": str(uuid.uuid4()),
            "Accept": "application/json",
            "Accept-Language": "en-us",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            # Attempt to parse Sparrow’s error response
            try:
                data = e.response.json()
            except Exception:
                return {"code": 500, "status": "error", "message": f"Network or parsing error: {e}", "sms_code": None}

        code = str(data.get("response_code", ""))
        mapping = {
            "200": {"code": 200, "status": "success", "message": "Message sent successfully", "sms_code": "200"},
            "1007": {"code": 401, "status": "error", "message": "Invalid Receiver", "sms_code": "1007"},
            "1607": {"code": 401, "status": "error", "message": "Authentication Failure", "sms_code": "1607"},
            "1002": {"code": 401, "status": "error", "message": "Invalid Token", "sms_code": "1002"},
            "1011": {"code": 401, "status": "error", "message": "Unknown Receiver", "sms_code": "1011"},
        }

        return mapping.get(
            code,
            {"code": 400, "status": "error", "message": data.get("message", "Unknown error"), "sms_code": code or "0000"},
        )
