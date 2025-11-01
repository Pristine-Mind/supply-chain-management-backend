#!/usr/bin/env python
"""
Simple test script to verify trending products API works
"""
import os
import sys
import django

# Setup Django
sys.path.append('/Users/rishikhatri/pristine-minds/supply-chain-management-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()

from market.trending_views import TrendingProductsManager
from producer.models import MarketplaceProduct

def test_trending_calculation():
    """Test the basic trending calculation"""
    print("🧪 Testing trending products calculation...")
    
    try:
        # Get a small sample of products
        queryset = MarketplaceProduct.objects.filter(is_available=True)[:3]
        print(f"📊 Testing with {queryset.count()} products")
        
        # Apply trending calculation
        result = TrendingProductsManager.calculate_trending_score(queryset)
        
        print("✅ Trending calculation successful!")
        
        # Print results
        for product in result:
            trending_score = getattr(product, 'trending_score', 'N/A')
            sales_velocity = getattr(product, 'sales_velocity', 'N/A')
            price_trend = getattr(product, 'price_trend', 'N/A')
            
            print(f"📦 {product.product.name}")
            print(f"   📈 Trending Score: {trending_score}")
            print(f"   🚀 Sales Velocity: {sales_velocity}")
            print(f"   💰 Price Trend: {price_trend}")
            print()
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_trending_categories():
    """Test the trending categories calculation"""
    print("🏷️  Testing trending categories...")
    
    try:
        categories = TrendingProductsManager.get_trending_categories()
        print(f"✅ Found {len(categories)} trending categories")
        
        for cat in categories[:3]:  # Show first 3
            print(f"📂 {cat.get('category_name', 'Unknown')}: {cat.get('trending_score', 0)} score")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting Trending Products API Tests")
    print("=" * 50)
    
    success1 = test_trending_calculation()
    print()
    success2 = test_trending_categories()
    
    print()
    print("=" * 50)
    if success1 and success2:
        print("🎉 All tests passed! Trending products API is working.")
    else:
        print("❌ Some tests failed. Check the errors above.")