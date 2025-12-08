from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from market.factories import MarketplaceProductFactory, UserFactory
from market.models import ShoppableVideo, VideoLike


class ShoppableVideoAPITestCase(APITestCase):
    def setUp(self):
        self.user = UserFactory(username="testuser")
        self.client.force_authenticate(user=self.user)
        self.product = MarketplaceProductFactory()

        # Create a dummy video file
        self.video_file = SimpleUploadedFile("video.mp4", b"file_content", content_type="video/mp4")

    def test_create_shoppable_video(self):
        url = reverse("shoppable-videos-list")
        data = {
            "video_file": self.video_file,
            "title": "Awesome Product Video",
            "description": "Check out this product!",
            "product_id": self.product.id,
        }
        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ShoppableVideo.objects.count(), 1)
        video = ShoppableVideo.objects.first()
        self.assertEqual(video.uploader, self.user)
        self.assertEqual(video.product, self.product)
        self.assertEqual(video.title, "Awesome Product Video")

    def test_create_shoppable_video_invalid_extension(self):
        url = reverse("shoppable-videos-list")
        invalid_file = SimpleUploadedFile("video.mov", b"file_content", content_type="video/quicktime")
        data = {
            "video_file": invalid_file,
            "title": "Invalid Video",
            "description": "This should fail",
            "product_id": self.product.id,
        }
        response = self.client.post(url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("video_file", response.data)

    def test_list_shoppable_videos(self):
        video = ShoppableVideo.objects.create(
            uploader=self.user,
            video_file=self.video_file,
            title="Test Video Title",
            description="Test Video",
            product=self.product,
        )

        url = reverse("shoppable-videos-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], video.id)
        self.assertEqual(response.data["results"][0]["title"], "Test Video Title")

    def test_like_video(self):
        video = ShoppableVideo.objects.create(
            uploader=self.user, video_file=self.video_file, description="Test Video", product=self.product
        )

        url = reverse("shoppable-videos-like", args=[video.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["liked"])
        self.assertEqual(response.data["likes_count"], 1)
        self.assertTrue(VideoLike.objects.filter(user=self.user, video=video).exists())

        # Unlike
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["liked"])
        self.assertEqual(response.data["likes_count"], 0)
        self.assertFalse(VideoLike.objects.filter(user=self.user, video=video).exists())

    def test_view_video(self):
        video = ShoppableVideo.objects.create(
            uploader=self.user, video_file=self.video_file, description="Test Video", product=self.product
        )

        url = reverse("shoppable-videos-view", args=[video.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        video.refresh_from_db()
        self.assertEqual(video.views_count, 1)
