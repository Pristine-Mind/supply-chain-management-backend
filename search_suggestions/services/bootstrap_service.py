import hashlib
import json
import logging
import random
from typing import List

from django.db.models import Q
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


class CatalogBootstrapService:
    """
    Creates initial 'Customers Also Searched For' suggestions
    from your existing product catalog
    """

    def __init__(self):
        self.min_cooccurrence = 5
        self.default_ctr = 0.15
        self.redis_client = get_redis_connection("default")

    def warmup_cache(self, limit: int = 100):
        """
        Warm up Redis cache with popular queries
        """
        from ..models import QueryPerformacePopularity
        from ..services.suggestion_service import SearchSuggestionService

        suggestion_service = SearchSuggestionService()

        # Get top popular queries
        popular_queries = QueryPerformacePopularity.objects.filter(total_searches__gte=50).order_by("-total_searches")[
            :limit
        ]

        logger.info(f"Warming up cache for {len(popular_queries)} queries...")

        cached_count = 0
        for query_pop in popular_queries:
            try:
                # Generate suggestions for this query
                suggestions = suggestion_service._generate_suggestions(query_pop.query, user_id=None)

                if suggestions:
                    cache_key = f"search_suggestions:{suggestion_service.get_query_hash(query_pop.query)}"
                    self.redis_client.setex(
                        cache_key, suggestion_service.cache_ttl, json.dumps(suggestions[:5])  # Cache top 5
                    )
                    cached_count += 1

            except Exception as e:
                logger.error(f"Error caching query {query_pop.query}: {e}")

        logger.info(f"Successfully cached {cached_count} queries")
        return cached_count

    def bootstrap_from_catalog(self, force=False):
        """
        Main method to bootstrap all suggestions from catalog
        """
        logger.info("Starting catalog-based bootstrap...")

        # Clear existing data if forcing
        if force:
            from ..models import (
                ManualQueryAssociation,
                QueryAssociation,
                QueryPerformacePopularity,
            )

            QueryAssociation.objects.all().delete()
            QueryPerformacePopularity.objects.all().delete()
            ManualQueryAssociation.objects.all().delete()

        try:
            # 1. Create suggestions from categories
            category_count = self._bootstrap_from_categories()
            logger.info(f"Created {category_count} category-based suggestions")

            # 2. Create suggestions from brands
            brand_count = self._bootstrap_from_brands()
            logger.info(f"Created {brand_count} brand-based suggestions")

            # 3. Create suggestions from product attributes
            attribute_count = self._bootstrap_from_attributes()
            logger.info(f"Created {attribute_count} attribute-based suggestions")

            # 4. Create complementary product suggestions
            complementary_count = self._bootstrap_complementary_products()
            logger.info(f"Created {complementary_count} complementary suggestions")

            # 5. Create manual curated suggestions
            manual_count = self._create_manual_associations()
            logger.info(f"Created {manual_count} manual suggestions")

            # 6. Initialize query popularity
            popularity_count = self._initialize_query_popularity()
            logger.info(f"Initialized {popularity_count} query popularity entries")

            total = category_count + brand_count + attribute_count + complementary_count + manual_count

            logger.info(f"Total suggestions created: {total}")
            return {
                "total_suggestions": total,
                "category": category_count,
                "brand": brand_count,
                "attribute": attribute_count,
                "complementary": complementary_count,
                "manual": manual_count,
                "popularity": popularity_count,
            }

        except Exception as e:
            logger.error(f"Error during bootstrap: {e}")
            raise

    def _bootstrap_from_categories(self) -> int:
        """
        Create suggestions based on your category hierarchy
        """
        from producer.models import Category, Product, Subcategory, SubSubcategory

        from ..models import QueryAssociation, QueryPerformacePopularity

        categories_created = 0

        # Get all categories with products
        categories = Category.objects.filter(is_active=True, product__is_active=True).distinct()

        for category in categories:
            # Generate queries for this category
            category_queries = self._generate_category_queries(category)

            # Create associations between category queries
            associations = []
            for i, query1 in enumerate(category_queries):
                for query2 in category_queries[i + 1 : min(i + 4, len(category_queries))]:
                    associations.append(
                        {
                            "source_query": query1,
                            "source_query_hash": get_query_hash(query1),
                            "target_query": query2,
                            "target_query_hash": get_query_hash(query2),
                            "co_occurrence_count": random.randint(10, 50),
                            "association_type": "category",
                            "confidence_score": 0.8,
                            "decay_score": 1.0,
                            "is_active": True,
                        }
                    )

            if associations:
                QueryAssociation.objects.bulk_create(
                    [QueryAssociation(**data) for data in associations], ignore_conflicts=True
                )
                categories_created += len(associations)

            # Create QueryPerformacePopularity for each query
            for query in category_queries:
                QueryPerformacePopularity.objects.update_or_create(
                    query_hash=get_query_hash(query),
                    defaults={
                        "query": query,
                        "total_searches": random.randint(20, 100),
                        "primary_category": category.name,
                        "detected_categories": [category.name],
                        "click_through_rate": self.default_ctr,
                        "trending_score": random.uniform(0.8, 1.5),
                        "trend_direction": "stable",
                    },
                )

        return categories_created

    def _generate_category_queries(self, category) -> List[str]:
        """Generate search queries for a category"""
        queries = []

        # Basic category name
        category_name = category.name.lower()
        queries.append(category_name)

        # Category with modifiers
        modifiers = [
            "buy",
            "shop",
            "purchase",
            "order",
            "best",
            "top",
            "popular",
            "trending",
            "cheap",
            "affordable",
            "premium",
            "luxury",
            "new",
            "latest",
            "2024",
            "modern",
            "discount",
            "sale",
            "offer",
            "deal",
        ]

        for modifier in modifiers[:6]:  # Take first 6
            queries.append(f"{modifier} {category_name}")
            queries.append(f"{category_name} {modifier}")

        # Category with product types
        product_types = self._get_product_types_for_category(category)
        for product_type in product_types[:5]:
            queries.append(f"{product_type} {category_name}")
            queries.append(f"{category_name} {product_type}")

        # Price range queries
        price_ranges = ["under 1000", "under 5000", "5000-10000", "10000-20000", "above 20000"]
        for price_range in price_ranges[:3]:
            queries.append(f"{category_name} {price_range}")

        return list(set(queries))

    def _get_product_types_for_category(self, category) -> List[str]:
        """Extract product types from products in category"""
        from producer.models import MarketplaceProduct

        # Get product names from this category
        products = MarketplaceProduct.objects.filter(product__category=category, is_available=True).values_list(
            "product__name", flat=True
        )[:50]

        # Extract common words (assume they're product types)
        product_types = set()
        for name in products:
            words = name.lower().split()
            for word in words:
                if len(word) > 3 and not word.isdigit():
                    product_types.add(word)

        return list(product_types)[:10]  # Return top 10

    def _bootstrap_from_brands(self) -> int:
        """
        Create suggestions based on brands
        """
        from producer.models import Brand, Product

        from ..models import QueryAssociation, QueryPerformacePopularity

        brands_created = 0

        # Get active brands with products
        brands = Brand.objects.filter(is_active=True, products__is_active=True).distinct()[:100]  # Limit to top 100 brands

        for brand in brands:
            # Generate brand queries
            brand_queries = self._generate_brand_queries(brand)

            # Create brand-category associations
            if brand.category:
                category_queries = self._generate_category_queries(brand.category)

                associations = []
                for brand_query in brand_queries[:3]:  # Top 3 brand queries
                    for category_query in category_queries[:5]:  # Top 5 category queries
                        associations.append(
                            {
                                "source_query": brand_query,
                                "source_query_hash": get_query_hash(brand_query),
                                "target_query": category_query,
                                "target_query_hash": get_query_hash(category_query),
                                "co_occurrence_count": random.randint(5, 30),
                                "association_type": "brand",
                                "confidence_score": 0.7,
                                "decay_score": 1.0,
                                "is_active": True,
                            }
                        )

                if associations:
                    QueryAssociation.objects.bulk_create(
                        [QueryAssociation(**data) for data in associations], ignore_conflicts=True
                    )
                    brands_created += len(associations)

            # Create QueryPerformacePopularity for brand queries
            for query in brand_queries:
                QueryPerformacePopularity.objects.update_or_create(
                    query_hash=get_query_hash(query),
                    defaults={
                        "query": query,
                        "total_searches": random.randint(30, 150),
                        "primary_category": brand.category.name if brand.category else None,
                        "detected_categories": [brand.category.name] if brand.category else [],
                        "click_through_rate": self.default_ctr,
                        "trending_score": random.uniform(0.9, 1.8),
                        "trend_direction": "stable",
                    },
                )

        return brands_created

    def _generate_brand_queries(self, brand) -> List[str]:
        """Generate search queries for a brand"""
        queries = []
        brand_name = brand.name.lower()

        # Basic brand queries
        queries.append(brand_name)
        queries.append(f"{brand_name} products")
        queries.append(f"buy {brand_name}")
        queries.append(f"{brand_name} online")

        # Brand with quality indicators
        quality_words = ["original", "authentic", "genuine", "official"]
        for quality in quality_words:
            queries.append(f"{quality} {brand_name}")

        # Brand with product categories
        if brand.category:
            category_name = brand.category.name.lower()
            queries.append(f"{brand_name} {category_name}")
            queries.append(f"{category_name} {brand_name}")

            # With modifiers
            modifiers = ["best", "new", "cheap", "premium"]
            for modifier in modifiers:
                queries.append(f"{modifier} {brand_name} {category_name}")

        # Brand comparisons
        competitor_brands = self._get_competitor_brands(brand)
        for competitor in competitor_brands[:3]:
            queries.append(f"{brand_name} vs {competitor}")

        return list(set(queries))

    def _get_competitor_brands(self, brand) -> List[str]:
        """Find competitor brands in same category"""
        from producer.models import Brand

        if not brand.category:
            return []

        competitors = (
            Brand.objects.filter(category=brand.category, is_active=True)
            .exclude(id=brand.id)
            .values_list("name", flat=True)[:5]
        )

        return [name.lower() for name in competitors]

    def _bootstrap_from_attributes(self) -> int:
        """
        Create suggestions based on product attributes (size, color)
        """
        from producer.models import MarketplaceProduct

        from ..models import QueryAssociation

        attributes_created = 0

        # Get products with attributes
        products = MarketplaceProduct.objects.filter(
            Q(product__size__isnull=False) | Q(product__color__isnull=False),
            is_available=True,
        )[:200]

        # Group by category and create attribute associations
        category_attributes = {}

        for product in products:
            if not product.product.category:
                continue

            category_name = product.product.category.name
            if category_name not in category_attributes:
                category_attributes[category_name] = {"sizes": set(), "colors": set()}

            if product.product.size:
                category_attributes[category_name]["sizes"].add(product.product.size)
            if product.product.color:
                category_attributes[category_name]["colors"].add(product.product.color)

        # Create associations between sizes and colors within categories
        associations = []

        for category_name, attributes in category_attributes.items():
            sizes = list(attributes["sizes"])
            colors = list(attributes["colors"])

            # Create size-size associations
            for i, size1 in enumerate(sizes):
                for size2 in sizes[i + 1 : min(i + 3, len(sizes))]:
                    query1 = f"{size1.lower()} {category_name.lower()}"
                    query2 = f"{size2.lower()} {category_name.lower()}"

                    associations.append(
                        {
                            "source_query": query1,
                            "source_query_hash": get_query_hash(query1),
                            "target_query": query2,
                            "target_query_hash": get_query_hash(query2),
                            "co_occurrence_count": random.randint(5, 20),
                            "association_type": "attribute",
                            "confidence_score": 0.6,
                            "decay_score": 1.0,
                            "is_active": True,
                        }
                    )

            # Create color-color associations
            for i, color1 in enumerate(colors):
                for color2 in colors[i + 1 : min(i + 3, len(colors))]:
                    query1 = f"{color1.lower()} {category_name.lower()}"
                    query2 = f"{color2.lower()} {category_name.lower()}"

                    associations.append(
                        {
                            "source_query": query1,
                            "source_query_hash": get_query_hash(query1),
                            "target_query": query2,
                            "target_query_hash": get_query_hash(query2),
                            "co_occurrence_count": random.randint(5, 20),
                            "association_type": "attribute",
                            "confidence_score": 0.6,
                            "decay_score": 1.0,
                            "is_active": True,
                        }
                    )

            # Create size-color cross associations
            for size in sizes[:3]:
                for color in colors[:3]:
                    query1 = f"{size.lower()} {category_name.lower()}"
                    query2 = f"{color.lower()} {category_name.lower()}"

                    associations.append(
                        {
                            "source_query": query1,
                            "source_query_hash": get_query_hash(query1),
                            "target_query": query2,
                            "target_query_hash": get_query_hash(query2),
                            "co_occurrence_count": random.randint(3, 15),
                            "association_type": "attribute",
                            "confidence_score": 0.5,
                            "decay_score": 1.0,
                            "is_active": True,
                        }
                    )

        if associations:
            QueryAssociation.objects.bulk_create([QueryAssociation(**data) for data in associations], ignore_conflicts=True)
            attributes_created = len(associations)

        return attributes_created

    def _bootstrap_complementary_products(self) -> int:
        """
        Create complementary product suggestions
        Based on common e-commerce patterns
        """
        from ..models import QueryAssociation, QueryPerformacePopularity

        # Define complementary pairs (source -> target)
        complementary_pairs = [
            # Electronics
            ("iphone", "iphone case"),
            ("iphone", "airpods"),
            ("samsung phone", "samsung case"),
            ("laptop", "laptop bag"),
            ("laptop", "wireless mouse"),
            ("tv", "tv stand"),
            ("tv", "soundbar"),
            ("camera", "memory card"),
            ("camera", "camera bag"),
            ("gaming console", "games"),
            ("headphones", "headphone stand"),
            # Fashion
            ("shirt", "tie"),
            ("suit", "belt"),
            ("dress", "heels"),
            ("jeans", "belt"),
            ("running shoes", "sports socks"),
            ("watch", "watch strap"),
            ("sunglasses", "sunglasses case"),
            ("handbag", "wallet"),
            # Home & Kitchen
            ("coffee maker", "coffee beans"),
            ("blender", "smoothie cups"),
            ("air fryer", "cooking oil"),
            ("bed", "mattress"),
            ("sofa", "cushions"),
            ("dining table", "chairs"),
            ("refrigerator", "water filter"),
            ("washing machine", "detergent"),
            # Beauty & Personal Care
            ("shampoo", "conditioner"),
            ("razor", "shaving cream"),
            ("toothbrush", "toothpaste"),
            ("perfume", "body lotion"),
            ("makeup", "makeup brushes"),
            # Sports & Fitness
            ("yoga mat", "yoga blocks"),
            ("dumbbells", "weight bench"),
            ("bicycle", "bicycle helmet"),
            ("tent", "sleeping bag"),
            ("running shoes", "fitness tracker"),
        ]

        associations = []

        for source, target in complementary_pairs:
            # Create bidirectional associations
            for source_query, target_query in [(source, target), (target, source)]:
                associations.append(
                    {
                        "source_query": source_query,
                        "source_query_hash": get_query_hash(source_query),
                        "target_query": target_query,
                        "target_query_hash": get_query_hash(target_query),
                        "co_occurrence_count": random.randint(15, 60),
                        "association_type": "complementary",
                        "confidence_score": 0.75,
                        "decay_score": 1.0,
                        "is_active": True,
                    }
                )

                # Also create popularity entries
                QueryPerformacePopularity.objects.update_or_create(
                    query_hash=get_query_hash(source_query),
                    defaults={
                        "query": source_query,
                        "total_searches": random.randint(50, 200),
                        "click_through_rate": random.uniform(0.1, 0.3),
                        "trending_score": random.uniform(1.0, 2.0),
                        "trend_direction": "stable",
                    },
                )

        if associations:
            QueryAssociation.objects.bulk_create([QueryAssociation(**data) for data in associations], ignore_conflicts=True)

        return len(associations)

    def _create_manual_associations(self) -> int:
        """
        Create manually curated associations for important relationships
        """
        from ..models import ManualQueryAssociation

        manual_associations = [
            # Synonyms
            {
                "source_query": "cell phone",
                "target_query": "mobile phone",
                "relationship_type": "synonym",
                "strength": 9.0,
                "description": "Common synonym in different regions",
            },
            {
                "source_query": "sneakers",
                "target_query": "running shoes",
                "relationship_type": "synonym",
                "strength": 8.0,
                "description": "Commonly used interchangeably",
            },
            # Upsells
            {
                "source_query": "basic phone",
                "target_query": "smartphone",
                "relationship_type": "upsell",
                "strength": 7.0,
                "description": "Upsell opportunity",
            },
            {
                "source_query": "standard tv",
                "target_query": "smart tv",
                "relationship_type": "upsell",
                "strength": 6.5,
                "description": "Upgrade to smart features",
            },
            # Cross-sells
            {
                "source_query": "laptop",
                "target_query": "laptop cooling pad",
                "relationship_type": "cross_sell",
                "strength": 8.0,
                "description": "Frequently bought together",
            },
            {
                "source_query": "coffee",
                "target_query": "coffee mug",
                "relationship_type": "cross_sell",
                "strength": 7.5,
                "description": "Natural combination",
            },
            # Alternatives
            {
                "source_query": "expensive watch",
                "target_query": "affordable watch",
                "relationship_type": "alternative",
                "strength": 6.0,
                "min_price": 10000,
                "max_price": 5000,
                "description": "Budget alternative",
            },
            {
                "source_query": "winter jacket",
                "target_query": "rain jacket",
                "relationship_type": "alternative",
                "strength": 5.5,
                "description": "Seasonal alternative",
            },
        ]

        created_count = 0
        for data in manual_associations:
            _, created = ManualQueryAssociation.objects.update_or_create(
                source_query=data["source_query"], target_query=data["target_query"], defaults=data
            )
            if created:
                created_count += 1

        return created_count

    def _initialize_query_popularity(self) -> int:
        """
        Initialize QueryPerformacePopularity for common queries
        """
        from ..models import QueryAssociation, QueryPerformacePopularity

        # Get all unique queries from associations
        all_queries = set()

        # From QueryAssociation
        all_queries.update(QueryAssociation.objects.values_list("source_query", flat=True).distinct())
        all_queries.update(QueryAssociation.objects.values_list("target_query", flat=True).distinct())

        # From ManualQueryAssociation
        from ..models import ManualQueryAssociation

        all_queries.update(ManualQueryAssociation.objects.values_list("source_query", flat=True).distinct())
        all_queries.update(ManualQueryAssociation.objects.values_list("target_query", flat=True).distinct())

        # Create/update QueryPerformacePopularity for each
        created_count = 0
        for query in all_queries:
            if query:  # Skip empty strings
                _, created = QueryPerformacePopularity.objects.update_or_create(
                    query_hash=get_query_hash(query),
                    defaults={
                        "query": query,
                        "total_searches": random.randint(10, 100),
                        "unique_users": random.randint(5, 50),
                        "click_through_rate": random.uniform(0.05, 0.25),
                        "trending_score": random.uniform(0.5, 1.5),
                        "trend_direction": random.choice(["up", "stable", "down"]),
                    },
                )
                if created:
                    created_count += 1

        return created_count


def get_query_hash(query):
    """Generate consistent hash for query"""
    normalized = normalize_query(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def normalize_query(query):
    """Normalize search query"""
    import re

    if not query:
        return ""
    normalized = query.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\s\-\.]", "", normalized)
    return normalized
