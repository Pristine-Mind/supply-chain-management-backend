from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from market.factories import MarketplaceProductFactory, UserFactory
from market.models import AffiliateClick, ProductTag, ShoppableVideo
from producer.models import MarketplaceProduct


class CreatorFollowAndAffiliateTests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.creator = UserFactory()
        self.client.force_authenticate(user=self.user)

        # Create a marketplace product
        self.mp = MarketplaceProductFactory()

        # Create a shoppable video to attach a product tag to
        self.video = ShoppableVideo.objects.create(
            uploader=self.creator, video_file="videos/sample.mp4", title="t", product=self.mp
        )

        # Create a product tag with merchant_url
        self.tag = ProductTag.objects.create(
            content_object=self.video, product=self.mp, x=0.1, y=0.1, merchant_url="https://example.com/product/1"
        )

    def test_follow_creator_endpoint(self):
        url = reverse("creator-follow", args=[self.creator.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("follower_count", resp.data)

        # Unfollow
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_affiliate_redirect_by_post_and_product(self):
        url = reverse("affiliate-redirect") + f"?post_id={self.video.id}&product_id={self.mp.id}"
        resp = self.client.get(url, follow=False)
        # Should redirect (302)
        self.assertIn(resp.status_code, (301, 302))
        # Log exists
        clicks = AffiliateClick.objects.filter(product=self.mp)
        self.assertTrue(clicks.exists())
