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

from producer.models import Brand, Category, MarketplaceProduct, SearchTaxonomyNode
from utils.constants import (
    CHEAP_SORT_REGEX,
    COMMON_ATTRIBUTES,
    DEFAULT_TAXONOMY_CACHE_TIMEOUT,
    DEFAULT_TAXONOMY_SEEDS,
    EXPENSIVE_SORT_REGEX,
    FOOTWEAR_ACCESSORY_EXCLUSIONS,
    MARKETPLACE_TAXONOMY_CACHE_KEY,
    NEPALI_PRODUCT_REGEX,
    PRICE_BETWEEN_REGEX,
    PRICE_MAX_REGEX,
    PRICE_MIN_REGEX,
    PRICE_STOP_WORDS,
    QUERY_NOISE_TOKENS,
)

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


class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_terminal = False
        self.canonical = None
        self.category = None
        self.primary_noun = None
        self.aliases = []


class TaxonomyTrie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, phrase: str, canonical: str, category: str, primary_noun: str, aliases: list = None):
        words = phrase.lower().strip().split()
        curr = self.root
        for word in words:
            if word not in curr.children:
                curr.children[word] = TrieNode()
            curr = curr.children[word]
        curr.is_terminal = True
        curr.canonical = canonical
        curr.category = category
        curr.primary_noun = primary_noun
        curr.aliases = aliases or []

    def match_longest(self, tokens, start_idx):
        curr = self.root
        last_match = None
        matched_len = 0
        for i in range(start_idx, len(tokens)):
            w = tokens[i]
            if w in curr.children:
                curr = curr.children[w]
                if curr.is_terminal:
                    last_match = (curr.canonical, curr.category, curr.primary_noun, curr.aliases)
                    matched_len = (i - start_idx) + 1
            else:
                break
        return last_match, matched_len


