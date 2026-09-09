import logging
import re 
from datetime import date, datetime
from django.utils.timezone import is_naive, localtime, make_aware
from keybert import KeyBERT
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from producer.models import MarketplaceProduct

from producer.models import MarketplaceProduct

# Lazy-load KeyBERT model to avoid memory bloat at startup
_kw_model = None
logger = logging.getLogger(__name__)


def get_keybert_model():
    """Lazy-load KeyBERT model on first use to avoid memory issues."""
    global _kw_model
    if _kw_model is None:
        logger.info("Loading KeyBERT model...")
        _kw_model = KeyBERT()
    return _kw_model


def unload_keybert_model():
    """Unload the KeyBERT model to free memory."""
    global _kw_model
    if _kw_model is not None:
        logger.info("Unloading KeyBERT model to free memory...")
        try:
            # Try to move model to CPU and clear CUDA cache if available
            if hasattr(_kw_model, "model") and hasattr(_kw_model.model, "cpu"):
                _kw_model.model.cpu()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except:
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

def smart_ai_search(user_query):
    """
    NLP query parser utilizing KeyBERT for semantic tag/entity extraction
    and structured regex parsing for price bounds and denominations.
    Returns the full un-sliced queryset.
    """
    from django.db.models import Q
    from .models import MarketplaceProduct

    query_str = user_query.strip()
    extracted_features = {
        "search_terms": [],
        "color": None,
        "max_price": None,
        "min_price": None,
        "brand": None,
        "is_made_in_nepal": False,
        "sort_field": "-listed_date",
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
        r'between\s+(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?\s+(?:and|to|-)\s+(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?',
        query_str,
        re.IGNORECASE,
    )
    if between_match:
        extracted_features["min_price"] = parse_amount(between_match.group(1), between_match.group(2))
        extracted_features["max_price"] = parse_amount(between_match.group(3), between_match.group(4))

    if not extracted_features["max_price"]:
        max_match = re.search(
            r'(?:under|below|less than|max(?:imum)?)\s+(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?',
            query_str,
            re.IGNORECASE,
        )
        if max_match:
            extracted_features["max_price"] = parse_amount(max_match.group(1), max_match.group(2))

    if not extracted_features["min_price"]:
        min_match = re.search(
            r'(?:above|over|more than|min(?:imum)?)\s+(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?',
            query_str,
            re.IGNORECASE,
        )
        if min_match:
            extracted_features["min_price"] = parse_amount(min_match.group(1), min_match.group(2))

    if re.search(r'\b(nepali|nepal|made in nepal|local)\b', query_str, re.IGNORECASE):
        extracted_features["is_made_in_nepal"] = True

    if re.search(r'\b(cheap|cheapest|lowest price|budget|affordable)\b', query_str, re.IGNORECASE):
        extracted_features["sort_field"] = "listed_price"
    elif re.search(r'\b(expensive|highest price|premium)\b', query_str, re.IGNORECASE):
        extracted_features["sort_field"] = "-listed_price"

    # Semantic entity extraction using the existing KeyBERT model
    try:
        kw_model = get_keybert_model()
        keywords = kw_model.extract_keywords(
            query_str,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            top_n=5,
        )
        semantic_terms = [kw[0].lower().strip() for kw in keywords if kw[0].strip()]
    except Exception as e:
        logger.warning(f"KeyBERT query extraction fallback: {e}")
        semantic_terms = []

    if not semantic_terms:
        semantic_terms = [word.lower() for word in re.findall(r'\b[a-zA-Z]{2,}\b', query_str)]

    price_stop_words = {"under", "below", "above", "over", "between", "price", "k", "lakh", "lac", "lakhs", "lacs", "crore", "cr"}
    extracted_features["search_terms"] = [t for t in semantic_terms if t not in price_stop_words]

    queryset = MarketplaceProduct.objects.filter(is_available=True).select_related("product", "product__brand", "product__category")

    if extracted_features["max_price"] is not None:
        queryset = queryset.filter(listed_price__lte=extracted_features["max_price"])

    if extracted_features["min_price"] is not None:
        queryset = queryset.filter(listed_price__gte=extracted_features["min_price"])

    if extracted_features["is_made_in_nepal"]:
        queryset = queryset.filter(is_made_in_nepal=True)

    if extracted_features["search_terms"]:
        term_filter = Q()
        for term in extracted_features["search_terms"]:
            term_filter |= (
                Q(search_tags__icontains=term)
                | Q(product__name__icontains=term)
                | Q(product__description__icontains=term)
            )
        queryset = queryset.filter(term_filter)

    return queryset.order_by(extracted_features["sort_field"]), extracted_features
    """
    Multi-variable NLP query parser:
    Extracts price ranges (including k/lakh/crore), colors, brands, origin,
    and core search terms to dynamically filter MarketplaceProduct.
    """
    query_str = user_query.lower()
    extracted_features = {
        "search_terms": [],
        "color": None,
        "max_price": None,
        "min_price": None,
        "brand": None,
        "is_made_in_nepal": False,
        "sort_field": "-created_at"
    }
    def parse_amount(val_str, unit_str):
        amt = float(val_str)
        if unit_str:
            unit = unit_str.lower().strip()
            if unit == 'k':
                amt *= 1000
            elif unit in ['lakh', 'lac', 'lakhs', 'lacs']:
                amt *= 100000
            elif unit in ['cr', 'crore', 'crores']:
                amt *= 10000000
        return amt
    range_pattern = r'(?:between|from)\s*(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|cr|crore)?\s*(?:to|and|-)\s*(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|cr|crore)?'
    range_match = re.search(range_pattern, query_str)
    if range_match:
        min_p = parse_amount(range_match.group(1), range_match.group(2))
        max_p = parse_amount(range_match.group(3), range_match.group(4))
        extracted_features["min_price"] = min(min_p, max_p)
        extracted_features["max_price"] = max(min_p, max_p)
        query_str = query_str[:range_match.start()] + query_str[range_match.end():]
    else:
        max_pattern = r'(?:under|below|less than|upto|within)\s*(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|cr|crore)?'
        max_match = re.search(max_pattern, query_str)
        if max_match:
            extracted_features["max_price"] = parse_amount(max_match.group(1), max_match.group(2))
            query_str = query_str[:max_match.start()] + query_str[max_match.end():]
        min_pattern = r'(?:above|over|more than|exceeding)\s*(?:rs\.?|npr)?\s*(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|cr|crore)?'
        min_match = re.search(min_pattern, query_str)
        if min_match:
            extracted_features["min_price"] = parse_amount(min_match.group(1), min_match.group(2))
            query_str = query_str[:min_match.start()] + query_str[min_match.end():]
    known_colors = [
        "black", "white", "red", "blue", "green", "silver",
        "grey", "gray", "gold", "yellow", "pink", "purple", "orange"
    ]
    for color in known_colors:
        if re.search(rf'\b{color}\b', query_str):
            extracted_features["color"] = color
            query_str = re.sub(rf'\b{color}\b', '', query_str)
            break
    if "made in nepal" in query_str or "nepali" in query_str or "nepalese" in query_str:
        extracted_features["is_made_in_nepal"] = True
        query_str = query_str.replace("made in nepal", "").replace("nepali", "").replace("nepalese", "")
    known_brands = ["asus", "lg", "dell", "samsung", "hp", "lenovo", "apple", "sony", "acer"]
    for brand in known_brands:
        if re.search(rf'\b{brand}\b', query_str):
            extracted_features["brand"] = brand
            query_str = re.sub(rf'\b{brand}\b', '', query_str)
            break
    if any(w in query_str for w in ["best selling", "best-selling", "top", "popular", "most bought"]):
        extracted_features["sort_field"] = "-id"
    elif any(w in query_str for w in ["cheap", "lowest price", "affordable"]):
        extracted_features["sort_field"] = "listed_price"
    elif any(w in query_str for w in ["expensive", "highest price", "premium"]):
        extracted_features["sort_field"] = "-listed_price"
    elif any(w in query_str for w in ["new", "latest", "recent"]):
        extracted_features["sort_field"] = "-created_at"
    stop_words = {
        "show", "me", "the", "a", "an", "best", "selling", "top", "cheap",
        "popular", "latest", "i", "want", "to", "buy", "looking", "for",
        "some", "under", "affordable", "lowest", "price", "with", "and", "in",
        "k", "lakh", "lac", "lakhs", "lacs", "crore", "cr"
    }
    clean_words = re.sub(r'[^\w\s]', '', query_str).split()
    search_terms = [w for w in clean_words if w not in stop_words]
    extracted_features["search_terms"] = search_terms
    queryset = MarketplaceProduct.objects.filter(is_available=True)

    if search_terms:
        term_filter = Q()
        for term in search_terms:
            term_filter |= Q(search_tags__icontains=term) | Q(product__name__icontains=term)
        queryset = queryset.filter(term_filter)

    if extracted_features["brand"]:
        queryset = queryset.filter(
            Q(product__brand__name__icontains=extracted_features["brand"]) |
            Q(search_tags__icontains=extracted_features["brand"])
        )

    if extracted_features["color"]:
        queryset = queryset.filter(
            Q(color__iexact=extracted_features["color"]) |
            Q(product__color__iexact=extracted_features["color"]) |
            Q(search_tags__icontains=extracted_features["color"])
        )

    if extracted_features["max_price"] is not None:
        queryset = queryset.filter(listed_price__lte=extracted_features["max_price"])

    if extracted_features["min_price"] is not None:
        queryset = queryset.filter(listed_price__gte=extracted_features["min_price"])

    if extracted_features["is_made_in_nepal"]:
        queryset = queryset.filter(is_made_in_nepal=True)
    try:
        recommended_products = queryset.order_by(extracted_features["sort_field"])[:10]
    except Exception:
        recommended_products = queryset.order_by('-id')[:10]

    return recommended_products, extracted_features, extracted_features["sort_field"]