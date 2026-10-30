"""
Constants for search taxonomy, query parsing, and caching.
"""
MARKETPLACE_TAXONOMY_CACHE_KEY = "marketplace_dynamic_taxonomy_graph_v3"
DEFAULT_TAXONOMY_CACHE_TIMEOUT = 3600  # 1 hour
QUERY_NOISE_TOKENS = {
    "banaune",
    "garne",
    "chahiyo",
    "khojeko",
    "ramro",
    "halka",
    "wala",
    "ko",
    "ma",
    "under",
    "cheap",
    "sasto",
    "for",
    "with",
    "and",
}

PRICE_STOP_WORDS = {
    "under",
    "below",
    "above",
    "over",
    "between",
    "price",
    "k",
    "lakh",
    "lac",
    "lakhs",
    "lacs",
    "crore",
    "cr",
    "thousand",
    "rs",
    "npr",
    "cheap",
    "cheapest",
    "lowest",
    "budget",
    "affordable",
    "expensive",
    "premium",
    "highest",
    "to",
    "and",
    "banaune",
    "garne",
    "chahiyo",
    "khojeko",
    "ramro",
    "with",
    "for",
    "in",
    "of",
    "at",
    "nepal",
    "nepali",
    "local",
    "product",
    "ko",
    "ma",
    "chha",
    "the",
    "a",
    "an",
}

NEPALI_PRODUCT_REGEX = r"\b(made in nepal|local product|nepali product|nepal|nepali)\b"
CHEAP_SORT_REGEX = r"\b(cheap|cheapest|lowest price|budget|affordable|sasto)\b"
EXPENSIVE_SORT_REGEX = r"\b(expensive|highest price|premium|mahango)\b"

PRICE_BETWEEN_REGEX = (
    r"between\s+(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?\s+"
    r"(?:and|to|-)\s+(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?"
)

PRICE_MAX_REGEX = (
    r"(?:under|below|less than|max(?:imum)?)\s+(?:rs\.?|npr)?\s*"
    r"(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?"
)

PRICE_MIN_REGEX = (
    r"(?:above|over|more than|min(?:imum)?)\s+(?:rs\.?|npr)?\s*"
    r"(\d+(?:\.\d+)?)\s*(k|lakh|lac|lakhs|lacs|crore|cr)?"
)