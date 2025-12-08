import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from market.models import ShoppableVideo, UserInteraction, VideoLike, VideoSave
from market.recommendation import VideoRecommendationService
from producer.models import MarketplaceProduct

User = get_user_model()


@pytest.mark.django_db
class TestVideoRecommendationService:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.product1 = MarketplaceProduct.objects.create(name="Product 1", category="Electronics", price=100)
        self.product2 = MarketplaceProduct.objects.create(name="Product 2", category="Fashion", price=50)

        self.video1 = ShoppableVideo.objects.create(
            product=self.product1,
            video_file="videos/test1.mp4",
            title="Tech Review",
            tags=["tech", "gadgets"],
            trend_score=0.8,
        )
        self.video2 = ShoppableVideo.objects.create(
            product=self.product2,
            video_file="videos/test2.mp4",
            title="Fashion Haul",
            tags=["fashion", "style"],
            trend_score=0.5,
        )
        self.service = VideoRecommendationService()

    def test_get_user_interests_empty(self):
        interests = self.service.get_user_interests(self.user)
        assert len(interests["categories"]) == 0
        assert len(interests["tags"]) == 0

    def test_get_user_interests_with_likes(self):
        VideoLike.objects.create(user=self.user, video=self.video1)
        interests = self.service.get_user_interests(self.user)
        assert "Electronics" in interests["categories"]
        assert "tech" in interests["tags"]

    def test_get_user_interests_with_saves(self):
        VideoSave.objects.create(user=self.user, video=self.video2)
        interests = self.service.get_user_interests(self.user)
        assert "Fashion" in interests["categories"]
        assert "style" in interests["tags"]

    def test_generate_feed(self):
        # User likes tech, so video1 should be ranked higher (or at least present)
        VideoLike.objects.create(user=self.user, video=self.video1)

        feed = self.service.generate_feed(self.user)
        assert len(feed) > 0
        # Since video1 matches interests, it should likely be first, but randomness might affect it.
        # However, with only 2 videos and clear preference, video1 should score higher.

        # Let's check scores directly to be sure
        interests = self.service.get_user_interests(self.user)
        score1 = self.service.score_video(self.video1, self.user, interests)
        score2 = self.service.score_video(self.video2, self.user, interests)

        assert score1 > score2


@pytest.mark.django_db
class TestShoppableVideoViewSet:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.force_authenticate(user=self.user)
        self.product = MarketplaceProduct.objects.create(name="Product 1", price=100)
        self.video = ShoppableVideo.objects.create(product=self.product, video_file="videos/test.mp4", title="Test Video")

    def test_list_videos(self):
        url = reverse("shoppablevideo-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_save_video(self):
        url = reverse("shoppablevideo-save-video", args=[self.video.id])

        # Save
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["saved"] is True
        assert VideoSave.objects.filter(user=self.user, video=self.video).exists()

        # Unsave
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["saved"] is False
        assert not VideoSave.objects.filter(user=self.user, video=self.video).exists()

    def test_share_video(self):
        url = reverse("shoppablevideo-share", args=[self.video.id])
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK

        self.video.refresh_from_db()
        assert self.video.shares_count == 1
