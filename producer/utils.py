import gc
import logging
import re
from datetime import date, datetime

from django.core.cache import cache
from django.db.models import DecimalField, Q
from django.db.models.functions import Coalesce
from django.utils.timezone import is_naive, localtime, make_aware
from keybert import KeyBERT
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from producer.models import Brand, Category, MarketplaceProduct, SearchTaxonomyNode, Subcategory

logger = logging.getLogger(__name__)

_kw_model = None


def get_keybert_model():
    """Lazy-load KeyBERT model for offline tag extraction."""
    global _kw_model
    if _kw_model is None:
        logger.info("Loading KeyBERT model...")
        _kw_model = KeyBERT()
    return _kw_model


def unload_keybert_model():
    """Unload KeyBERT to free worker memory."""
    global _kw_model
    if _kw_model is not None:
        logger.info("Unloading KeyBERT model...")
        try:
            import torch

            if hasattr(_kw_model, "model") and hasattr(_kw_model.model, "cpu"):
                _kw_model.model.cpu()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        _kw_model = None
        gc.collect()


def export_queryset_to_excel(queryset, field_names, headers=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data Export"

    if headers:
        ws.append(headers)
    else:
        ws.append([field.replace("_", " ").title() for field in field_names])

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for obj in queryset:
        row = []
        for field in field_names:
            value = getattr(obj, field)
            if callable(value):
                value = value()
            elif hasattr(value, "all"):
                value = ", ".join([str(item) for item in value.all()])
            elif isinstance(value, datetime):
                if is_naive(value):
                    value = make_aware(value)
                value = localtime(value).strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, date):
                value = value.strftime("%Y-%m-%d")
            else:
                value = str(value) if value is not None else ""
            row.append(value)
        ws.append(row)

    for col_num, column_cells in enumerate(ws.columns, 1):
        length = max(len(str(cell.value) or "") for cell in column_cells)
        ws.column_dimensions[get_column_letter(col_num)].width = length + 5

    return wb


def generate_and_save_product_tags(product_id):
    """
    Extracts semantic search tags using KeyBERT and saves them to MarketplaceProduct.
    Executed asynchronously in Celery or background tasks.
    """
    try:
        product = MarketplaceProduct.objects.select_related(
            "product", "product__brand", "product__category"
        ).get(id=product_id)
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
                for b_name in Brand.objects.values_list("name", flat=True):
                    b_clean = b_name.strip().lower() if b_name else ""
                    if (
                        b_clean
                        and len(b_clean) > 1
                        and b_clean != "unbranded"
                        and b_clean in text_to_analyze.lower()
                    ):
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
        keywords = kw_model.extract_keywords(
            text_to_analyze,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            top_n=5,
        )

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


class DynamicSynonymService:
    """
    In-memory and Redis-cached taxonomy resolver.
    Prioritizes internal catalog entities (Category, Subcategory, Brand)
    before falling back to the external SearchTaxonomyNode table.
    """
    CACHE_KEY = "marketplace_search_taxonomy_map_v2"
    CACHE_TIMEOUT = 3600  # 1 hour

    @classmethod
    def get_taxonomy_bundle(cls):
        bundle = cache.get(cls.CACHE_KEY)
        if bundle is None:
            taxonomy = {}
            alias_to_key = {}
            for node in SearchTaxonomyNode.objects.filter(is_active=True):
                k = node.key.lower().strip()
                taxonomy[k] = {
                    "canonical": node.canonical,
                    "category": node.category,
                    "aliases": [a.lower().strip() for a in (node.aliases or [])],
                    "trending_suggestions": node.trending_suggestions or [],
                }
                alias_to_key[k] = k
                for alias in taxonomy[k]["aliases"]:
                    if alias:
                        alias_to_key[alias] = k

            sorted_aliases = sorted(alias_to_key.keys(), key=len, reverse=True)
            bundle = {
                "taxonomy": taxonomy,
                "alias_to_key": alias_to_key,
                "sorted_aliases": sorted_aliases,
            }
            cache.set(cls.CACHE_KEY, bundle, timeout=cls.CACHE_TIMEOUT)
        return bundle

    @classmethod
    def invalidate_cache(cls):
        cache.delete(cls.CACHE_KEY)

    @classmethod
    def resolve_query(cls, raw_query: str):
        cleaned = raw_query.lower().strip()
        noise_tokens = {"banaune", "garne", "chahiyo", "khojeko", "ramro", "halka", "wala", "ko", "ma"}
        filtered_words = [w for w in cleaned.split() if w not in noise_tokens]
        normalized_str = " ".join(filtered_words)
        internal_cat = Category.objects.filter(name__iexact=normalized_str, is_active=True).first()
        if internal_cat:
            return {
                "source": "internal_catalog",
                "matched_alias": normalized_str,
                "canonical_term": internal_cat.name,
                "category": internal_cat.name,
                "trending_suggestions": [],
            }
        internal_subcat = (
            Subcategory.objects.filter(name__iexact=normalized_str, is_active=True)
            .select_related("category")
            .first()
        )
        if internal_subcat:
            return {
                "source": "internal_catalog",
                "matched_alias": normalized_str,
                "canonical_term": internal_subcat.name,
                "category": internal_subcat.category.name if internal_subcat.category else internal_subcat.name,
                "trending_suggestions": [],
            }
        internal_brand = (
            Brand.objects.filter(name__iexact=normalized_str, is_active=True)
            .select_related("category")
            .first()
        )
        if internal_brand:
            return {
                "source": "internal_catalog",
                "matched_alias": normalized_str,
                "canonical_term": internal_brand.name,
                "category": internal_brand.category.name if internal_brand.category else "",
                "trending_suggestions": [],
            }
        bundle = cls.get_taxonomy_bundle()
        taxonomy = bundle["taxonomy"]
        alias_to_key = bundle["alias_to_key"]
        sorted_aliases = bundle["sorted_aliases"]

        # Exact match
        if normalized_str in alias_to_key:
            target_key = alias_to_key[normalized_str]
            node = taxonomy[target_key]
            return {
                "source": "external_taxonomy",
                "matched_alias": normalized_str,
                "canonical_term": node["canonical"],
                "category": node["category"],
                "trending_suggestions": node["trending_suggestions"],
            }
        for alias in sorted_aliases:
            pattern = r"(^|[\s\-_/.,()])" + re.escape(alias) + r"([\s\-_/.,()]|$)"
            if re.search(pattern, normalized_str):
                target_key = alias_to_key[alias]
                entry = taxonomy[target_key]
                return {
                    "source": "external_taxonomy",
                    "matched_alias": alias,
                    "canonical_term": entry.get("canonical"),
                    "category": entry.get("category"),
                    "trending_suggestions": entry.get("trending_suggestions", []),
                }

        return None


