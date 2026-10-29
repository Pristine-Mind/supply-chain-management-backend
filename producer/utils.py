import gc
import logging
import re
from datetime import date, datetime

from django.core.cache import cache
from django.db.models import Case, DecimalField, IntegerField, Q, Value, When
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
    CACHE_KEY = "marketplace_dynamic_taxonomy_graph_v3"
    CACHE_TIMEOUT = 3600  # 1 hour

    @classmethod
    def get_dynamic_graph(cls):
        cached_graph = cache.get(cls.CACHE_KEY)
        if cached_graph is not None:
            return cached_graph

        category_map = {}
        subcategory_to_category = {}
        for cat in Category.objects.filter(is_active=True).prefetch_related("subcategories"):
            c_name = cat.name.strip()
            c_key = c_name.lower()
            subcats = [s.name.strip() for s in cat.subcategories.filter(is_active=True)]

            category_map[c_key] = {
                "id": cat.id,
                "name": c_name,
                "subcategories": subcats,
                "brands": set(),
            }
            for s in subcats:
                subcategory_to_category[s.lower()] = c_key

        active_pairs = (
            MarketplaceProduct.objects.filter(is_available=True)
            .values("product__brand__name", "product__category__name")
            .distinct()
        )
        for pair in active_pairs:
            b_name = pair.get("product__brand__name")
            c_name = pair.get("product__category__name")
            if b_name and c_name:
                b_clean = b_name.strip()
                c_key = c_name.strip().lower()
                if b_clean.lower() != "unbranded":
                    if c_key in category_map:
                        category_map[c_key]["brands"].add(b_clean)

        for c_key in category_map:
            category_map[c_key]["brands"] = sorted(list(category_map[c_key]["brands"]))

        taxonomy_nodes = {}
        alias_to_key = {}
        for node in SearchTaxonomyNode.objects.filter(is_active=True):
            k = node.key.lower().strip()
            taxonomy_nodes[k] = {
                "canonical": node.canonical,
                "category": node.category,
                "aliases": [a.lower().strip() for a in (node.aliases or []) if a],
                "trending_suggestions": node.trending_suggestions or [],
            }
            alias_to_key[k] = k
            for alias in taxonomy_nodes[k]["aliases"]:
                alias_to_key[alias] = k

        sorted_aliases = sorted(alias_to_key.keys(), key=len, reverse=True)

        bundle = {
            "category_map": category_map,
            "subcategory_to_category": subcategory_to_category,
            "taxonomy_nodes": taxonomy_nodes,
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
        graph = cls.get_dynamic_graph()
        category_map = graph.get("category_map", {})
        subcategory_to_category = graph.get("subcategory_to_category", {})
        taxonomy_nodes = graph.get("taxonomy_nodes", {})
        alias_to_key = graph.get("alias_to_key", {})
        sorted_aliases = graph.get("sorted_aliases", [])

        cleaned = raw_query.lower().strip()
        noise_tokens = {
            "banaune", "garne", "chahiyo", "khojeko", "ramro", "halka", "wala", 
            "ko", "ma", "under", "cheap", "sasto", "for", "with", "and"
        }
        tokens = [
            w for w in re.findall(r"\b[a-zA-Z0-9]+\b", cleaned) 
            if w not in noise_tokens and not w.isdigit() and len(w) >= 2
        ]
        normalized_str = " ".join(tokens)

        extracted = {
            "canonical_term": None,
            "category": None,
            "related_brands": [],
            "sibling_subcategories": [],
            "matched_alias": None,
            "trending_suggestions": [],
        }

        for token in tokens:
            candidate_keys = [token, token.rstrip("s")]
            matched_c_key = next((k for k in candidate_keys if k in category_map), None)
            if matched_c_key:
                cat_info = category_map[matched_c_key]
                extracted["category"] = cat_info["name"]
                extracted["related_brands"].extend(cat_info["brands"][:6])
                extracted["sibling_subcategories"].extend(cat_info["subcategories"][:6])
                extracted["matched_alias"] = token
                break

        if not extracted["sibling_subcategories"]:
            for token in tokens:
                candidate_keys = [token, token.rstrip("s")]
                matched_sub = next((k for k in candidate_keys if k in subcategory_to_category), None)
                if matched_sub:
                    parent_c_key = subcategory_to_category[matched_sub]
                    cat_info = category_map.get(parent_c_key, {})
                    extracted["category"] = cat_info.get("name")
                    siblings = [s for s in cat_info.get("subcategories", []) if s.lower() != matched_sub]
                    extracted["sibling_subcategories"].extend(siblings[:6])
                    extracted["related_brands"].extend(cat_info.get("brands", [])[:4])
                    extracted["matched_alias"] = token
                    break

        matched_key = None
        if normalized_str in alias_to_key:
            matched_key = alias_to_key[normalized_str]
            extracted["matched_alias"] = normalized_str
        else:
            for alias in sorted_aliases:
                pattern = r"(^|[\s\-_/.,()])" + re.escape(alias) + r"([\s\-_/.,()]|$)"
                if re.search(pattern, normalized_str):
                    matched_key = alias_to_key[alias]
                    extracted["matched_alias"] = alias
                    break

        if matched_key and matched_key in taxonomy_nodes:
            node = taxonomy_nodes[matched_key]
            extracted["canonical_term"] = node["canonical"]
            if not extracted["category"] and node["category"]:
                extracted["category"] = node["category"]
            extracted["trending_suggestions"] = node["trending_suggestions"]

            cat_k = (node["category"] or "").lower().strip()
            if cat_k in category_map:
                cat_info = category_map[cat_k]
                extracted["related_brands"].extend(cat_info.get("brands", [])[:5])
                extracted["sibling_subcategories"].extend(cat_info.get("subcategories", [])[:5])

        extracted["related_brands"] = list(dict.fromkeys(extracted["related_brands"]))
        extracted["sibling_subcategories"] = list(dict.fromkeys(extracted["sibling_subcategories"]))

        return extracted if any(extracted.values()) else None


def smart_ai_search(user_query, target_count=20):
    query_str = (user_query or "").strip()
    synonym_resolution = DynamicSynonymService.resolve_query(query_str)

    extracted_features = {
        "search_terms": [],
        "related_brands": [],
        "sibling_subcategories": [],
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
        "nepal", "nepali", "local", "product", "ko", "ma", "chha", "the", "a", "an",
    }

    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", query_str.lower())
    clean_terms = [t for t in tokens if t not in price_stop_words and not t.isdigit() and len(t) >= 2]

    canonical_term = None
    resolved_category = None
    if synonym_resolution:
        canonical_term = synonym_resolution.get("canonical_term")
        resolved_category = synonym_resolution.get("category")
        extracted_features["related_brands"] = synonym_resolution.get("related_brands", [])
        extracted_features["sibling_subcategories"] = synonym_resolution.get("sibling_subcategories", [])

        if canonical_term:
            for term in canonical_term.lower().split():
                if term not in clean_terms and term not in price_stop_words:
                    clean_terms.append(term)

    extracted_features["search_terms"] = clean_terms

    base_qs = (
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
        base_qs = base_qs.filter(effective_price__lte=extracted_features["max_price"])

    if extracted_features["min_price"] is not None:
        base_qs = base_qs.filter(effective_price__gte=extracted_features["min_price"])

    if extracted_features["is_made_in_nepal"]:
        base_qs = base_qs.filter(is_made_in_nepal=True)


    tier1_q = Q()
    if clean_terms:
        for term_str in clean_terms:
            tier1_q |= (
                Q(product__name__icontains=term_str)
                | Q(search_tags__icontains=term_str)
                | Q(product__description__icontains=term_str)
            )

    tier2_q = Q()
    for rel_brand in extracted_features["related_brands"][:5]:
        tier2_q |= (
            Q(product__brand__name__iexact=rel_brand)
            | Q(product__name__icontains=rel_brand)
        )

    for sibling in extracted_features["sibling_subcategories"][:5]:
        tier2_q |= (
            Q(product__subcategory__name__iexact=sibling)
            | Q(product__name__icontains=sibling)
            | Q(search_tags__icontains=sibling.lower())
        )

    tier3_q = Q()
    if resolved_category:
        tier3_q |= (
            Q(product__category__name__icontains=resolved_category)
            | Q(search_tags__icontains=resolved_category.lower())
        )

    when_clauses = []
    if tier1_q.children:
        when_clauses.append(When(tier1_q, then=Value(1)))
    if tier2_q.children:
        when_clauses.append(When(tier2_q, then=Value(2)))
    if tier3_q.children:
        when_clauses.append(When(tier3_q, then=Value(3)))

    final_qs = (
        base_qs.annotate(
            match_rank=Case(
                *when_clauses,
                default=Value(4),
                output_field=IntegerField(),
            )
        )
        .select_related("product", "product__brand", "product__category")
        .order_by("match_rank", extracted_features["sort_field"])
    )

    return final_qs, extracted_features