from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PaymentGatewayInterface(ABC):

    @abstractmethod
    def get_payment_gateways(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def by_customer(self, name: str, email: str, phone: str):
        pass

    @abstractmethod
    def pay(
        self,
        amount: float,
        return_url: str,
        purchase_order_id: str,
        purchase_order_name: str,
        gateway: str,
        bank: Optional[str] = None,
    ):
        pass

    @abstractmethod
    def initiate(self, amount: float, return_url: str, gateway: str, bank: Optional[str] = None):
        pass

    @abstractmethod
    def is_success(self, inquiry: Dict[str, Any], arguments: Optional[Dict[str, Any]] = None) -> bool:
        pass

    @abstractmethod
    def requested_amount(self, inquiry: Dict[str, Any], arguments: Optional[Dict[str, Any]] = None) -> float:
        pass

    @abstractmethod
    def inquiry(self, transaction_id: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pass
