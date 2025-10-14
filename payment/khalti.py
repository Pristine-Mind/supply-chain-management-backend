import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.http import HttpResponseRedirect

from .interfaces import PaymentGatewayInterface

logger = logging.getLogger(__name__)


class Khalti(PaymentGatewayInterface):
    """Khalti Payment Gateway Implementation"""

    def __init__(self):
        self.amount: Optional[float] = None
        self.base_url: str = "https://dev.khalti.com/api/v2/"
        self.purchase_order_id: Optional[str] = None
        self.purchase_order_name: Optional[str] = None
        self.inquiry_response: Optional[Dict[str, Any]] = None

        self.customer_name: Optional[str] = None
        self.customer_phone: Optional[str] = None
        self.customer_email: Optional[str] = None

        self.secret_key = getattr(settings, "KHALTI_SECRET_KEY", "")

        # Log initialization details
        logger.info(f"Initializing Khalti: base_url={self.base_url}, secret_key={'SET' if self.secret_key else 'NOT SET'}")
        if not self.secret_key:
            logger.error("Khalti secret key is not set in settings!")

    def filter_keys_from_array_objects(self, data: List[Dict[str, Any]], keys_to_show: List[str]) -> List[Dict[str, Any]]:
        logger.debug(f"Filtering keys {keys_to_show} from array objects: {data}")
        """Filter specific keys from array of objects"""
        return [{key: item.get(key) for key in keys_to_show if key in item} for item in data]

    def get_payment_gateways(self) -> List[Dict[str, Any]]:
        """Get payment gateways from Khalti API"""
        logger.info("Fetching payment gateways from Khalti API...")
        try:
            logger.debug("Requesting payment gateways from https://dev.khalti.com/api/v5/payment-gateway/")
            response = requests.get("https://dev.khalti.com/api/v5/payment-gateway/")

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and "data" in data:
                    logger.info("Successfully fetched payment gateways from Khalti API.")
                    return data["data"]
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch payment gateways from API: {e}")

        try:
            logger.debug("Requesting ebanking and mobile banking options from Khalti API...")
            ebanking_response = requests.get("https://dev.khalti.com/api/v5/bank/", {"payment_type": "ebanking"})
            ebanking_items = []
            if ebanking_response.status_code == 200:
                ebanking_data = ebanking_response.json()
                ebanking_items = self.filter_keys_from_array_objects(
                    ebanking_data.get("records", []), ["idx", "name", "logo"]
                )

            mobanking_response = requests.get("https://dev.khalti.com/api/v5/bank/", {"payment_type": "mobilecheckout"})
            mobanking_items = []
            if mobanking_response.status_code == 200:
                mobanking_data = mobanking_response.json()
                mobanking_items = self.filter_keys_from_array_objects(
                    mobanking_data.get("records", []), ["idx", "name", "logo"]
                )
            logger.info("Successfully fetched fallback payment gateway options.")

            return [
                {
                    "slug": "SCT",
                    "name": "SCT Card",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/sct.svg",
                    "items": [],
                },
                {
                    "slug": "KHALTI",
                    "name": "Khalti Wallet",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/wallet.svg",
                    "items": [],
                },
                {
                    "slug": "CONNECT_IPS",
                    "name": "Connect IPS",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/connect-ips.svg",
                    "items": [],
                },
                {
                    "slug": "MOBILE_BANKING",
                    "name": "Mobile Banking",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/mbanking.svg",
                    "items": mobanking_items,
                },
                {
                    "slug": "EBANKING",
                    "name": "E-Banking",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/ebanking.svg",
                    "items": ebanking_items,
                },
            ]
        except requests.RequestException as e:
            logger.error(f"Failed to fetch bank options: {e}")
            return [
                {
                    "slug": "SCT",
                    "name": "SCT Card",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/sct.svg",
                    "items": [],
                },
                {
                    "slug": "KHALTI",
                    "name": "Khalti Wallet",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/wallet.svg",
                    "items": [],
                },
                {
                    "slug": "CONNECT_IPS",
                    "name": "Connect IPS",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/connect-ips.svg",
                    "items": [],
                },
                {
                    "slug": "MOBILE_BANKING",
                    "name": "Mobile Banking",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/mbanking.svg",
                    "items": [],
                },
                {
                    "slug": "EBANKING",
                    "name": "E-Banking",
                    "logo": "https://khalti-static.s3.ap-south-1.amazonaws.com/media/kpg/ebanking.svg",
                    "items": [],
                },
            ]

    def by_customer(self, name: str, email: str, phone: str):
        logger.info(f"Setting customer info: name={name}, email={email}, phone={phone}")
        """Set customer information"""
        self.customer_name = name
        self.customer_email = email
        self.customer_phone = phone
        return self

    def pay(
        self,
        amount: float,
        return_url: str,
        purchase_order_id: str,
        purchase_order_name: str,
        gateway: str,
        bank: Optional[str] = None,
    ):
        logger.info(
            f"Initiating payment: amount={amount}, return_url={return_url}, purchase_order_id={purchase_order_id}, purchase_order_name={purchase_order_name}, gateway={gateway}, bank={bank}"
        )
        """Perform payment process"""
        self.purchase_order_id = purchase_order_id
        self.purchase_order_name = purchase_order_name
        return self.initiate(amount, return_url, gateway, bank)

    def initiate(
        self, amount: float, return_url: str, gateway: str, bank: Optional[str] = None
    ) -> Union[HttpResponseRedirect, Dict[str, Any]]:
        logger.info(
            f"Starting Khalti payment initiation: amount={amount}, return_url={return_url}, gateway={gateway}, bank={bank}"
        )
        """Initiate Payment Gateway Transaction"""
        # Convert amount to paisa (multiply by 100) and use test amount if in debug mode
        self.amount = 1000 if settings.DEBUG else (amount * 100)

        process_url = urljoin(self.base_url, "epayment/initiate/")

        # Build the data payload
        data = {
            "return_url": settings.KHALTI_RETURN_URL,
            "website_url": getattr(settings, "SITE_URL", "http://localhost:8000"),
            "amount": int(amount * 100),  # Convert to paisa
            "purchase_order_id": self.purchase_order_id,
            "purchase_order_name": self.purchase_order_name,
            "modes": [gateway],
        }
        if bank:
            data["bank"] = bank

        headers = {"Content-Type": "application/json", "Authorization": f"key {self.secret_key}"}

        # Log all request details for debugging
        logger.info(f"Khalti initiate called with: process_url={process_url}, data={data}, headers={headers}")

        try:
            response = requests.post(process_url, json=data, headers=headers)
            logger.info(f"Khalti initiate response: {response.status_code} - {response.text}")

            if response.status_code == 200:
                response_data = response.json()
                payment_url = response_data.get("payment_url")
                if payment_url:
                    logger.info(f"Khalti payment URL received: {payment_url}")
                    return HttpResponseRedirect(payment_url)
                else:
                    logger.error(f"Payment URL not found in Khalti response: {response_data}")
                    raise Exception("Payment URL not found in response")
            else:
                logger.error(f"Khalti transaction failed with status {response.status_code}: {response.text}")
                raise Exception(f"Khalti transaction failed with status {response.status_code}: {response.text}")

        except requests.RequestException as e:
            logger.error(f"Khalti transaction request failed: {e}")
            raise Exception("Khalti transaction failed")

    def is_success(self, inquiry: Dict[str, Any], arguments: Optional[Dict[str, Any]] = None) -> bool:
        logger.debug(f"Checking Khalti transaction success for inquiry: {inquiry}")
        """Check if payment transaction was successful"""
        return inquiry.get("status") == "Completed"

    def requested_amount(self, inquiry: Dict[str, Any], arguments: Optional[Dict[str, Any]] = None) -> float:
        logger.debug(f"Getting requested amount from inquiry: {inquiry}")
        """Get requested amount from inquiry response"""
        return float(inquiry.get("total_amount", 0))

    def inquiry(self, transaction_id: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"Performing Khalti inquiry for transaction_id: {transaction_id}")
        """Payment status lookup request"""
        process_url = urljoin(self.base_url, "epayment/lookup/")

        payload = {"pidx": transaction_id}

        headers = {"Content-Type": "application/json", "Authorization": f"key {self.secret_key}"}

        logger.debug(f"Khalti inquiry called with: process_url={process_url}, payload={payload}, headers={headers}")
        try:
            response = requests.post(process_url, json=payload, headers=headers)
            self.inquiry_response = response.json()
            logger.info(f"Khalti inquiry response: {response.status_code} - {self.inquiry_response}")
            return self.inquiry_response
        except requests.RequestException as e:
            logger.error(f"Khalti inquiry request failed: {e}")
            raise Exception("Khalti inquiry failed")
