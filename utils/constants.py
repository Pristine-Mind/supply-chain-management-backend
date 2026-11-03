MARKETPLACE_TAXONOMY_CACHE_KEY = "marketplace_dynamic_taxonomy_graph_v3"
DEFAULT_TAXONOMY_CACHE_TIMEOUT = 3600  # 1 hour


QUERY_NOISE_TOKENS = {
    "bhayeko",
    "bata",
    "kasto",
    "kun",
    "paaincha",
    "lagi",
    "malai", "hamilai", "lai", "ho", "pani", "dine", "chai", "cha", "chha",
    "banaune", "garne", "chahiyo", "khojeko", "ramro", "halka", "wala", "wali",
    "ko", "ma", "under", "cheap", "sasto", "for", "with", "and", "needs", "want",
    "pure", "comfortable", "daily", "wear", "fit", "loose", "best", "quality"
}


PRICE_STOP_WORDS = {
    "under", "below", "above", "over", "between", "price", "k", "lakh", "lac",
    "lakhs", "lacs", "crore", "cr", "thousand", "rs", "npr", "cheap", "cheapest",
    "lowest", "budget", "affordable", "expensive", "premium", "highest", "to", "and",
    "malai", "hamilai", "lai", "ho", "pani", "dine", "chai", "banaune", "garne",
    "chahiyo", "khojeko", "ramro", "with", "for", "in", "of", "at", "nepal", "nepali",
    "local", "product", "ko", "ma", "chha", "the", "a", "an", "wala", "wali",
    "sasto", "mahango", "pure", "comfortable", "daily", "wear", "fit", "loose"
}


COMMON_ATTRIBUTES = {
    "black", "white", "red", "blue", "green", "grey", "gray", "yellow",
    "casual", "formal", "loose", "slim", "thick", "warm", "winter", "summer"
}


FOOTWEAR_ACCESSORY_EXCLUSIONS = {
    "polish", "sponge", "spray", "cleaner", "socks", "brush", "cream",
    "shiner", "lace", "insoles", "rack", "stand", "holder", "box",
    "glue", "wipes", "cover", "patch"
}


DEFAULT_TAXONOMY_SEEDS = [
    ("running shoes", "Running Shoes", "Footwear", "shoe", ["shoes", "sneaker", "sneakers", "jutta"]),
    ("casual shoes", "Casual Shoes", "Footwear", "shoe", ["shoes", "sneaker", "sneakers", "jutta"]),
    ("shoes", "Shoes", "Footwear", "shoe", ["shoe", "sneaker", "sneakers", "jutta"]),
    ("gaming laptop", "Gaming Laptop", "Electronics", "laptop", ["lenovo", "legion", "notebook", "thinkbook"]),
    ("thinkbook", "ThinkBook Laptop", "Electronics", "laptop", ["lenovo", "legion", "notebook"]),
    ("laptop", "Laptop", "Electronics", "laptop", ["lenovo", "legion", "notebook"]),
    ("wool cardigan", "Cardigan", "Clothing", "cardigan", ["sweater", "wool", "winter"]),
    ("cardigan", "Cardigan", "Clothing", "cardigan", ["sweater", "jacket", "wool"]),
    ("cotton tshirt", "T-Shirt", "Clothing", "tshirt", ["t-shirt", "tee", "shirt", "cotton"]),
    ("tshirt", "T-Shirt", "Clothing", "tshirt", ["t-shirt", "tee", "shirt"]),
    ("t-shirt", "T-Shirt", "Clothing", "tshirt", ["tshirt", "tee", "shirt"]),
]


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