def smart_ai_search(user_query):
    """
    Sub-50ms search query engine:
    Extracts price bounds, origins, and clean search tokens using pure regex.
    Combines keywords with OR logic and sorts on effective price.
    """
    query_str = user_query.strip()
    synonym_resolution = DynamicSynonymService.resolve_query(query_str)

    extracted_features = {
        "search_terms": [],
        "color": None,
        "max_price": None,
        "min_price": None,
        "brand": None,
        "is_made_in_nepal": False,
        "sort_field": "-listed_date",
        "synonym_resolution": synonym_resolution,
    }

    def parse_amount(val_str, unit_str):
        amt = float(val_str)
        unit = (unit_str or "").lower()
        if unit == "k":
            return amt * 1000.0
        elif unit in ["lakh", "lac", "lakhs", "lacs"]:
            return amt * 100000.0
        elif unit in ["crore", "cr"]:
            return amt * 10000000.0
        return amt

    between_match = re.search(
        r"between\s+(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?\s+(?:and|to|-)\s+(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?",
        query_str,
        re.IGNORECASE,
    )
    if between_match:
        extracted_features["min_price"] = parse_amount(between_match.group(1), between_match.group(2))
        extracted_features["max_price"] = parse_amount(between_match.group(3), between_match.group(4))

    if not extracted_features["max_price"]:
        max_match = re.search(
            r"(?:under|below|less than|max(?:imum)?)\s+(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?",
            query_str,
            re.IGNORECASE,
        )
        if max_match:
            extracted_features["max_price"] = parse_amount(max_match.group(1), max_match.group(2))

    if not extracted_features["min_price"]:
        min_match = re.search(
            r"(?:above|over|more than|min(?:imum)?)\s+(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?",
            query_str,
            re.IGNORECASE,
        )
        if min_match:
            extracted_features["min_price"] = parse_amount(min_match.group(1), min_match.group(2))

    if re.search(r"\b(made in nepal|local product|nepali product|nepal|nepali)\b", query_str, re.IGNORECASE):
        extracted_features["is_made_in_nepal"] = True

    if re.search(r"\b(cheap|cheapest|lowest price|budget|affordable|sasto)\b", query_str, re.IGNORECASE):
        extracted_features["sort_field"] = "effective_price"
    elif re.search(r"\b(expensive|highest price|premium|mahango)\b", query_str, re.IGNORECASE):
        extracted_features["sort_field"] = "-effective_price"

    price_stop_words = {
        "under", "below", "above", "over", "between", "price", "k", "lakh", "lac",
        "lakhs", "lacs", "crore", "cr", "thousand", "rs", "npr", "cheap", "cheapest",
        "lowest", "budget", "affordable", "expensive", "premium", "highest", "to", "and",
        "banaune", "garne", "chahiyo", "khojeko", "ramro", "with", "for", "in", "of", "at",
        "nepal", "nepali", "local", "product", "ko", "ma", "chha"
    }

    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", query_str.lower())
    clean_terms = [t for t in tokens if t not in price_stop_words and not t.isdigit() and len(t) >= 2]

    if synonym_resolution and synonym_resolution.get("canonical_term"):
        c_term = synonym_resolution["canonical_term"].lower().strip()
        if c_term not in clean_terms:
            clean_terms.insert(0, c_term)

    extracted_features["search_terms"] = clean_terms

    queryset = (
        MarketplaceProduct.objects.filter(is_available=True)
        .annotate(
            effective_price=Coalesce(
                "discounted_price",
                "listed_price",
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )

    if extracted_features["max_price"] is not None:
        queryset = queryset.filter(effective_price__lte=extracted_features["max_price"])

    if extracted_features["min_price"] is not None:
        queryset = queryset.filter(effective_price__gte=extracted_features["min_price"])

    if extracted_features["is_made_in_nepal"]:
        queryset = queryset.filter(is_made_in_nepal=True)

    if extracted_features["search_terms"]:
        term_queries = Q()
        for term_str in extracted_features["search_terms"]:
            boundary = r"(^|[\s\-_/.,()])" + re.escape(term_str) + r"([\s\-_/.,()]|$)"
            term_q = (
                Q(product__name__iregex=boundary)
                | Q(search_tags__iregex=boundary)
                | Q(product__description__icontains=term_str)
            )
            term_queries |= term_q

        queryset = queryset.filter(term_queries)

    return (
        queryset.select_related("product", "product__brand", "product__category")
        .order_by(extracted_features["sort_field"]),
        extracted_features,
    )