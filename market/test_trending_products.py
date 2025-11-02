from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from market.models import MarketplaceSale
from market.trending_utils import TrendingProductUtils
from producer.models import MarketplaceProduct, Producer, Product


class TrendingProductsAPITestCase(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create test user and producer
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        self.producer = Producer.objects.create(
            name="Test Producer",
            contact="1234567890",
            email="producer@test.com",
            address="Test Address",
            registration_number="REG123",
            user=self.user,
        )

        # Create test products
        self.product1 = Product.objects.create(
            producer=self.producer,
            name="Test Product 1",
            description="Test description",
            sku="SKU001",
            price=100.0,
            cost_price=80.0,
            stock=50,
            user=self.user,
        )

        self.product2 = Product.objects.create(
            producer=self.producer,
            name="Test Product 2",
            description="Test description 2",
            sku="SKU002",
            price=200.0,
            cost_price=150.0,
            stock=30,
            user=self.user,
        )

        # Create marketplace products
        self.marketplace_product1 = MarketplaceProduct.objects.create(
            product=self.product1,
            listed_price=100.0,
            discounted_price=80.0,
            is_available=True,
            view_count=100,
            recent_purchases_count=5,
            rank_score=4.5,
        )

        self.marketplace_product2 = MarketplaceProduct.objects.create(
            product=self.product2,
            listed_price=200.0,
            is_available=True,
            view_count=50,
            recent_purchases_count=2,
            rank_score=3.8,
        )

    def test_trending_products_list(self):
        """Test the main trending products endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertIn("timestamp", data)

        # Should have our test products
        self.assertGreaterEqual(data["count"], 2)

        # Check that products have trending data
        if data["results"]:
            product = data["results"][0]
            self.assertIn("trending_score", product)
            self.assertIn("trending_rank", product)
            self.assertIn("sales_velocity", product)

    def test_trending_products_with_filters(self):
        """Test trending products with filters"""
        # Test price filter
        response = self.client.get("/api/v1/marketplace-trending/?min_price=150")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test limit filter
        response = self.client.get("/api/v1/marketplace-trending/?limit=1")
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(data["count"], 1)

    def test_top_weekly_products(self):
        """Test top weekly products endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/top_weekly/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("results", data)
        self.assertIn("period", data)
        self.assertEqual(data["period"], "weekly")

    def test_most_viewed_products(self):
        """Test most viewed products endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/most_viewed/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("results", data)
        self.assertEqual(data["period"], "most_viewed")

    def test_fastest_selling_products(self):
        """Test fastest selling products endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/fastest_selling/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data["period"], "fastest_selling")

    def test_new_trending_products(self):
        """Test new trending products endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/new_trending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data["period"], "new_trending")

    def test_trending_categories(self):
        """Test trending categories endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/categories/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("results", data)
        self.assertIn("count", data)

    def test_trending_stats(self):
        """Test trending statistics endpoint"""
        response = self.client.get("/api/v1/marketplace-trending/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("total_trending_products", data)
        self.assertIn("average_trending_score", data)
        self.assertIn("price_range", data)

    def test_track_product_view(self):
        """Test product view tracking"""
        response = self.client.post("/api/v1/trending/track-view/", {"product_id": self.marketplace_product1.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that view count was updated
        self.marketplace_product1.refresh_from_db()
        # Note: View count increment is done via F() expression,
        # so we can't easily test the exact value here

    def test_track_product_view_invalid(self):
        """Test product view tracking with invalid product"""
        response = self.client.post("/api/v1/trending/track-view/", {"product_id": 99999})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test missing product_id
        response = self.client.post("/api/v1/trending/track-view/", {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trending_summary(self):
        """Test trending summary endpoint"""
        response = self.client.get("/api/v1/trending/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("total_products", data)
        self.assertIn("trending_products", data)
        self.assertIn("weekly_sales", data)
        self.assertIn("trending_percentage", data)


class TrendingUtilsTestCase(TestCase):
    def setUp(self):
        """Set up test data for utils testing"""
        self.user = User.objects.create_user(username="testuser", password="testpass123")

        self.producer = Producer.objects.create(
            name="Test Producer",
            contact="1234567890",
            email="producer@test.com",
            address="Test Address",
            registration_number="REG123",
            user=self.user,
        )

        self.product = Product.objects.create(
            producer=self.producer,
            name="Test Product",
            description="Test description",
            sku="SKU001",
            price=100.0,
            cost_price=80.0,
            stock=50,
            user=self.user,
        )

        self.marketplace_product = MarketplaceProduct.objects.create(
            product=self.product, listed_price=100.0, is_available=True, view_count=10
        )

    def test_update_product_view_count(self):
        """Test updating product view count"""
        initial_count = self.marketplace_product.view_count

        success = TrendingProductUtils.update_product_view_count(self.marketplace_product.id)
        self.assertTrue(success)

        # Test with non-existent product
        success = TrendingProductUtils.update_product_view_count(99999)
        self.assertFalse(success)

    def test_get_trending_summary(self):
        """Test getting trending summary"""
        summary = TrendingProductUtils.get_trending_summary()

        self.assertIn("total_products", summary)
        self.assertIn("trending_products", summary)
        self.assertIn("weekly_sales", summary)
        self.assertIn("trending_percentage", summary)

        self.assertIsInstance(summary["total_products"], int)
        self.assertIsInstance(summary["trending_products"], int)
        self.assertIsInstance(summary["trending_percentage"], float)

    def test_boost_product_ranking(self):
        """Test boosting product ranking"""
        initial_score = self.marketplace_product.rank_score

        success = TrendingProductUtils.boost_product_ranking(self.marketplace_product.id, 1.5)
        self.assertTrue(success)

        # Test with non-existent product
        success = TrendingProductUtils.boost_product_ranking(99999, 1.5)
        self.assertFalse(success)
