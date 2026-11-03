from rest_framework import status
from rest_framework.test import APITestCase

from .factories import (
    CustomerFactory,
    OrderFactory,
    ProducerFactory,
    ProductFactory,
    SaleFactory,
)
from .models import Order


class ProducerAPITestCase(APITestCase):

    def setUp(self):
        user = getattr(self, "user", None)
        if not user:
            from user.models import User
            user, _ = User.objects.get_or_create(username="test_auth_user", defaults={"email": "auth@ex.com"})
        self.client.force_authenticate(user=user)
        self.producer = ProducerFactory()
        self.url = "/api/v1/producers/"

    def test_create_producer(self):
        """
        Test creating a producer.
        """
        data = {
            "name": "New Producer",
            "contact": "1234567890",
            "email": "producer@test.com",
            "address": "1234 Test Address",
            "registration_number": "ABC123",
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_producer_list(self):
        """
        Test retrieving the list of producers.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)


class CustomerAPITestCase(APITestCase):

    def setUp(self):
        user = getattr(self, "user", None)
        if not user:
            from user.models import User
            user, _ = User.objects.get_or_create(username="test_auth_user", defaults={"email": "auth@ex.com"})
        self.client.force_authenticate(user=user)
        self.customer = CustomerFactory()
        self.url = "/api/v1/customers/"

    def test_create_customer(self):
        """
        Test creating a customer.
        """
        producer = ProducerFactory.create()
        data = {
            "name": "New Customer",
            "customer_type": "Retailer",
            "contact": "9876543210",
            "email": "customer@test.com",
            "billing_address": "123 Test Billing",
            "shipping_address": "456 Test Shipping",
            "credit_limit": 5000.00,
            "current_balance": 1000.00,
            "producer": producer.id,
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_customer_list(self):
        """
        Test retrieving the list of customers.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)


class ProductAPITestCase(APITestCase):

    def setUp(self):
        user = getattr(self, "user", None)
        if not user:
            from user.models import User
            user, _ = User.objects.get_or_create(username="test_auth_user", defaults={"email": "auth@ex.com"})
        self.client.force_authenticate(user=user)
        self.product = ProductFactory()
        self.url = "/api/v1/products/"

    def test_create_product(self):
        """
        Test creating a product.
        """
        producer = ProducerFactory.create()
        data = {
            "name": "New Product",
            "description": "A new product description",
            "sku": "1234567890123",
            "price": 100.00,
            "cost_price": 80.00,
            "stock": 100,
            "producer": producer.id,
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_product_list(self):
        """
        Test retrieving the list of products.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)


class OrderAPITestCase(APITestCase):

    def setUp(self):
        user = getattr(self, "user", None)
        if not user:
            from user.models import User
            user, _ = User.objects.get_or_create(username="test_auth_user", defaults={"email": "auth@ex.com"})
        self.client.force_authenticate(user=user)
        self.order = OrderFactory.create()
        self.url = "/api/v1/orders/"

    def test_create_order(self):
        """
        Test creating an order.
        """
        customer = CustomerFactory.create()
        product = ProductFactory.create()
        data = {
            "customer": customer.id,
            "product": product.id,
            "quantity": 10,
            "status": Order.Status.PENDING,
            "order_date": "2023-01-01T00:00:00Z",
            "payment_status": Order.Status.PENDING,
            "order_number": 123232,
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_order_list(self):
        """
        Test retrieving the list of orders.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)


class SaleAPITestCase(APITestCase):

    def setUp(self):
        user = getattr(self, "user", None)
        if not user:
            from user.models import User
            user, _ = User.objects.get_or_create(username="test_auth_user", defaults={"email": "auth@ex.com"})
        self.client.force_authenticate(user=user)
        self.sale = SaleFactory()
        self.url = "/api/v1/sales/"

    def test_create_sale(self):
        """
        Test creating a sale.
        """
        order = OrderFactory.create()
        data = {"order": order.id, "quantity": 5, "sale_price": 150.00}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_sale_list(self):
        """
        Test retrieving the list of sales.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
