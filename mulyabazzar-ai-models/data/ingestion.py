import json
import os
import random
import time
from typing import List, Optional

import requests
from pydantic import BaseModel

# 1.Data classes


class CategoryInfo(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = ""
    is_active: bool
    created_at: str
    updated_at: str
    subcategories_count: int


class UserDetails(BaseModel):
    id: int
    username: str
    email: str
    role: str
    business_type: str
    has_access_to_marketplace: bool
    b2b_verified: bool


class ProducerInfo(BaseModel):
    id: int
    name: str
    contact: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    registration_number: Optional[str] = ""
    service_radius_km: Optional[int] = 0
    location: Optional[str] = ""
    user: int
    user_details: UserDetails


class BrandInfo(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""
    country_of_origin: Optional[str] = ""
    is_active: bool
    is_verified: bool
    products_count: int


class ProductInfo(BaseModel):
    id: int
    name: str
    category_details: str
    description: Optional[str] = ""
    price: float
    stock: int
    producer: Optional[int] = None
    brand_name: Optional[str] = "Unbranded"


class DirectSaleInfo(BaseModel):
    id: int
    product: int
    quantity: int
    unit_price: float
    sale_date: str


class ERPOrderInfo(BaseModel):
    id: int
    quantity: int
    total_price: float
    payment_status: str
    delivery_date: str


class EcommerceSaleInfo(BaseModel):
    id: int
    buyer: int
    seller: int
    product: int
    quantity: int
    payment_status: str
    shipping_cost: float


class B2BInteractionInfo(BaseModel):
    id: int
    initiator: int
    target_business: int
    interaction_type: str
    weight: float


# 2. Chunking logic


def fetch_data_in_chunks(
    endpoint_url: str, headers: dict = None, chunk_size: int = 50, sleep_time: float = 1.0, is_mock: bool = True
):
    all_results = []
    offset = 0
    print(f"Starting bulk ingestion for: {endpoint_url}")
    business_types = ["distributor", "wholesaler", "retailer", "general user"]
    interaction_types = {"view": 1.0, "contact": 2.0, "connect": 3.0, "order": 5.0}
    while True:
        url = f"{endpoint_url}?limit={chunk_size}&offset={offset}"
        if is_mock:
            results = []
            for i in range(offset, min(offset + chunk_size, offset + 5)):
                if "categories" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "code": f"C{i}",
                            "name": f"Mock Category {i}",
                            "description": "",
                            "is_active": True,
                            "created_at": "2025-11-06T00:00:00Z",
                            "updated_at": "2025-11-06T00:00:00Z",
                            "subcategories_count": 3,
                        }
                    )
                elif "producers" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "name": f"Mock Producer {i}",
                            "contact": "9800000000",
                            "email": f"producer{i}@test.com",
                            "address": "Kathmandu",
                            "registration_number": "123",
                            "service_radius_km": 50,
                            "location": "POINT (0 0)",
                            "user": 100 + i,
                            "user_details": {
                                "username": f"user_{i}",
                                "id": 100 + i,
                                "has_access_to_marketplace": True,
                                "business_type": random.choice(business_types),
                                "role": "business_owner",
                                "email": f"khatririshi{i}@gmail.com",
                                "b2b_verified": random.choice([True, False]),
                            },
                        }
                    )
                elif "brands" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "name": f"Mock Brand {i}",
                            "description": "",
                            "country_of_origin": "",
                            "is_active": True,
                            "is_verified": False,
                            "products_count": 10,
                        }
                    )
                elif "products" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "name": f"Mock Product {i}",
                            "category_details": "Home",
                            "description": "<p>Test product</p>",
                            "price": 100.0,
                            "stock": 20,
                            "producer": 1,
                            "brand_name": "Mock Brand",
                        }
                    )
                elif "direct-sales" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "product": random.randint(1, 10),
                            "quantity": random.randint(1, 5),
                            "unit_price": 150.0,
                            "sale_date": "2026-08-03T10:00:00Z",
                        }
                    )
                elif "erp-orders" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "quantity": random.randint(10, 50),
                            "total_price": 5000.0,
                            "payment_status": random.choice(["cash", "online"]),
                            "delivery_date": "2026-08-05T10:00:00Z",
                        }
                    )
                elif "ecommerce-sales" in endpoint_url:
                    results.append(
                        {
                            "id": i,
                            "buyer": 100 + random.randint(1, 5),
                            "seller": 100 + random.randint(6, 10),
                            "product": random.randint(1, 10),
                            "quantity": random.randint(1, 3),
                            "payment_status": "online",
                            "shipping_cost": 50.0,
                        }
                    )
                elif "b2b-interactions" in endpoint_url:
                    int_type = random.choice(list(interaction_types.keys()))
                    results.append(
                        {
                            "id": i,
                            "initiator": 100 + random.randint(1, 5),
                            "target_business": 100 + random.randint(6, 10),
                            "interaction_type": int_type,
                            "weight": interaction_types[int_type],
                        }
                    )

            data = {"count": 5, "next": None, "results": results}
        else:
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"API Error: {e}")
                break

        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)
        if not data.get("next"):
            break
        offset += chunk_size
        time.sleep(sleep_time)

    return all_results


# 3. Caching logic


def get_cached_data(endpoint_url: str, cache_filename: str, headers: dict = None, is_mock: bool = True):
    os.makedirs("data", exist_ok=True)
    cache_path = f"data/{cache_filename}"
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
        except OSError:
            pass

    data = fetch_data_in_chunks(endpoint_url, headers=headers, is_mock=is_mock)
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=4)
    return data


if __name__ == "__main__":
    print("Testing Universal Caching Data")
    direct_sales = get_cached_data(
        "https://appmulyabazzar.com/api/v1/direct-sales/", "direct_sales_cache.json", is_mock=True
    )
    erp_orders = get_cached_data("https://appmulyabazzar.com/api/v1/erp-orders/", "erp_orders_cache.json", is_mock=True)
    eco_sales = get_cached_data(
        "https://appmulyabazzar.com/api/v1/ecommerce-sales/", "ecommerce_sales_cache.json", is_mock=True
    )
    b2b = get_cached_data("https://appmulyabazzar.com/api/v1/b2b-interactions/", "b2b_interactions_cache.json", is_mock=True)
    print("\nEdges cached successfully!")
