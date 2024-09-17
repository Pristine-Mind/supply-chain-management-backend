from rest_framework import status
from rest_framework.test import APITestCase

from .factories import UserFactory, MarketplaceProductFactory, PurchaseFactory, BidFactory, ChatMessageFactory
from .models import Purchase, Bid, ChatMessage


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
