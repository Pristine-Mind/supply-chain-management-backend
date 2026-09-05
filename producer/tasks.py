import logging
import math
import statistics
from collections import defaultdict
from datetime import timedelta

from celery import shared_task
from django.db.models import Sum, functions
from django.utils import timezone
from keybert import KeyBERT

from .models import MarketplaceProduct, Product, Sale, StockList

logger = logging.getLogger(__name__)

# Lazy-load KeyBERT model to avoid memory bloat at startup
_kw_model = None


def get_keybert_model():
    """Lazy-load KeyBERT model on first use to avoid memory issues."""
    global _kw_model
    if _kw_model is None:
        logger.info("Loading KeyBERT model...")
        _kw_model = KeyBERT()
    return _kw_model


@shared_task
def move_large_stock_to_stocklist():
    LARGE_STOCK_THRESHOLD = 25

    products = Product.objects.filter(is_active=True)

    for product in products:
        if product.stock > LARGE_STOCK_THRESHOLD:
            if not StockList.objects.filter(product=product).exists():
                StockList.objects.create(product=product, user=product.user)
                product.is_active = False
                product.save()

    return f"{len(products)} products checked."


SERVICE_LEVEL_Z = 1.65  # ~95% service level


@shared_task
def recalc_inventory_parameters():
    """
    Recalculate inventory parameters for all products.
    This task updates average daily demand, safety stock, reorder points, etc.
    """
    try:
        logger.info("Starting inventory parameters recalculation...")

        today = timezone.localdate()
        cutoff_90 = today - timedelta(days=90)
        cutoff_14 = today - timedelta(days=14)

        # Bulk 90-day sales aggregated by product & day
        sales_90 = (
            Sale.objects.filter(sale_date__date__gte=cutoff_90)
            .annotate(day=functions.TruncDate("sale_date"))
            .values("order__product_id", "day")
            .annotate(units_sold=Sum("quantity"))
        )
        sales_map = defaultdict(list)
        for row in sales_90:
            sales_map[row["order__product_id"]].append(row["units_sold"])

        # Bulk 14-day burn aggregated by product
        burn_14 = (
            Sale.objects.filter(sale_date__date__gte=cutoff_14)
            .values("order__product_id")
            .annotate(total_sold=Sum("quantity"))
        )
        burn_map = {row["order__product_id"]: row["total_sold"] for row in burn_14}

        products_updated = 0
        products_with_errors = 0

        for p in Product.objects.all():
            try:
                vals90 = sales_map.get(p.id, [])
                p.avg_daily_demand = statistics.mean(vals90) if vals90 else 0
                p.stddev_daily_demand = statistics.pstdev(vals90) if len(vals90) > 1 else 0

                # Safety stock & reorder point
                sigma_lt = math.sqrt(p.lead_time_days * p.stddev_daily_demand**2)
                p.safety_stock = math.ceil(SERVICE_LEVEL_Z * sigma_lt)
                p.reorder_point = math.ceil(p.avg_daily_demand * p.lead_time_days + p.safety_stock)

                # EOQ
                annual = p.avg_daily_demand * 365
                p.reorder_quantity = math.ceil(math.sqrt((2 * annual * 50) / 2))

                # Projected stock-out (persist to a DateField if you add one)
                burn = (burn_map.get(p.id, 0) or 0) / 14
                if burn > 0:
                    p.projected_stockout_date_field = today + timedelta(days=p.stock / burn)
                else:
                    p.projected_stockout_date_field = None

                p.save(
                    update_fields=[
                        "avg_daily_demand",
                        "stddev_daily_demand",
                        "safety_stock",
                        "reorder_point",
                        "reorder_quantity",
                        "projected_stockout_date_field",
                    ]
                )
                products_updated += 1

            except Exception as e:
                logger.error(f"Error updating product {p.id}: {e}")
                products_with_errors += 1
                continue

        logger.info(
            f"Inventory parameters recalculation completed. Updated: {products_updated}, Errors: {products_with_errors}"
        )
        return f"Updated {products_updated} products successfully, {products_with_errors} errors"

    except Exception as e:
        logger.error(f"Critical error in recalc_inventory_parameters: {e}")
        raise


@shared_task(bind=True, rate_limit="10/m")
def generate_and_save_product_tags(self, product_id):
    """
    Extracts semantic search tags using KeyBERT and saves them back to the product.
    Runs asynchronously to prevent blocking the web server.
    Overwrites any existing tags with the new optimized format.
    """
    try:
        product = MarketplaceProduct.objects.select_related("product", "product__brand", "product__category").get(
            id=product_id
        )
        base_product = product.product

        name = base_product.name if base_product and base_product.name else ""
        desc = base_product.description if base_product and base_product.description else ""
        text_to_analyze = f"{name} {desc}".strip()

        if not text_to_analyze:
            logger.warning(f"No text to analyze for product {product_id}")
            return []

        static_tags = []
        if base_product and getattr(base_product, "brand", None):
            b_name = getattr(base_product.brand, "name", None) or str(base_product.brand)
            b_clean = b_name.strip().lower() if b_name else ""
            if b_clean and not b_clean.startswith("dummy_") and b_clean != "unbranded":
                static_tags.append(b_clean)

        if not static_tags:
            try:
                from .models import Brand

                for b_name in Brand.objects.values_list("name", flat=True):
                    b_clean = b_name.strip().lower() if b_name else ""
                    if b_clean and len(b_clean) > 1 and b_clean != "unbranded" and b_clean in text_to_analyze.lower():
                        static_tags.append(b_clean)
                        break
            except Exception:
                pass

        if not static_tags and name:
            first_word = name.split()[0].strip().lower()
            if first_word.isalpha() and len(first_word) >= 2 and first_word != "unbranded":
                static_tags.append(first_word)
        if base_product and getattr(base_product, "category", None):
            c_name = getattr(base_product.category, "name", None)
            if c_name:
                static_tags.append(str(c_name).strip().lower())
        kw_model = get_keybert_model()
        keywords = kw_model.extract_keywords(text_to_analyze, keyphrase_ngram_range=(1, 2), stop_words="english", top_n=5)

        nlp_tags = [kw[0] for kw in keywords]
        combined_tags = []
        for tag in static_tags + nlp_tags:
            clean_tag = tag.strip().lower()
            if clean_tag and clean_tag not in combined_tags:
                combined_tags.append(clean_tag)
        product.search_tags = combined_tags
        product.save(update_fields=["search_tags"])

        logger.info(f"AI tagged product {product_id} with: {combined_tags}")
        return combined_tags

    except MarketplaceProduct.DoesNotExist:
        logger.error(f"MarketplaceProduct {product_id} not found.")
        return None
    except Exception as e:
        logger.error(f"AI Extraction failed for product {product_id}: {str(e)}")
        return None
