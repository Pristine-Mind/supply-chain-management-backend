from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from .factories import (
    BidFactory,
    ChatMessageFactory,
    MarketplaceProductFactory,
    PurchaseFactory,
    UserFactory,
)
from .models import Bid, ChatMessage, MarketplaceUserProduct, Purchase


class PurchaseAPITestCase(APITestCase):
    def setUp(self):
        self.user = UserFactory(username="testuser")
        self.client.login(username="testuser", password="password")

    def test_create_purchase(self):
        self.marketplace_product = MarketplaceProductFactory.create()
        url = "/api/v1/purchases/"
        data = {"product_id": self.marketplace_product.id, "quantity": 2}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Purchase.objects.count(), 1)
        self.assertEqual(Purchase.objects.first().product, self.marketplace_product)

    def test_get_purchases(self):
        self.marketplace_product = MarketplaceProductFactory.create()
        PurchaseFactory.create(buyer=self.user, product=self.marketplace_product, quantity=1)

        url = "/api/v1/purchases/"
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class BidAPITestCase(APITestCase):
    def setUp(self):
        self.user = UserFactory(username="testuser")
        self.client.login(username="testuser", password="password")

    def test_create_bid(self):
        self.marketplace_product = MarketplaceProductFactory.create()
        url = "/api/v1/bids/"
        data = {"product_id": self.marketplace_product.id, "bid_amount": 150.00}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Bid.objects.count(), 1)
        self.assertEqual(Bid.objects.first().product, self.marketplace_product)

    def test_get_bids(self):
        self.marketplace_product = MarketplaceProductFactory.create()
        BidFactory.create(bidder=self.user, product=self.marketplace_product, bid_amount=150.00)

        url = "/api/v1/bids/"
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class ChatAPITestCase(APITestCase):
    def setUp(self):
        self.user = UserFactory(username="testuser")
        self.client.login(username="testuser", password="password")

    def test_create_chat_message(self):
        self.marketplace_product = MarketplaceProductFactory.create()
        url = "/api/v1/chats/"
        data = {"product_id": self.marketplace_product.id, "message": "Is this product available?"}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.first().product, self.marketplace_product)

    def test_get_chat_messages(self):
        self.marketplace_product = MarketplaceProductFactory.create()
        ChatMessageFactory.create(sender=self.user, product=self.marketplace_product)

        url = "/api/v1/chats/"
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class MarketplaceUserProductTests(APITestCase):

    def setUp(self):
        image = SimpleUploadedFile("test_image.jpg", b"file_content", content_type="image/jpeg")

        self.product_data = {
            "name": "Test Product",
            "description": "This is a test product.",
            "price": "10.00",
            "stock": 100,
            "category": "EL",
            "is_verified": True,
            "is_sold": False,
            "image": image,
        }

    def test_list_user_products(self):
        MarketplaceUserProduct.objects.create(**self.product_data)
        url = "/api/v1/marketplace-user-products/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
