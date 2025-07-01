from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .factories import (
    AuditLogFactory,
    CustomerFactory,
    LedgerEntryFactory,
    ProducerFactory,
    ProductFactory,
    SaleFactory,
    UserFactory,
)
from .models import AuditLog, Customer, LedgerEntry, Order, Product, Sale
from .serializers import (
    ProcurementRequestSerializer,
    SalesResponseSerializer,
)
from .supply_chain import SupplyChainService


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def user():
    return UserFactory()


@pytest.mark.django_db
class TestSupplyChainService:
    def test_procurement_process(self, user):
        producer = ProducerFactory(user=user)
        product = ProductFactory(user=user, stock=0)
        CustomerFactory(user=user)

        service = SupplyChainService(user)
        order = service.procurement_process(
            producer_id=producer.id, product_id=product.id, quantity=100, unit_cost=Decimal("500.00")
        )

        assert Order.objects.count() == 1
        assert order.total_price == Decimal("50000.00")
        assert order.status == Order.Status.APPROVED
        assert Product.objects.get(id=product.id).stock == 100

        ledger_entries = LedgerEntry.objects.filter(user=user)
        assert ledger_entries.count() == 4
        assert ledger_entries.filter(account_type=LedgerEntry.AccountType.INVENTORY, debit=True).exists()
        assert ledger_entries.filter(account_type=LedgerEntry.AccountType.VAT_RECEIVABLE).exists()

        audit_logs = AuditLog.objects.filter(user=user)
        assert audit_logs.count() == 1
        assert audit_logs.first().transaction_type == AuditLog.TransactionType.PROCUREMENT

    def test_sales_process(self, user):
        customer = CustomerFactory(user=user)
        product = ProductFactory(user=user, stock=1000)

        service = SupplyChainService(user)
        sale = service.sales_process(
            customer_id=customer.id, product_id=product.id, quantity=50, selling_price=Decimal("750.00")
        )

        assert Sale.objects.count() == 1
        assert sale.sale_price == Decimal("750.00")
        assert Product.objects.get(id=product.id).stock == 950
        assert Customer.objects.get(id=customer.id).current_balance > 0

        ledger_entries = LedgerEntry.objects.filter(user=user)
        assert ledger_entries.count() == 5
        assert ledger_entries.filter(account_type=LedgerEntry.AccountType.SALES_REVENUE, debit=False).exists()
        assert ledger_entries.filter(account_type=LedgerEntry.AccountType.VAT_PAYABLE).exists()

        audit_logs = AuditLog.objects.filter(user=user)
        assert audit_logs.count() == 1
        assert audit_logs.first().transaction_type == AuditLog.TransactionType.SALES

    def test_reconciliation_process(self, user):
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.VAT_PAYABLE, amount=Decimal("6500.00"), debit=False
        )
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.VAT_RECEIVABLE, amount=Decimal("5000.00"), debit=True
        )
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.TDS_PAYABLE, amount=Decimal("750.00"), debit=False
        )
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.SALES_REVENUE, amount=Decimal("37500.00"), debit=False
        )
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.COST_OF_GOODS_SOLD, amount=Decimal("25000.00"), debit=True
        )

        service = SupplyChainService(user)
        result = service.reconciliation_process()

        assert result["net_vat"] == Decimal("1500.00")  # 6500 - 5000
        assert result["tds_total"] == Decimal("750.00")
        assert result["profit"] == Decimal("12500.00")  # 37500 - 25000

        assert LedgerEntry.objects.filter(account_type=LedgerEntry.AccountType.CASH).exists()
        assert AuditLog.objects.filter(transaction_type=AuditLog.TransactionType.RECONCILIATION).exists()


@pytest.mark.django_db
class TestSupplyChainAPI:
    def test_procurement_api(self, authenticated_client, user):
        producer = ProducerFactory(user=user)
        product = ProductFactory(user=user, stock=0)

        data = {"producer_id": producer.id, "product_id": product.id, "quantity": 100, "unit_cost": "500.00"}
        response = authenticated_client.post(reverse("procurement"), data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Order.objects.count() == 1
        assert Product.objects.get(id=product.id).stock == 100
        assert "order_number" in response.data

    def test_sales_api(self, authenticated_client, user):
        customer = CustomerFactory(user=user)
        product = ProductFactory(user=user, stock=1000)

        data = {"customer_id": customer.id, "product_id": product.id, "quantity": 50, "selling_price": "750.00"}
        response = authenticated_client.post(reverse("sales"), data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Sale.objects.count() == 1
        assert Product.objects.get(id=product.id).stock == 950
        assert "sale_price" in response.data

    def test_reconciliation_api(self, authenticated_client, user):
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.VAT_PAYABLE, amount=Decimal("6500.00"), debit=False
        )
        LedgerEntryFactory(
            user=user, account_type=LedgerEntry.AccountType.SALES_REVENUE, amount=Decimal("37500.00"), debit=False
        )

        response = authenticated_client.get(reverse("reconciliation"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["net_vat"] == "6500.00"
        assert response.data["profit"] == "37500.00"

    def test_ledger_entries_api(self, authenticated_client, user):
        LedgerEntryFactory(user=user, amount=Decimal("50000.00"))

        response = authenticated_client.get(reverse("ledger-entry-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["amount"] == "50000.00"

    def test_audit_logs_api(self, authenticated_client, user):
        AuditLogFactory(user=user, amount=Decimal("50000.00"))

        response = authenticated_client.get(reverse("audit-log-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["amount"] == "50000.00"


@pytest.mark.django_db
class TestSerializers:
    def test_procurement_request_serializer(self):
        data = {"producer_id": 1, "product_id": 1, "quantity": 100, "unit_cost": "500.00"}
        serializer = ProcurementRequestSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["quantity"] == 100

    def test_sales_response_serializer(self):
        sale = SaleFactory()
        serializer = SalesResponseSerializer(sale)
        assert "sale_price" in serializer.data
        assert serializer.data["quantity"] == sale.quantity
