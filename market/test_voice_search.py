from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from producer.models import MarketplaceProduct, Producer, Product


class VoiceSearchViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("voice-search")
        self.user = User.objects.create_user(username="testuser", password="password")
        self.producer = Producer.objects.create(
            name="Test Producer", contact="1234567890", address="Test Address", registration_number="12345", user=self.user
        )
        self.product = Product.objects.create(
            producer=self.producer, name="Test Apple", description="A red apple", price=100, sku="APPLE123"
        )
        self.marketplace_product = MarketplaceProduct.objects.create(product=self.product, listed_price=100)

    def test_text_search(self):
        """Test search with text query (Client-side architecture)"""
        data = {"query": "apple"}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["query"], "apple")

    @patch("market.services.VoiceRecognitionService.transcribe_audio")
    def test_voice_search_success(self, mock_transcribe):
        """Test search with audio file (Server-side architecture)"""
        mock_transcribe.return_value = "apple"

        # Create a dummy audio file
        audio_file = SimpleUploadedFile("test.wav", b"dummy_audio_content", content_type="audio/wav")

        data = {"audio_file": audio_file}
        response = self.client.post(self.url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["query"], "apple")
        self.assertEqual(response.data["count"], 1)

    @patch("market.services.VoiceRecognitionService.transcribe_audio")
    def test_voice_search_failure(self, mock_transcribe):
        """Test search with unprocessable audio"""
        mock_transcribe.side_effect = ValueError("Could not understand audio.")

        audio_file = SimpleUploadedFile("test.wav", b"dummy_audio_content", content_type="audio/wav")

        data = {"audio_file": audio_file}
        response = self.client.post(self.url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Could not understand audio.")
