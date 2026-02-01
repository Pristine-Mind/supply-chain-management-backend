import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from django.core.cache import cache
from django.db.models import Q

logger = logging.getLogger(__name__)


try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


@dataclass
class SearchQuery:
    """Represents a parsed search query"""

    original_query: str
    normalized_query: str
    intent: str  # 'product_search', 'comparison', 'question', etc.
    entities: Dict[str, Any] = field(default_factory=dict)
    expanded_queries: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


class QueryUnderstandingService:
    """
    Understands natural language search queries.
    Extracts intent, entities, and generates query variations.
    """

    def __init__(self, use_openai: bool = False):
        self.use_openai = use_openai and OPENAI_AVAILABLE
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        if self.use_openai and not self.openai_api_key:
            logger.warning("OpenAI API key not set. Disabling LLM features.")
            self.use_openai = False

    def parse_query(self, query: str) -> SearchQuery:
        """
        Parse a natural language query.
        Uses LLM if available, otherwise uses rule-based parsing.
        """
        if self.use_openai:
            return self._parse_with_llm(query)
        else:
            return self._parse_rule_based(query)

    def _parse_with_llm(self, query: str) -> SearchQuery:
        """Parse query using OpenAI API"""
        try:
            import openai

            openai.api_key = ""

            prompt = f"""
            Analyze this e-commerce search query and extract information in JSON format:

            Query: "{query}"

            Extract:
            1. intent: One of [product_search, comparison, question, navigation]
            2. entities:
               - product_types: list of product types mentioned
               - brands: list of brand names
               - attributes: dict of attributes (color, size, material, etc.)
               - price_constraints: any price mentions (budget, premium, under RsX, etc.)
               - use_cases: intended use cases (gift, office, outdoor, etc.)
            3. expanded_queries: 2-3 alternative ways to express this search
            4. keywords: list of important search terms

            Return valid JSON only.
            """

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful e-commerce search assistant.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )

            result = json.loads(response.choices[0].message.content)

            return SearchQuery(
                original_query=query,
                normalized_query=query.lower().strip(),
                intent=result.get("intent", "product_search"),
                entities=result.get("entities", {}),
                expanded_queries=result.get("expanded_queries", [query]),
                keywords=result.get("keywords", self._extract_keywords(query)),
            )

        except Exception as e:
            logger.error(f"LLM parsing failed: {e}")
            return self._parse_rule_based(query)

    def _parse_rule_based(self, query: str) -> SearchQuery:
        """Parse query using rules and patterns"""
        query_lower = query.lower().strip()

        # Detect intent
        if any(word in query_lower for word in ["vs", "versus", "compare", "difference", "better"]):
            intent = "comparison"
        elif any(word in query_lower for word in ["what", "how", "why", "when", "which"]):
            intent = "question"
        elif any(word in query_lower for word in ["cheap", "expensive", "price"]):
            intent = "price_search"
        else:
            intent = "product_search"

        # Extract entities
        entities = self._extract_entities_rule_based(query_lower)

        # Extract keywords
        keywords = self._extract_keywords(query_lower)

        # Generate expanded queries
        expanded = self._generate_expanded_queries(query_lower, entities)

        return SearchQuery(
            original_query=query,
            normalized_query=query_lower,
            intent=intent,
            entities=entities,
            expanded_queries=expanded,
            keywords=keywords,
        )

    def _extract_entities_rule_based(self, query: str) -> Dict:
        """Extract entities using keyword matching"""
        entities = {
            "brands": [],
            "colors": [],
            "sizes": [],
            "materials": [],
            "price_constraints": {},
            "use_cases": [],
        }

        # Color extraction
        colors = [
            "red",
            "blue",
            "green",
            "black",
            "white",
            "yellow",
            "pink",
            "purple",
            "orange",
            "grey",
            "gray",
            "brown",
            "silver",
            "gold",
            "navy",
            "beige",
        ]
        for color in colors:
            if color in query:
                entities["colors"].append(color)

        # Size extraction
        sizes = [
            "small",
            "medium",
            "large",
            "xl",
            "xxl",
            "xs",
            "extra large",
            "compact",
            "mini",
            "big",
        ]
        for size in sizes:
            if size in query:
                entities["sizes"].append(size)

        # Material extraction
        materials = [
            "cotton",
            "leather",
            "plastic",
            "metal",
            "wood",
            "glass",
            "silicone",
            "rubber",
            "fabric",
            "steel",
        ]
        for material in materials:
            if material in query:
                entities["materials"].append(material)

        # Price constraints
        price_patterns = [
            (r"under\s+(?:rs\.?\s*)?(\d+)", "max"),
            (r"below\s+(?:rs\.?\s*)?(\d+)", "max"),
            (r"less\s+than\s+(?:rs\.?\s*)?(\d+)", "max"),
            (r"over\s+(?:rs\.?\s*)?(\d+)", "min"),
            (r"above\s+(?:rs\.?\s*)?(\d+)", "min"),
            (r"between\s+(?:rs\.?\s*)?(\d+)\s+and\s+(?:rs\.?\s*)?(\d+)", "range"),
        ]

        for pattern, constraint_type in price_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                if constraint_type == "range":
                    entities["price_constraints"] = {
                        "min": int(match.group(1)),
                        "max": int(match.group(2)),
                    }
                else:
                    entities["price_constraints"][constraint_type] = int(match.group(1))
                break

        # Price descriptors
        if "cheap" in query or "budget" in query or "affordable" in query:
            entities["price_constraints"]["descriptor"] = "budget"
        elif "premium" in query or "luxury" in query or "high-end" in query:
            entities["price_constraints"]["descriptor"] = "premium"

        # Use cases
        use_cases = {
            "gift": ["gift", "present", "birthday", "anniversary"],
            "office": ["office", "work", "desk", "professional", "business"],
            "outdoor": ["outdoor", "camping", "hiking", "sports", "travel"],
            "home": ["home", "kitchen", "bedroom", "living room", "house"],
            "study": ["study", "student", "school", "college", "learning"],
        }

        for use_case, keywords in use_cases.items():
            if any(kw in query for kw in keywords):
                entities["use_cases"].append(use_case)

        return entities

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query"""
        # Remove common stop words
        stop_words = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "and",
            "but",
            "or",
            "yet",
            "so",
            "if",
            "because",
            "although",
            "though",
            "while",
            "where",
            "when",
            "that",
            "which",
            "who",
            "whom",
            "whose",
            "what",
            "this",
            "these",
            "those",
            "i",
            "me",
            "my",
            "myself",
            "we",
            "our",
            "you",
            "your",
            "he",
            "him",
            "his",
            "she",
            "her",
            "it",
            "its",
            "they",
            "them",
            "their",
        }

        words = query.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return keywords

    def _generate_expanded_queries(self, query: str, entities: Dict) -> List[str]:
        """Generate query variations"""
        expanded = [query]

        # Add variations based on entities
        if entities["use_cases"]:
            for use_case in entities["use_cases"]:
                if use_case not in query:
                    expanded.append(f"{query} for {use_case}")

        # Add variations without descriptive words
        descriptive_words = [
            "best",
            "top",
            "quality",
            "good",
            "nice",
            "great",
            "cheap",
            "affordable",
            "looking",
            "searching",
            "want",
            "need",
        ]
        simplified = query
        for word in descriptive_words:
            simplified = simplified.replace(word, "").strip()
        if simplified and simplified != query and len(simplified) > 5:
            expanded.append(simplified)

        return list(set(expanded))[:3]


class SemanticSearchService:
    """
    Enhanced product search with query understanding.
    Uses keyword-based search with relevance scoring (no ML embeddings).
    """

    def __init__(self):
        self.query_service = QueryUnderstandingService(use_openai=os.getenv("USE_OPENAI_LLM", "false").lower() == "true")

    def search(
        self,
        query: str,
        k: int = 20,
        filters: Optional[Dict] = None,
        queryset=None,
    ) -> Dict:
        """
        Perform enhanced search with query understanding.

        Args:
            query: Search query string
            k: Number of results to return
            filters: Optional filters to apply
            queryset: Optional base queryset

        Returns:
            Dictionary with results and metadata
        """
        from producer.models import MarketplaceProduct

        # Parse and understand query
        parsed_query = self.query_service.parse_query(query)

        # Get base queryset
        if queryset is None:
            queryset = MarketplaceProduct.objects.filter(is_available=True)

        # Perform enhanced keyword search
        results = self._enhanced_keyword_search(parsed_query, queryset, k)

        # Apply additional filters
        if filters:
            results = self._apply_filters(results, filters)

        return {
            "query": parsed_query.original_query,
            "parsed_query": {
                "intent": parsed_query.intent,
                "entities": parsed_query.entities,
                "keywords": parsed_query.keywords,
                "expanded_queries": parsed_query.expanded_queries,
            },
            "results": results[:k],
            "total_found": len(results),
            "search_method": "enhanced_keyword",
        }

    def _enhanced_keyword_search(self, parsed_query: SearchQuery, queryset, k: int) -> List[Dict]:
        """Perform keyword-based search with relevance scoring"""
        queries = [parsed_query.normalized_query] + parsed_query.expanded_queries
        keywords = parsed_query.keywords
        entities = parsed_query.entities

        results = []
        seen_ids = set()

        for search_query in queries:
            # Build Q objects for multiple field search
            q_objects = Q()

            # Search in product name (highest weight)
            q_objects |= Q(product__name__icontains=search_query)

            # Search in description
            q_objects |= Q(product__description__icontains=search_query)

            # Search in tags
            q_objects |= Q(search_tags__icontains=search_query)

            # Search in brand
            q_objects |= Q(product__brand__name__icontains=search_query)

            # Search in additional info
            q_objects |= Q(additional_information__icontains=search_query)

            # Execute query
            matches = queryset.filter(q_objects).distinct()

            # Score and rank each match
            for product in matches:
                if product.id in seen_ids:
                    continue

                score = self._calculate_relevance_score(product, search_query, keywords, entities)

                results.append(
                    {
                        "product_id": product.id,
                        "product": product,
                        "relevance_score": round(score, 4),
                        "semantic_score": 0.0,  # Not using embeddings
                        "keyword_score": round(score, 4),
                        "match_type": self._determine_match_type(score),
                    }
                )

                seen_ids.add(product.id)

        # Sort by relevance score
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

        return results

    def _calculate_relevance_score(self, product, query: str, keywords: List[str], entities: Dict) -> float:
        """Calculate relevance score based on multiple factors"""
        score = 0.0
        query_lower = query.lower()
        product_name = product.product.name.lower() if product.product else ""
        description = product.product.description.lower() if product.product and product.product.description else ""

        # Exact match in name (highest score)
        if query_lower == product_name:
            score += 1.0
        elif query_lower in product_name:
            score += 0.8
        elif any(kw in product_name for kw in keywords):
            score += 0.6

        # Partial matches
        name_words = product_name.split()
        query_words = query_lower.split()
        matching_words = sum(1 for w in query_words if w in name_words)
        if name_words:
            score += (matching_words / len(name_words)) * 0.4

        # Description match
        if query_lower in description:
            score += 0.3
        elif any(kw in description for kw in keywords):
            score += 0.2

        # Entity matching boosts
        if entities["colors"]:
            product_color = (product.color or "").lower()
            base_color = (product.product.color if product.product else "").lower()
            if any(c in product_color or c in base_color for c in entities["colors"]):
                score += 0.15

        if entities["sizes"]:
            product_size = (product.size or "").lower()
            base_size = (product.product.size if product.product else "").lower()
            if any(s in product_size or s in base_size for s in entities["sizes"]):
                score += 0.15

        if entities.get("brands"):
            brand_name = product.product.brand.name.lower() if product.product and product.product.brand else ""
            if any(b.lower() in brand_name for b in entities["brands"]):
                score += 0.2

        # Use case matching
        if entities["use_cases"]:
            searchable_text = f"{product_name} {description} {product.additional_information or ''}".lower()
            use_case_keywords = {
                "gift": ["gift", "present", "giftable", "gifting"],
                "office": ["office", "work", "desk", "professional"],
                "outdoor": ["outdoor", "camping", "sports", "travel"],
                "home": ["home", "kitchen", "bedroom", "house"],
            }
            for use_case in entities["use_cases"]:
                keywords = use_case_keywords.get(use_case, [use_case])
                if any(kw in searchable_text for kw in keywords):
                    score += 0.1

        return min(score, 1.0)

    def _apply_filters(self, results: List[Dict], filters: Dict) -> List[Dict]:
        """Apply additional filters to results"""
        filtered = results

        if "category_id" in filters:
            filtered = [
                r
                for r in filtered
                if (r["product"].product.category_id == filters["category_id"] if r["product"].product else False)
            ]

        if "brand_id" in filters:
            filtered = [
                r
                for r in filtered
                if (r["product"].product.brand_id == filters["brand_id"] if r["product"].product else False)
            ]

        if "min_price" in filters:
            filtered = [r for r in filtered if r["product"].listed_price >= filters["min_price"]]

        if "max_price" in filters:
            filtered = [r for r in filtered if r["product"].listed_price <= filters["max_price"]]

        if filters.get("in_stock"):
            filtered = [r for r in filtered if r["product"].product and r["product"].product.stock > 0]

        return filtered

    def _determine_match_type(self, score: float) -> str:
        """Determine the type of match based on score"""
        if score >= 0.8:
            return "excellent"
        elif score >= 0.6:
            return "good"
        elif score >= 0.4:
            return "fair"
        elif score > 0:
            return "weak"
        else:
            return "none"

    def get_similar_products(self, product_id: int, k: int = 10) -> List[Dict]:
        """Find products similar to a given product using category and attributes"""
        from producer.models import MarketplaceProduct

        try:
            product = MarketplaceProduct.objects.select_related("product", "product__category", "product__brand").get(
                id=product_id
            )
        except MarketplaceProduct.DoesNotExist:
            return []

        # Find similar products based on category and attributes
        similar = MarketplaceProduct.objects.filter(is_available=True).select_related(
            "product", "product__category", "product__brand"
        )

        # Same category is strongest signal
        if product.product and product.product.category:
            similar = similar.filter(product__category=product.product.category).exclude(id=product_id)

        results = []
        for p in similar[: k * 2]:
            score = self._calculate_similarity_score(product, p)
            if score > 0:
                results.append(
                    {
                        "product_id": p.id,
                        "product": p,
                        "similarity_score": round(score, 4),
                    }
                )

        # Sort by similarity and return top k
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:k]

    def _calculate_similarity_score(self, product1, product2) -> float:
        """Calculate similarity score between two products"""
        score = 0.0

        p1 = product1.product if product1.product else None
        p2 = product2.product if product2.product else None

        if not p1 or not p2:
            return score

        # Same category
        if p1.category and p1.category == p2.category:
            score += 0.4

        # Same subcategory
        if p1.subcategory and p1.subcategory == p2.subcategory:
            score += 0.2

        # Same brand
        if p1.brand and p1.brand == p2.brand:
            score += 0.15

        # Same size
        if product1.size and product1.size == product2.size:
            score += 0.1
        elif p1.size and p1.size == p2.size:
            score += 0.1

        # Same color
        if product1.color and product1.color == product2.color:
            score += 0.1
        elif p1.color and p1.color == p2.color:
            score += 0.1

        # Similar price range (within 20%)
        if product1.listed_price > 0 and product2.listed_price > 0:
            price_ratio = min(product1.listed_price, product2.listed_price) / max(
                product1.listed_price, product2.listed_price
            )
            if price_ratio >= 0.8:
                score += 0.1
            elif price_ratio >= 0.5:
                score += 0.05

        return score


# Global instance for reuse
_semantic_search_service = None


def get_semantic_search_service():
    """Get or create the semantic search service singleton"""
    global _semantic_search_service
    if _semantic_search_service is None:
        _semantic_search_service = SemanticSearchService()
    return _semantic_search_service
