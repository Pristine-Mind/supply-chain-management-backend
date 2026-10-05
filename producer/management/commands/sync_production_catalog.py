import urllib.request
import json
import re
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from producer.models import MarketplaceProduct, Product, Category, Brand, Producer

class Command(BaseCommand):
    help = "Syncs full catalog inventory from appmulyabazzar production API"

    def handle(self, *args, **options):
        User = get_user_model()
        default_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not default_user:
            default_user = User.objects.create(username="sync_bot", email="sync@mulyabazzar.com")

        default_producer = Producer.objects.first()
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = "https://appmulyabazzar.com/api/v1/marketplace/?limit=200"

        total_synced = 0
        page = 1

        self.stdout.write(self.style.NOTICE("Starting catalog sync from production API..."))

        while url:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
            except Exception as e:
                self.stderr.write(f"Network error on page {page}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            batch_synced = 0
            for item in results:
                try:
                    p_details = item.get("product_details", {}) or {}
                    name = (p_details.get("name") or item.get("name") or "Unnamed Product").strip()
                    raw_desc = p_details.get("description") or ""
                    clean_desc = re.sub(r'<[^>]+>', ' ', raw_desc).strip()
                    if not clean_desc:
                        clean_desc = f"{name} - Quality marketplace verified product."

                    cat_info = p_details.get("category_info", {}) or {}
                    cat_name = (cat_info.get("name") or "General").strip()
                    raw_cat_code = str(cat_info.get("code") or "GEN").strip()[:5].upper() or "GEN"

                    category, _ = Category.objects.get_or_create(
                        code=raw_cat_code,
                        defaults={"name": cat_name}
                    )

                    brand_name = item.get("brand_name") or p_details.get("brand_name")
                    brand = None
                    if brand_name and str(brand_name).strip():
                        brand, _ = Brand.objects.get_or_create(name=str(brand_name).strip())

                    listed_p = float(item.get("listed_price") or 0.0)
                    price_val = listed_p if listed_p > 0 else 100.0
                    cost_p = round(price_val * 0.8, 2)

                    disc_val = item.get("discounted_price")
                    disc_price = Decimal(str(disc_val)) if disc_val not in [None, ""] else None
                    disc_perc = float(item.get("discount_percentage") or 0.0)

                    tags = [name.lower()]
                    if brand_name:
                        tags.append(str(brand_name).lower().strip())
                    if cat_name:
                        tags.append(cat_name.lower().strip())

                    prod_defaults = {
                        "description": clean_desc,
                        "old_category": "OT",
                        "price": price_val,
                        "cost_price": cost_p,
                        "stock": 100,
                        "reorder_level": 10,
                        "is_active": True,
                        "is_marketplace_created": True,
                        "user": default_user,
                        "avg_daily_demand": 1.0,
                        "stddev_daily_demand": 0.5,
                        "safety_stock": 10,
                        "reorder_point": 15,
                        "reorder_quantity": 50,
                        "lead_time_days": 3,
                    }
                    if hasattr(Product, 'brand') and brand:
                        prod_defaults["brand"] = brand
                    if hasattr(Product, 'producer') and default_producer:
                        prod_defaults["producer"] = default_producer

                    product, _ = Product.objects.update_or_create(
                        name=name,
                        category=category,
                        defaults=prod_defaults
                    )

                    mp_defaults = {
                        "product": product,
                        "listed_price": Decimal(str(price_val)),
                        "discounted_price": disc_price,
                        "discount_percentage": disc_perc,
                        "is_available": item.get("is_available", True),
                        "shipping_cost": Decimal(str(item.get("shipping_cost") or 0.0)),
                        "is_delivery_free": item.get("is_delivery_free", False),
                        "recent_purchases_count": int(item.get("recent_purchases_count") or 0),
                        "view_count": int(item.get("view_count") or 0),
                        "rank_score": float(item.get("rank_score") or 0.0),
                        "is_featured": item.get("is_featured", False),
                        "is_made_in_nepal": item.get("is_made_in_nepal", False),
                        "made_for_you": item.get("made_for_you", False),
                        "enable_b2b_sales": item.get("enable_b2b_sales", False),
                        "enable_geo_restrictions": item.get("enable_geo_restrictions", False),
                        "search_tags": tags
                    }
                    if hasattr(MarketplaceProduct, 'producer') and default_producer:
                        mp_defaults["producer"] = default_producer

                    MarketplaceProduct.objects.update_or_create(
                        id=item.get("id"),
                        defaults=mp_defaults
                    )
                    batch_synced += 1
                except Exception:
                    continue

            total_synced += batch_synced
            self.stdout.write(f"Page {page:<2} synced: {batch_synced:<3} items | Total in DB: {total_synced}")
            url = data.get("next")
            page += 1

        self.stdout.write(self.style.SUCCESS(f"Finished. Total {total_synced} products synced."))