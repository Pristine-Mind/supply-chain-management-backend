#!/usr/bin/env python
"""
Simple test script to verify the trending products API works
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/Users/rishikhatri/pristine-minds/supply-chain-management-backend')

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()

from market.trending_views import TrendingProductsManager
from producer.models import MarketplaceProduct

def test_trending_calculation():
    """Test the trending score calculation"""
    try:
        print("Testing trending products calculation...")
        
        # Get a small subset of products
        queryset = MarketplaceProduct.objects.filter(is_available=True)[:5]
        print(f"Found {queryset.count()} available marketplace products")
        
        # Apply trending calculations
        trending_queryset = TrendingProductsManager.calculate_trending_score(queryset)
        
        print("Trending calculation successful!")
        
        # Check results
        for product in trending_queryset:
            print(f"Product: {product.product.name}")
            print(f"  - Trending Score: {getattr(product, 'trending_score', 'N/A')}")
            print(f"  - Total Sales: {getattr(product, 'total_sales', 'N/A')}")
            print(f"  - Weekly Sales: {getattr(product, 'weekly_sales_count', 'N/A')}")
            print(f"  - View Count: {product.view_count}")
            print("---")
            
    except Exception as e:
        print(f"Error in trending calculation: {e}")
        import traceback
        traceback.print_exc()

def test_trending_categories():
    """Test the trending categories calculation"""
    try:
        print("Testing trending categories...")
        categories = TrendingProductsManager.get_trending_categories()
        print(f"Found {len(categories)} trending categories")
        
        for category in categories[:3]:  # Show first 3
            print(f"Category: {category.get('category_name', 'Unknown')}")
            print(f"  - Product Count: {category.get('product_count', 0)}")
            print(f"  - Total Sales: {category.get('total_sales', 0)}")
            print(f"  - Weekly Sales: {category.get('weekly_sales', 0)}")
            print("---")
            
    except Exception as e:
        print(f"Error in categories calculation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_trending_calculation()
    print("\n" + "="*50 + "\n")
    test_trending_categories()