class DynamicSynonymService:
    CACHE_KEY = MARKETPLACE_TAXONOMY_CACHE_KEY
    CACHE_TIMEOUT = DEFAULT_TAXONOMY_CACHE_TIMEOUT

    @classmethod
    def get_dynamic_tree(cls):
        try:
            cached_tree = cache.get(cls.CACHE_KEY)
            if cached_tree is not None:
                return cached_tree
        except Exception as e:
            logger.warning(f"Redis lookup failed ({e}), building tree directly...")

        trie = TaxonomyTrie()

        for phrase, canonical, category, noun, aliases in DEFAULT_TAXONOMY_SEEDS:
            trie.insert(phrase, canonical, category, noun, aliases)

        try:
            for node in SearchTaxonomyNode.objects.filter(is_active=True):
                k = node.key.lower().strip()
                canonical = node.canonical
                cat = node.category or ""
                aliases = [a.lower().strip() for a in (node.aliases or []) if a]
                trie.insert(k, canonical, cat, k, aliases)
                for alias in aliases:
                    trie.insert(alias, canonical, cat, k, aliases)
        except Exception as e:
            logger.debug(f"Taxonomy DB sync bypassed: {e}")

        try:
            cache.set(cls.CACHE_KEY, trie, timeout=cls.CACHE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache taxonomy tree in Redis: {e}")

        return trie

    @classmethod
    def invalidate_cache(cls):
        try:
            cache.delete(cls.CACHE_KEY)
        except Exception as e:
            logger.warning(f"Failed to invalidate Redis cache: {e}")

    @classmethod
    def resolve_query(cls, raw_query: str):
        trie = cls.get_dynamic_tree()
        cleaned = raw_query.lower()

        tokens = re.findall(r"\b[a-zA-Z0-9\-]+\b", cleaned)
        filtered_tokens = [
            t for t in tokens
            if t not in QUERY_NOISE_TOKENS and not t.isdigit() and len(t) >= 2
        ]

        canonical_term = None
        resolved_category = None
        target_noun = None
        aliases = []

        i = 0
        while i < len(filtered_tokens):
            match, length = trie.match_longest(filtered_tokens, i)
            if match:
                canonical_term, resolved_category, target_noun, aliases = match
                i += length
            else:
                i += 1

        primary_words = []
        modifier_words = []
        for t in filtered_tokens:
            if t in PRICE_STOP_WORDS:
                continue
            if t in COMMON_ATTRIBUTES:
                modifier_words.append(t)
            else:
                primary_words.append(t)

        target_anchors = list(dict.fromkeys(
            primary_words + ([target_noun] if target_noun else []) + aliases
        ))

        return {
            "canonical_term": canonical_term,
            "category": resolved_category,
            "target_noun": target_noun,
            "primary_words": primary_words,
            "modifier_words": modifier_words,
            "target_anchors": target_anchors,
            "aliases": aliases,
        }


def smart_ai_search(user_query, target_count=20):
    query_str = (user_query or "").strip()
    resolution = DynamicSynonymService.resolve_query(query_str)

    extracted_features = {
        "search_terms": resolution["target_anchors"],
        "primary_words": resolution["primary_words"],
        "modifier_words": resolution["modifier_words"],
        "target_noun": resolution["target_noun"],
        "canonical_term": resolution["canonical_term"],
        "category": resolution["category"],
        "color": None,
        "max_price": None,
        "min_price": None,
        "is_made_in_nepal": False,
        "sort_field": "-listed_date",
        "synonym_resolution": resolution,
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

    between_match = re.search(PRICE_BETWEEN_REGEX, query_str, re.IGNORECASE)
    if between_match:
        extracted_features["min_price"] = parse_amount(between_match.group(1), between_match.group(2))
        extracted_features["max_price"] = parse_amount(between_match.group(3), between_match.group(4))

    if not extracted_features["max_price"]:
        max_match = re.search(PRICE_MAX_REGEX, query_str, re.IGNORECASE)
        if max_match:
            extracted_features["max_price"] = parse_amount(max_match.group(1), max_match.group(2))

    if not extracted_features["min_price"]:
        min_match = re.search(PRICE_MIN_REGEX, query_str, re.IGNORECASE)
        if min_match:
            extracted_features["min_price"] = parse_amount(min_match.group(1), min_match.group(2))

    if re.search(NEPALI_PRODUCT_REGEX, query_str, re.IGNORECASE):
        extracted_features["is_made_in_nepal"] = True

    if re.search(CHEAP_SORT_REGEX, query_str, re.IGNORECASE):
        extracted_features["sort_field"] = "effective_price"
    elif re.search(EXPENSIVE_SORT_REGEX, query_str, re.IGNORECASE):
        extracted_features["sort_field"] = "-effective_price"

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

    if resolution["category"] == "Footwear":
        for acc in FOOTWEAR_ACCESSORY_EXCLUSIONS:
            base_qs = base_qs.exclude(product__name__icontains=acc)

  
    tier1_q = Q()
    if resolution["canonical_term"]:
        tier1_q |= Q(product__name__icontains=resolution["canonical_term"])

    tier2_q = Q()
    target_noun = resolution["target_noun"]
    if target_noun:
        noun_q = Q(product__name__iregex=r"\y" + re.escape(target_noun) + r"\y")
        for a in resolution["aliases"]:
            noun_q |= Q(product__name__iregex=r"\y" + re.escape(a) + r"\y")
        tier2_q &= noun_q

    for pw in resolution["primary_words"]:
        if len(pw) >= 3:
            tier2_q |= (
                Q(product__name__iregex=r"\y" + re.escape(pw) + r"\y")
                | Q(product__description__iregex=r"\y" + re.escape(pw) + r"\y")
            )

    tier3_q = Q()
    for mw in resolution["modifier_words"]:
        tier3_q |= (
            Q(product__name__iregex=r"\y" + re.escape(mw) + r"\y")
            | Q(product__description__iregex=r"\y" + re.escape(mw) + r"\y")
        )

    candidate_q = Q()
    for anchor in resolution["target_anchors"]:
        candidate_q |= (
            Q(product__name__iregex=r"\y" + re.escape(anchor) + r"\y")
            | Q(product__description__iregex=r"\y" + re.escape(anchor) + r"\y")
        )

    if candidate_q.children:
        base_qs = base_qs.filter(candidate_q)

    
    match_score_expr = Value(0)
    if resolution["canonical_term"]:
        match_score_expr = match_score_expr + Case(
            When(product__name__icontains=resolution["canonical_term"], then=Value(25)),
            default=Value(0),
            output_field=IntegerField(),
        )

    if resolution["target_noun"]:
        noun_wb = r"\y" + re.escape(resolution["target_noun"]) + r"\y"
        match_score_expr = match_score_expr + Case(
            When(Q(product__name__iregex=noun_wb), then=Value(15)),
            default=Value(0),
            output_field=IntegerField(),
        )

    if extracted_features["is_made_in_nepal"]:
        match_score_expr = match_score_expr + Case(
            When(Q(is_made_in_nepal=True), then=Value(10)),
            default=Value(0),
            output_field=IntegerField(),
        )

    for pw in resolution["primary_words"]:
        if len(pw) >= 2:
            wb_pw = r"\y" + re.escape(pw) + r"\y"
            match_score_expr = match_score_expr + Case(
                When(Q(product__name__iregex=wb_pw), then=Value(10)),
                default=Value(0),
                output_field=IntegerField(),
            ) + Case(
                When(Q(product__description__iregex=wb_pw), then=Value(4)),
                default=Value(0),
                output_field=IntegerField(),
            )

    for mw in resolution["modifier_words"]:
        wb_mw = r"\y" + re.escape(mw) + r"\y"
        match_score_expr = match_score_expr + Case(
            When(Q(product__name__iregex=wb_mw), then=Value(6)),
            default=Value(0),
            output_field=IntegerField(),
        ) + Case(
            When(Q(product__description__iregex=wb_mw), then=Value(2)),
            default=Value(0),
            output_field=IntegerField(),
        )

    final_qs = (
        base_qs.annotate(
            match_score=match_score_expr
        )
        .select_related("product", "product__brand", "product__category")
        .order_by("-match_score", extracted_features["sort_field"])
    )

    return final_qs, extracted_features