import re


class TagExtractor:
    """Comprehensive tag extraction for marketplace products"""

    # Category mapping with tags (using your actual category codes)
    CATEGORY_TAGS = {
        "EG": {  # Electronics & Gadgets
            "products": {
                "television_tv": [
                    "tv",
                    "television",
                    "led tv",
                    "lcd tv",
                    "oled tv",
                    "qled tv",
                    "4k tv",
                    "8k tv",
                    "smart tv",
                    "android tv",
                    "google tv",
                    "roku tv",
                    "curved tv",
                    "flat tv",
                    "hd ready",
                    "full hd",
                    "ultra hd",
                    "hdr tv",
                    "dolby vision",
                ],
                "refrigerator_fridge": [
                    "refrigerator",
                    "fridge",
                    "freezer",
                    "mini fridge",
                    "double door",
                    "single door",
                    "side by side",
                    "french door",
                    "bottom freezer",
                    "top freezer",
                    "frost free",
                    "direct cool",
                    "inverter fridge",
                ],
                "washing_machine": [
                    "washing machine",
                    "washer",
                    "dryer",
                    "washer dryer",
                    "front load",
                    "top load",
                    "semi automatic",
                    "fully automatic",
                    "portable washer",
                ],
                "air_conditioner": [
                    "ac",
                    "air conditioner",
                    "split ac",
                    "window ac",
                    "portable ac",
                    "inverter ac",
                    "smart ac",
                    "1 ton",
                    "1.5 ton",
                    "2 ton",
                ],
                "mobile_phone": ["smartphone", "mobile", "cell phone", "android", "iphone", "5g", "4g"],
                "laptop": ["laptop", "notebook", "gaming laptop", "business laptop", "ultrabook"],
                "audio": ["headphone", "earphone", "speaker", "soundbar", "earbuds", "bluetooth speaker"],
                "accessories": ["charger", "cable", "power bank", "case", "screen protector", "adapter"],
            },
            "attributes": {
                "display": [
                    "oled",
                    "amoled",
                    "lcd",
                    "ips",
                    "retina",
                    "hdr",
                    "4k",
                    "8k",
                    "1080p",
                    "720p",
                    "120hz",
                    "144hz",
                    "240hz",
                    "touch screen",
                    "foldable",
                ],
                "connectivity": ["wifi", "bluetooth", "5g", "4g", "nfc", "gps", "hdmi", "usb-c", "ethernet"],
                "smart": ["smart", "voice control", "alexa", "google assistant", "app control", "iot"],
                "energy": ["inverter", "energy efficient", "power saving", "eco mode", "star rated"],
                "battery": ["long battery life", "fast charging", "wireless charging", "quick charge"],
            },
        },
        "HL": {  # Home & Living
            "products": {
                "refrigerators": ["refrigerator", "fridge", "freezer", "mini fridge", "bar fridge"],
                "washing_machines": ["washing machine", "washer", "dryer", "laundry machine"],
                "air_conditioners": ["ac", "air conditioner", "cooler", "heater"],
                "kitchen_appliances": [
                    "microwave",
                    "oven",
                    "stove",
                    "cooktop",
                    "chimney",
                    "water heater",
                    "geyser",
                    "mixer",
                    "grinder",
                    "juicer",
                    "blender",
                    "air fryer",
                    "rice cooker",
                    "toaster",
                    "kettle",
                    "coffee maker",
                ],
                "furniture": [
                    "sofa",
                    "chair",
                    "table",
                    "bed",
                    "mattress",
                    "pillow",
                    "wardrobe",
                    "cabinet",
                    "bookshelf",
                    "dining table",
                    "office chair",
                    "study table",
                ],
                "decor": ["wall art", "mirror", "clock", "vase", "planter", "curtains", "cushion", "rug"],
                "lighting": ["lamp", "light", "chandelier", "led light", "bulb", "tube light"],
            },
            "attributes": {
                "material": ["wooden", "metal", "glass", "fabric", "leather", "plastic", "bamboo", "marble"],
                "style": ["modern", "traditional", "classic", "minimalist", "rustic", "industrial", "vintage"],
                "features": ["adjustable", "foldable", "removable", "washable", "water resistant", "space saving"],
                "smart_home": ["smart", "wifi", "app control", "voice control", "automation"],
            },
        },
        "FA": {  # Fashion & Apparel
            "products": {
                "clothing": [
                    "shirt",
                    "t shirt",
                    "pants",
                    "jeans",
                    "jacket",
                    "dress",
                    "skirt",
                    "sweater",
                    "hoodie",
                    "coat",
                    "blouse",
                    "leggings",
                    "shorts",
                    "saree",
                    "kurti",
                    "sherwani",
                ],
                "footwear": ["shoes", "sneakers", "sandals", "slippers", "boots", "heels", "flats", "loafers"],
                "accessories": [
                    "watch",
                    "bag",
                    "belt",
                    "hat",
                    "scarf",
                    "sunglasses",
                    "jewelry",
                    "necklace",
                    "earrings",
                    "ring",
                    "bracelet",
                    "wallet",
                ],
                "traditional": ["dhoti", "kurta", "lehenga", "dupatta", "pagri", "topi"],
            },
            "attributes": {
                "material": [
                    "cotton",
                    "silk",
                    "wool",
                    "leather",
                    "denim",
                    "linen",
                    "polyester",
                    "nylon",
                    "cashmere",
                    "velvet",
                    "satin",
                    "lace",
                ],
                "occasion": ["casual", "formal", "party", "wedding", "office", "party wear", "daily wear"],
                "season": ["summer", "winter", "spring", "autumn", "all season"],
                "fit": ["slim fit", "regular fit", "loose fit", "oversized", "tailored"],
            },
        },
        "GE": {  # Groceries & Essentials
            "products": {
                "staples": ["rice", "flour", "oil", "sugar", "salt", "lentils", "daal", "pulses", "spices"],
                "packaged": ["noodles", "pasta", "cereal", "biscuits", "snacks", "chips", "cookies"],
                "beverages": ["tea", "coffee", "juice", "soda", "water", "milk", "yogurt"],
                "condiments": ["sauce", "ketchup", "mayonnaise", "pickle", "chutney", "honey", "jam"],
            },
            "attributes": {
                "quality": ["organic", "natural", "pure", "fresh", "preservative free", "non gmo", "gluten free"],
                "packaging": ["packaged", "bulk", "family pack", "single serve", "eco friendly packaging"],
                "dietary": ["vegan", "vegetarian", "halal", "kosher", "low sugar", "low sodium", "high protein"],
            },
        },
        "HB": {  # Health & Beauty
            "products": {
                "skincare": ["cream", "lotion", "face wash", "serum", "moisturizer", "sunscreen", "face mask"],
                "haircare": ["shampoo", "conditioner", "hair oil", "hair serum", "hair color", "hair mask"],
                "makeup": ["foundation", "lipstick", "eyeshadow", "mascara", "kajal", "eyeliner", "compact"],
                "personal_care": ["soap", "body wash", "deodorant", "perfume", "toothpaste", "mouthwash"],
                "wellness": ["vitamin", "supplement", "protein powder", "ayurvedic", "herbal"],
            },
            "attributes": {
                "ingredients": ["herbal", "organic", "natural", "chemical free", "paraben free", "sulfate free"],
                "skin_type": ["dry skin", "oily skin", "normal skin", "sensitive skin", "combination skin"],
                "benefits": ["anti aging", "whitening", "brightening", "hydrating", "repairing", "soothing"],
            },
        },
        "SP": {  # Sports & Fitness
            "products": {
                "apparel": ["sports shoe", "track suit", "sports t shirt", "shorts", "leggings", "sports bra"],
                "equipment": ["dumbbell", "barbell", "mat", "yoga mat", "ball", "racket", "bat", "gloves"],
                "fitness": ["gym", "fitness band", "smartwatch", "bottle", "protein", "supplement"],
                "outdoor": ["camping gear", "tent", "backpack", "hiking shoe", "climbing gear"],
            },
            "attributes": {
                "sport_type": [
                    "cricket",
                    "football",
                    "basketball",
                    "tennis",
                    "badminton",
                    "swimming",
                    "running",
                    "yoga",
                    "gym",
                    "workout",
                    "cardio",
                    "strength",
                ],
                "features": ["breathable", "lightweight", "non slip", "sweatproof", "shockproof", "durable"],
            },
        },
        "AU": {  # Automotive
            "products": {
                "parts": ["tire", "battery", "brake", "engine oil", "filter", "spark plug", "headlight", "taillight"],
                "accessories": ["car cover", "seat cover", "floor mat", "steering cover", "car charger", "phone holder"],
                "tools": ["tool kit", "jack", "wrench", "screwdriver", "tire inflator"],
                "care": ["car cleaner", "polish", "wax", "shampoo", "microfiber cloth"],
            },
            "attributes": {
                "vehicle_type": ["car", "bike", "scooter", "truck", "bus", "tractor", "bicycle"],
                "compatibility": ["universal", "specific model", "aftermarket", "original", "oem"],
                "material": ["rubber", "metal", "plastic", "fabric", "leather", "carbon fiber"],
            },
        },
        "FD": {  # Food & Beverages
            "products": {
                "snacks": ["chips", "namkeen", "biscuits", "cookies", "cake", "pastry", "chocolate", "candy"],
                "beverages": ["soft drink", "juice", "energy drink", "smoothie", "milkshake", "coffee", "tea"],
                "ready_to_eat": ["instant noodles", "frozen food", "canned food", "ready meal", "instant mix"],
                "dairy": ["milk", "cheese", "butter", "yogurt", "paneer", "cream"],
            },
            "attributes": {
                "flavor": ["sweet", "salty", "spicy", "sour", "bitter", "savory", "tangy"],
                "dietary": ["vegetarian", "non vegetarian", "vegan", "gluten free", "lactose free"],
                "preservation": ["fresh", "frozen", "canned", "dried", "fermented"],
            },
        },
        "BK": {  # Books & Media
            "products": {
                "books": ["novel", "textbook", "magazine", "comic", "guide", "encyclopedia", "dictionary"],
                "stationery": ["notebook", "pen", "pencil", "marker", "highlighter", "eraser", "ruler"],
                "music": ["cd", "vinyl", "instrument", "guitar", "piano", "keyboard", "drums"],
                "art": ["canvas", "paint", "brush", "easel", "sketchbook", "color pencil"],
            },
            "attributes": {
                "genre": ["fiction", "non fiction", "mystery", "thriller", "romance", "sci fi", "fantasy", "comedy"],
                "format": ["hardcover", "paperback", "digital", "audio book", "ebook", "kindle"],
                "level": ["beginner", "intermediate", "advanced", "professional", "children", "adult"],
            },
        },
    }

    # Common tags for all products
    COMMON_TAGS = {
        "price_segments": {
            "budget": ["budget", "affordable", "economy", "cheap", "low price", "value", "under 500", "under 1000"],
            "mid_range": ["mid range", "moderate", "value for money", "best value", "popular"],
            "premium": ["premium", "luxury", "high end", "expensive", "high quality", "deluxe"],
            "super_premium": ["ultra premium", "flagship", "top tier", "exclusive", "limited"],
        },
        "condition": ["new", "genuine", "authentic", "original", "brand new", "factory sealed"],
        "popularity": ["bestseller", "trending", "popular", "viral", "hot selling", "customer favorite"],
        "occasion": ["gift", "festival", "birthday", "anniversary", "wedding", "diwali", "dashain", "tihar"],
        "service": ["warranty", "guarantee", "easy return", "free delivery", "fast shipping", "installation"],
    }

    # Brands database (expandable)
    BRANDS = {
        "electronics": [
            "samsung",
            "lg",
            "sony",
            "panasonic",
            "philips",
            "tcl",
            "hisense",
            "xiaomi",
            "oneplus",
            "realme",
            "apple",
            "google",
            "microsoft",
            "dell",
            "hp",
            "lenovo",
            "asus",
            "acer",
            "msi",
            "razer",
            "logitech",
            "bose",
            "jbl",
            "boat",
            "mi",
            "redmi",
            "oppo",
            "vivo",
        ],
        "appliances": [
            "whirlpool",
            "godrej",
            "haier",
            "voltas",
            "daikin",
            "blue star",
            "carrier",
            "hitachi",
            "mitsubishi",
            "bosch",
            "siemens",
            "electrolux",
            "ifb",
            "videocon",
            "crompton",
            "havells",
        ],
        "fashion": [
            "nike",
            "adidas",
            "puma",
            "reebok",
            "zara",
            "hm",
            "levi",
            "arrow",
            "allen solly",
            "us polo",
            "tommy",
            "calvin klein",
            "gucci",
            "prada",
            "louis vuitton",
            "chanel",
        ],
        "grocery": [
            "nestle",
            "unilever",
            "procter & gamble",
            "pepsico",
            "coca cola",
            "britannia",
            "amul",
            "dabur",
            "patanjali",
            "mother dairy",
        ],
    }

    @classmethod
    def extract_tags(cls, marketplace_product):
        """Main tag extraction method"""
        tags = set()

        # Get product info
        product = marketplace_product.product
        category_code = product.category.category_code if product.category else None

        product_name = product.name.lower()
        product_description = (product.description or "").lower()
        additional_info = (marketplace_product.additional_information or "").lower()

        combined_text = f"{product_name} {product_description} {additional_info}"

        # 1. Extract category-specific tags
        if category_code in cls.CATEGORY_TAGS:
            category_tags = cls._extract_category_tags(category_code, combined_text)
            tags.update(category_tags)

            # Add category name as tag
            if product.category:
                tags.add(product.category.category_name.lower())

        # 2. Extract brands
        brands = cls._extract_brands(combined_text)
        tags.update(brands)

        # 3. Extract product specifications
        specs = cls._extract_specifications(combined_text, category_code)
        tags.update(specs)

        # 4. Extract size and dimensions
        sizes = cls._extract_sizes(combined_text)
        tags.update(sizes)

        # 5. Extract colors
        colors = cls._extract_colors(combined_text, marketplace_product)
        tags.update(colors)

        # 6. Add product field-based tags
        cls._add_field_tags(marketplace_product, tags)

        # 7. Add price-related tags
        cls._add_price_tags(marketplace_product, tags)

        # 8. Add popularity tags
        cls._add_popularity_tags(marketplace_product, tags)

        # 9. Add feature tags from description
        features = cls._extract_features(combined_text, category_code)
        tags.update(features)

        # 10. Add numeric values as tags
        numeric_tags = cls._extract_numeric_values(combined_text)
        tags.update(numeric_tags)

        # 11. Clean and limit
        cleaned_tags = cls._clean_tags(tags)

        return list(cleaned_tags)[:35]  # Max 35 tags

    @classmethod
    def _extract_category_tags(cls, category_code, text):
        """Extract tags specific to category"""
        tags = set()
        category_data = cls.CATEGORY_TAGS.get(category_code, {})

        # Extract product type tags
        for product_type, keywords in category_data.get("products", {}).items():
            if isinstance(keywords, list):
                for keyword in keywords:
                    if keyword in text:
                        tags.add(keyword)
                        # Add the product type as tag (e.g., 'television', 'refrigerator')
                        tags.add(product_type.replace("_", " "))

        # Extract attribute tags
        for attr_category, attributes in category_data.get("attributes", {}).items():
            if isinstance(attributes, list):
                for attr in attributes:
                    if attr in text:
                        tags.add(attr)
                        tags.add(attr_category)

        return tags

    @classmethod
    def _extract_brands(cls, text):
        """Extract brand names from text"""
        brands_found = set()

        for brand_category, brand_list in cls.BRANDS.items():
            for brand in brand_list:
                # Check for brand as whole word
                if re.search(r"\b" + re.escape(brand) + r"\b", text):
                    brands_found.add(brand)
                    brands_found.add(brand_category)

        return brands_found

    @classmethod
    def _extract_specifications(cls, text, category_code):
        """Extract technical specifications"""
        tags = set()

        # Screen sizes (for EG category)
        if category_code == "EG":
            screen_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:inch|"|inches|' "|″)", text)
            for size in screen_matches:
                size_float = float(size)
                tags.add(f"{size} inch")
                if size_float >= 65:
                    tags.add("cinema size")
                elif size_float >= 55:
                    tags.add("large screen")
                elif size_float >= 43:
                    tags.add("medium screen")
                elif size_float >= 32:
                    tags.add("small screen")
                elif size_float < 32:
                    tags.add("compact screen")

        # Capacities (refrigerators, washing machines, ACs)
        capacity_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(liters|ltrs|litres|kg|kgs|ton)", text)
        for capacity, unit in capacity_matches:
            tags.add(f"{capacity}{unit}")
            capacity_float = float(capacity)

            if unit in ["liters", "ltrs", "litres"]:
                if capacity_float >= 500:
                    tags.add("large capacity fridge")
                elif capacity_float >= 300:
                    tags.add("family size fridge")
                elif capacity_float >= 200:
                    tags.add("medium fridge")
                elif capacity_float >= 100:
                    tags.add("compact fridge")

            elif unit == "ton":
                tags.add(f"{capacity} ton ac")
                if capacity_float >= 2:
                    tags.add("large room ac")
                elif capacity_float >= 1.5:
                    tags.add("medium room ac")
                else:
                    tags.add("small room ac")

        # Resolution
        resolutions = {
            "8k": "8k resolution",
            "4k": "4k ultra hd",
            "ultra hd": "ultra hd",
            "full hd": "full hd 1080p",
            "hd ready": "hd ready 720p",
        }
        for res, tag in resolutions.items():
            if res in text:
                tags.add(tag)
                tags.add(res)

        # Storage and memory
        storage_matches = re.findall(r"(\d+(?:gb|tb|gB|tB|GB|TB))", text)
        for storage in storage_matches:
            tags.add(storage.lower())

        ram_matches = re.findall(r"(\d+(?:gb|gB|GB))\s+ram", text)
        for ram in ram_matches:
            tags.add(f"{ram.lower()} ram")

        return tags

    @classmethod
    def _extract_sizes(cls, text):
        """Extract size information"""
        tags = set()

        size_words = {
            "xs": ["xs", "extra small", "x-small"],
            "s": ["s", "small"],
            "m": ["m", "medium"],
            "l": ["l", "large"],
            "xl": ["xl", "extra large", "x-large"],
            "xxl": ["xxl", "double extra large", "2xl"],
            "xxxl": ["xxxl", "triple extra large", "3xl"],
            "one_size": ["one size", "free size", "os", "one size fits all"],
        }

        for size_code, size_variants in size_words.items():
            for variant in size_variants:
                if variant in text:
                    tags.add(size_code.upper())
                    tags.add(variant)

        return tags

    @classmethod
    def _extract_colors(cls, text, marketplace_product):
        """Extract color information"""
        tags = set()

        # Add color from model field if exists
        if marketplace_product.color:
            color_display = dict(MarketplaceProduct.ColorChoices.choices).get(marketplace_product.color, "")
            if color_display:
                tags.add(color_display.lower())
            tags.add(marketplace_product.color.lower())

        # Extract colors from text
        common_colors = [
            "red",
            "blue",
            "green",
            "black",
            "white",
            "gray",
            "grey",
            "brown",
            "orange",
            "purple",
            "pink",
            "navy",
            "beige",
            "gold",
            "silver",
            "yellow",
            "maroon",
            "cyan",
            "magenta",
            "violet",
            "indigo",
        ]

        for color in common_colors:
            if color in text:
                tags.add(color)

        return tags

    @classmethod
    def _add_field_tags(cls, product, tags):
        """Add tags from product model fields"""
        # Made in Nepal
        if product.is_made_in_nepal:
            tags.update(["made in nepal", "nepali product", "local made", "desi", "swadeshi", "nepal"])

        # Free delivery
        if product.is_delivery_free:
            tags.update(["free delivery", "free shipping", "no delivery charge", "free home delivery"])

        # B2B
        if product.enable_b2b_sales:
            tags.update(["wholesale", "bulk purchase", "b2b", "business price", "commercial buyer"])

        # Featured
        if product.is_featured:
            tags.add("featured")

        # Made for you
        if product.made_for_you:
            tags.add("personalized")

        # Availability
        if product.is_available:
            tags.add("in stock")
        else:
            tags.add("out of stock")

    @classmethod
    def _add_price_tags(cls, product, tags):
        """Add price-related tags"""
        if product.discounted_price:
            price = product.discounted_price
            discount = product.discount_percentage

            # Price range tags (in NPR)
            if price < 500:
                tags.update(["budget", "affordable", "under 500"])
            elif price < 1000:
                tags.update(["economy", "under 1000", "value pick"])
            elif price < 5000:
                tags.update(["mid range", "affordable premium", "under 5k"])
            elif price < 20000:
                tags.update(["premium", "quality product", "investment"])
            elif price < 50000:
                tags.update(["luxury", "high end", "deluxe"])
            else:
                tags.update(["ultra luxury", "premium segment", "exclusive"])

            # Discount tags
            if discount >= 70:
                tags.update(["mega sale", "clearance", "huge discount", "best deal", "steal deal"])
            elif discount >= 50:
                tags.update(["big sale", "half price", "great discount", "festive offer"])
            elif discount >= 30:
                tags.update(["sale", "discounted", "good offer", "price drop"])
            elif discount >= 10:
                tags.update(["minor discount", "saving deal"])

            # Savings amount
            savings = product.listed_price - price
            if savings > 10000:
                tags.add("massive savings")
            elif savings > 5000:
                tags.add("big savings")
            elif savings > 1000:
                tags.add("good savings")

    @classmethod
    def _add_popularity_tags(cls, product, tags):
        """Add popularity and engagement tags"""
        if product.recent_purchases_count > 100:
            tags.update(["trending", "bestseller", "viral", "hot cake", "high demand"])
        elif product.recent_purchases_count > 50:
            tags.update(["popular", "customer choice", "well selling"])
        elif product.recent_purchases_count > 20:
            tags.update(["selling fast", "good seller", "frequently bought"])
        elif product.recent_purchases_count > 10:
            tags.add("moderate demand")
        elif product.recent_purchases_count > 0:
            tags.add("new selling")

        if product.view_count > 5000:
            tags.add("viral product")
        elif product.view_count > 1000:
            tags.add("highly viewed")
        elif product.view_count > 500:
            tags.add("popular view")

    @classmethod
    def _extract_features(cls, text, category_code):
        """Extract feature-related tags"""
        features = set()

        # Common feature keywords
        feature_keywords = {
            "waterproof": ["waterproof", "water resistant", "splash proof", "rain proof"],
            "durable": ["durable", "long lasting", "sturdy", "heavy duty", "tough"],
            "portable": ["portable", "lightweight", "easy to carry", "compact", "travel friendly"],
            "easy_to_use": ["easy to use", "user friendly", "simple operation", "plug and play"],
            "safety": ["child lock", "safe", "protective", "overload protection", "auto shutoff"],
            "energy_saving": ["energy saving", "power efficient", "eco friendly", "green", "low consumption"],
            "smart_features": ["smart", "intelligent", "auto", "automatic", "programmable", "digital"],
        }

        for feature_category, keywords in feature_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    features.add(keyword)
                    features.add(feature_category.replace("_", " "))

        # Category-specific features
        if category_code == "EG":
            eg_features = ["inverter", "digital display", "remote control", "touch control", "voice control"]
            for feat in eg_features:
                if feat in text:
                    features.add(feat)

        elif category_code == "HL":
            hl_features = ["easy clean", "stain resistant", "scratch resistant", "heat resistant", "foldable"]
            for feat in hl_features:
                if feat in text:
                    features.add(feat)

        return features

    @classmethod
    def _extract_numeric_values(cls, text):
        """Extract numeric values as tags"""
        tags = set()

        # Weight
        weight_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(kg|kilogram|gm|gram|lb|pound)", text)
        for weight, unit in weight_matches:
            tags.add(f"{weight}{unit}")

            weight_float = float(weight)
            if unit in ["kg", "kilogram"]:
                if weight_float < 1:
                    tags.add("light weight")
                elif weight_float < 5:
                    tags.add("medium weight")
                elif weight_float < 10:
                    tags.add("heavy")
                else:
                    tags.add("very heavy")

        # Year/warranty
        year_matches = re.findall(r"(\d+)\s*(year|yr|years|yrs)", text)
        for years, _ in year_matches:
            if int(years) >= 2:
                tags.add(f"{years} year warranty")

        # Quantity
        quantity_matches = re.findall(r"(\d+)\s*(?:pack|set|piece|pc|pcs)", text)
        for qty in quantity_matches:
            if int(qty) > 1:
                tags.add(f"{qty} pack")
                tags.add("multi pack")
            elif int(qty) == 1:
                tags.add("single pack")

        return tags

    @classmethod
    def _clean_tags(cls, tags):
        """Clean and deduplicate tags"""
        cleaned = set()
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "of",
            "to",
            "for",
            "with",
            "on",
            "at",
            "by",
            "in",
            "out",
            "up",
            "down",
            "from",
            "into",
            "upon",
            "via",
        }

        for tag in tags:
            # Clean tag
            tag = tag.lower().strip()
            tag = re.sub(r"[^\w\s-]", "", tag)
            tag = " ".join(tag.split())
            tag = tag.replace("  ", " ")

            # Skip invalid tags
            if len(tag) < 2 or tag in stopwords:
                continue
            if tag.isdigit():
                continue
            if len(tag) > 60:  # Too long
                continue
            if tag in ["nan", "none", "null", "undefined"]:
                continue

            cleaned.add(tag)

        return cleaned

    @classmethod
    def extract_and_save(cls, marketplace_product, save=True):
        """Extract tags and save to database"""
        tags = cls.extract_tags(marketplace_product)

        # Preserve existing tags if any
        existing_tags = set(marketplace_product.search_tags or [])

        # Combine existing and new tags (prioritize new extraction)
        combined_tags = list(set(tags) | existing_tags)

        # Limit to 40 tags
        marketplace_product.search_tags = combined_tags[:40]

        if save:
            marketplace_product.save(update_fields=["search_tags"])

        return marketplace_product.search_tags

    @classmethod
    def bulk_extract(cls, queryset=None, batch_size=100):
        """Bulk extract tags for multiple products"""
        from .models import MarketplaceProduct

        if queryset is None:
            queryset = MarketplaceProduct.objects.select_related("product", "product__category").all()

        updated = 0
        for product in queryset.iterator(chunk_size=batch_size):
            cls.extract_and_save(product, save=True)
            updated += 1

            if updated % batch_size == 0:
                print(f"✅ Processed {updated} products")

        return updated
