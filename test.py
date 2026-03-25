
import logging
import requests

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def send_sms(phone_number: str, message: str) -> bool:
    """Send an SMS via SparrowSMS API."""
    sms_data = {
        "token": "v2_KOrIlUe1zJuhoGwcy0a3LHeflJ1.rUND",
        "from": "InfoAlert",
        "to": phone_number,
        "text": message,
    }
    try:
        response = requests.post(
            "https://api.sparrowsms.com/v2/sms/",
            data=sms_data,
            timeout=30,
        )
        print(response.status_code)
        print(response.text)
        if response.status_code == 200:
            return response.json().get("response_code") == "200"
        return False
    except Exception as e:
        logger.error(f"SMS send error: {e}")


if __name__ == "__main__":
    result = send_sms("9845333509", "hi")
    logger.info(f"SMS sent: {result}")