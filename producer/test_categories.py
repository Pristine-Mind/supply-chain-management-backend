# Test the category API endpoints

import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from producer.models import Category, Subcategory, SubSubcategory


class CategoryAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create test data
        self.category = Category.objects.create(
            code='TEST',
            name='Test Category'
        )
        self.subcategory = Subcategory.objects.create(
            code='TEST_SUB',
            name='Test Subcategory',
            category=self.category
        )
        self.sub_subcategory = SubSubcategory.objects.create(
            code='TEST_SUB_SUB',
            name='Test Sub-Subcategory',
            subcategory=self.subcategory
        )

    def test_categories_list(self):
        """Test listing categories"""
        response = self.client.get('/api/categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)

    def test_category_hierarchy(self):
        """Test category hierarchy endpoint"""
        response = self.client.get('/api/categories/hierarchy/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_subcategories_filtered(self):
        """Test filtering subcategories by category"""
        response = self.client.get(f'/api/subcategories/?category={self.category.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)

    def test_category_model_methods(self):
        """Test category model methods"""
        # Test string representation
        self.assertEqual(str(self.category), 'TEST - Test Category')
        self.assertEqual(str(self.subcategory), 'TEST_SUB - Test Subcategory')
        self.assertEqual(str(self.sub_subcategory), 'TEST_SUB_SUB - Test Sub-Subcategory')

    def test_product_category_hierarchy(self):
        """Test product category hierarchy method"""
        from producer.models import Product, Producer
        
        # Create a producer and product for testing
        producer = Producer.objects.create(
            name='Test Producer',
            contact='123456789',
            address='Test Address',
            registration_number='TEST123',
            user=self.user
        )
        
        product = Product.objects.create(
            name='Test Product',
            producer=producer,
            category=self.category,
            subcategory=self.subcategory,
            sub_subcategory=self.sub_subcategory,
            price=100.0,
            cost_price=80.0,
            stock=10,
            user=self.user
        )
        
        hierarchy = product.get_category_hierarchy()
        expected = f"{self.category.name} > {self.subcategory.name} > {self.sub_subcategory.name}"
        self.assertEqual(hierarchy, expected)