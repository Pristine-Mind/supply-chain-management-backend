import json
import urllib.request
import re
from producer.tag_extractor import TagExtractor

class MockCategory:
    def __init__(self, category_code):
        self.code = category_code 
        self.category_name = "General"

class MockProduct:
    def __init__(self, prod_data):
        details = prod_data.get("product_details", {})
        
        self.name = details.get("name", "")
        raw_desc = details.get("description", "")
        self.description = re.sub(r'<[^>]+>', ' ', raw_desc)
        cat_info = details.get("category_info", {})
        cat_code = cat_info.get("code", "EG")
        
        self.category = MockCategory(cat_code)

class MockMarketplaceProduct:
    def __init__(self, api_data):
        self.product = MockProduct(api_data)
        details = api_data.get("product_details", {})
        self.additional_information = api_data.get("additional_information", "")
        self.color = api_data.get("color", "")
 
        self.is_made_in_nepal = api_data.get("is_made_in_nepal", False)
        self.is_delivery_free = api_data.get("is_delivery_free", False)
        self.enable_b2b_sales = api_data.get("enable_b2b_sales", False)
        self.is_featured = api_data.get("is_featured", False)
        self.made_for_you = api_data.get("made_for_you", False)
        self.is_available = api_data.get("is_available", True)
        self.discounted_price = float(api_data.get("discounted_price") or 0)
        self.listed_price = float(api_data.get("listed_price") or 0)
        self.discount_percentage = float(api_data.get("discount_percentage") or 0)
        self.recent_purchases_count = int(api_data.get("recent_purchases_count", 0))
        self.view_count = int(api_data.get("view_count", 0))

def run():
    print("Fetching data from Marketplace API...")
    api_url = "https://appmulyabazzar.com/api/v1/marketplace/?limit=100" 
    
    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    products = data.get("results", []) if isinstance(data, dict) else data
    
    extracted_data = []
    
    for prod in products:
        prod_id = prod.get("id")
        mock_db_row = MockMarketplaceProduct(prod)
        generated_tags = TagExtractor.extract_tags(mock_db_row)
        api_brand = prod.get("brand_name") or prod.get("product_details", {}).get("brand_name", "")
        if api_brand:
            pure_brands = [api_brand.lower()]
        else:
            combined_text = f"{mock_db_row.product.name} {mock_db_row.product.description}".lower()
            extracted_brands = list(TagExtractor._extract_brands(combined_text))
            pure_brands = [b for b in extracted_brands if b not in TagExtractor.BRANDS.keys()]
        extracted_data.append({
            "id": prod_id,
            "brands": pure_brands,
            "keywords": generated_tags
        })
        print(f" Processed ID {prod_id} | Brands: {pure_brands} | Tags: {generated_tags[:3]}")

    with open("manager_extracted_data.json", "w", encoding="utf-8") as f:
        json.dump(extracted_data, f, indent=4, ensure_ascii=False)
        
    print("\n Done! File saved as 'manager_extracted_data.json'")

if __name__ == "__main__":
    run()