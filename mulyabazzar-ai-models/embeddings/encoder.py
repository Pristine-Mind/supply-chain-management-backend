import html
import re
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

encoder_model = SentenceTransformer("all-MiniLM-L6-v2")


def clean_tinymce_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = html.unescape(raw_html)
    clean_text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean_text).strip()


def create_product_feature_string(product_data: dict) -> str:
    name = product_data.get("name", "")
    category = product_data.get("category_details", "")
    brand = product_data.get("brand_name", "Unbranded")
    description = clean_tinymce_html(product_data.get("description", ""))
    return f"Product: {name}. Brand: {brand}. Category: {category}. Details: {description}."


def create_producer_feature_string(producer_data: dict) -> str:
    name = producer_data.get("name", "")
    address = producer_data.get("address", "")
    user_details = producer_data.get("user_details", {})
    business_type = user_details.get("business_type", "general user")
    role = user_details.get("role", "Unknown")
    is_verified = user_details.get("b2b_verified", False)

    verification_status = "Verified B2B Vendor" if is_verified else "Unverified Vendor"
    return f"Producer: {name}. Location: {address}. Role: {role}. Business Type: {business_type}. Status: {verification_status}."


def create_brand_feature_string(brand_data: dict) -> str:
    name = brand_data.get("name", "")
    description = clean_tinymce_html(brand_data.get("description", ""))
    origin = brand_data.get("country_of_origin", "")

    feature = f"Brand: {name}."
    if origin:
        feature += f" Origin: {origin}."
    if description:
        feature += f" Details: {description}."
    return feature


def generate_embeddings(text_list: List[str]) -> np.ndarray:
    print(f"\nGenerating embeddings for {len(text_list)} items...")
    return encoder_model.encode(text_list, convert_to_numpy=True)


if __name__ == "__main__":
    print("Testing Full Feature Extraction...")

    sample_prod = {
        "name": "HOME PUJA SAMAGRI",
        "category_details": "Garden & Outdoor",
        "brand_name": "Unbranded",
        "description": "<p>Complete essential kit for daily worship.</p>",
    }
    sample_prod_feature = create_product_feature_string(sample_prod)
    print(f"Product Feature: {sample_prod_feature}")

    sample_brand = {"name": "Ajazz", "country_of_origin": "China", "description": "Keyboard manufacturer."}
    sample_brand_feature = create_brand_feature_string(sample_brand)
    print(f"Brand Feature: {sample_brand_feature}")
    sample_producer = {
        "name": "Mulya Admin",
        "address": "Kathmandu",
        "user_details": {
            "username": "root",
            "id": 1,
            "has_access_to_marketplace": True,
            "business_type": "distributor",
            "role": "business_owner",
            "email": "khatririshi2430@gmail.com",
            "b2b_verified": True,
        },
    }
    sample_producer_feature = create_producer_feature_string(sample_producer)
    print(f"Producer Feature: {sample_producer_feature}")

    vectors = generate_embeddings([sample_prod_feature, sample_brand_feature, sample_producer_feature])
    print(f"Generated Vectors Shape: {vectors.shape} (Should be 3, 384)")
