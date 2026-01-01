import json
import logging
import random
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import redis
from django.db.models import Count, F, Q, Value
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


class SearchSuggestionService:
    """
    Main service for generating 'Customers Also Searched For' suggestions
    """

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=1):
        self.redis_client = get_redis_connection("default")
        self.cache_ttl = 3600  # 1 hour
        self.min_cooccurrence = 3
        self.max_suggestions = 10

    def get_suggestions(
        self, query: str, user_id: Optional[str] = None, limit: int = 5, use_cache: bool = True
    ) -> List[Dict]:
        """
        Get suggestions for a search query
        """
        try:
            # Normalize query
            normalized_query = self.normalize_query(query)
            if len(normalized_query) < 2:
                return []

            # Check cache
            cache_key = f"search_suggestions:{self.get_query_hash(normalized_query)}"
            if use_cache:
                cached = self.redis_client.get(cache_key)
                if cached:
                    suggestions = json.loads(cached)
                    # Update cache hit stats using pipeline
                    pipeline = self.redis_client.pipeline()
                    pipeline.zincrby("suggestion_cache:hits", 1, cache_key)
                    pipeline.expire("suggestion_cache:hits", 86400)  # 1 day
                    pipeline.execute()
                    return suggestions[:limit]

            # Generate fresh suggestions
            suggestions = self._generate_suggestions(normalized_query, user_id)

            # Cache results
            if use_cache and suggestions:
                self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(suggestions))

            return suggestions[:limit]

        except Exception as e:
            logger.error(f"Error getting suggestions for '{query}': {e}")
            return self._get_fallback_suggestions(query, limit)

    def _generate_suggestions(self, query: str, user_id: Optional[str] = None) -> List[Dict]:
        """
        Generate suggestions using multiple strategies
        """
        from ..models import (
            ManualQueryAssociation,
            QueryAssociation,
            QueryPerformacePopularity,
        )

        all_suggestions = {}

        # 1. Get co-search suggestions (main algorithm)
        co_search_suggestions = self._get_co_search_suggestions(query)
        self._merge_suggestions(all_suggestions, co_search_suggestions, weight=1.0)

        # 2. Get manual associations (high priority)
        manual_suggestions = self._get_manual_suggestions(query)
        self._merge_suggestions(all_suggestions, manual_suggestions, weight=1.5)

        # 3. Get category-based suggestions
        category_suggestions = self._get_category_suggestions(query)
        self._merge_suggestions(all_suggestions, category_suggestions, weight=0.8)

        # 4. Get attribute-based suggestions
        attribute_suggestions = self._get_attribute_suggestions(query)
        self._merge_suggestions(all_suggestions, attribute_suggestions, weight=0.7)

        # 5. Get complementary product suggestions
        complementary_suggestions = self._get_complementary_suggestions(query)
        self._merge_suggestions(all_suggestions, complementary_suggestions, weight=0.9)

        # 6. Add trending queries if we need more suggestions
        if len(all_suggestions) < 3:
            trending_suggestions = self._get_trending_suggestions(query)
            self._merge_suggestions(all_suggestions, trending_suggestions, weight=0.5)

        # Convert to list and sort
        suggestions_list = []
        for query_text, data in all_suggestions.items():
            suggestions_list.append(
                {
                    "query": query_text,
                    "score": data["score"],
                    "type": data["type"],
                    "confidence": data.get("confidence", 0.5),
                    "reason": data.get("reason", "customers_also_searched"),
                    "metrics": data.get("metrics", {}),
                }
            )

        # Sort by score descending
        suggestions_list.sort(key=lambda x: x["score"], reverse=True)

        # Attach marketplace product id where possible to allow frontend deep-links
        try:
            self._attach_product_ids(suggestions_list)
        except Exception:
            logger.exception("Failed to attach product ids to suggestions")

        return suggestions_list

    def _attach_product_ids(self, suggestions_list: List[Dict]):
        """Try to attach a MarketplaceProduct id for each suggestion if a good match exists."""
        try:
            from producer.models import MarketplaceProduct
        except Exception:
            return
        import re

        for suggestion in suggestions_list:
            if suggestion.get("product_id"):
                continue

            query_text = (suggestion.get("query") or "").strip()
            if not query_text:
                continue

            # 1) Try exact phrase match on product name/description
            mp = (
                MarketplaceProduct.objects.filter(
                    (Q(product__name__icontains=query_text) | Q(product__description__icontains=query_text)),
                    is_available=True,
                )
                .only("id")
                .first()
            )
            if mp:
                suggestion["product_id"] = mp.id
                continue

            # 2) Tokenized AND match (all significant tokens must appear)
            tokens = [t for t in re.findall(r"\w+", query_text.lower()) if len(t) > 2]
            if tokens:
                q_and = Q()
                for t in tokens:
                    q_and &= (Q(product__name__icontains=t) | Q(product__description__icontains=t))

                mp = MarketplaceProduct.objects.filter(q_and, is_available=True).only("id").first()
                if mp:
                    suggestion["product_id"] = mp.id
                    continue

            # 3) Fallback: match any token (prefer products matching more tokens could be optimized later)
            if tokens:
                q_or = Q()
                for t in tokens[:4]:
                    q_or |= (Q(product__name__icontains=t) | Q(product__description__icontains=t))

                mp = MarketplaceProduct.objects.filter(q_or, is_available=True).only("id").first()
                if mp:
                    suggestion["product_id"] = mp.id

    def _get_co_search_suggestions(self, query: str) -> List[Dict]:
        """
        Get queries that are frequently searched together
        """
        from ..models import QueryAssociation

        query_hash = self.get_query_hash(query)

        associations = (
            QueryAssociation.objects.filter(
                source_query_hash=query_hash, is_active=True, co_occurrence_count__gte=self.min_cooccurrence
            )
            .select_related()
            .order_by("-co_occurrence_count", "-confidence_score")[:20]
        )

        suggestions = []
        for assoc in associations:
            score = self._calculate_association_score(assoc)
            suggestions.append(
                {
                    "query": assoc.target_query,
                    "score": score,
                    "type": "co_search",
                    "confidence": assoc.confidence_score,
                    "reason": "frequently_searched_together",
                    "metrics": {
                        "co_occurrence": assoc.co_occurrence_count,
                        "ctr": assoc.source_to_target_ctr,
                        "conversion": assoc.conversion_rate,
                    },
                }
            )

        return suggestions

    def _get_manual_suggestions(self, query: str) -> List[Dict]:
        """
        Get manually curated suggestions
        """
        from ..models import ManualQueryAssociation

        manual_associations = ManualQueryAssociation.objects.filter(
            Q(source_query=query) | Q(source_query__icontains=query), is_active=True
        ).order_by("-priority", "-strength")[:10]

        suggestions = []
        for manual in manual_associations:
            suggestions.append(
                {
                    "query": manual.target_query,
                    "score": manual.strength * 10,  # Convert to score scale
                    "type": "manual",
                    "confidence": min(manual.strength / 10, 1.0),
                    "reason": manual.relationship_type,
                    "metrics": {"strength": manual.strength, "priority": manual.priority, "description": manual.description},
                }
            )

        return suggestions

    def _get_category_suggestions(self, query: str) -> List[Dict]:
        """
        Get suggestions based on category matching
        """
        from producer.models import Category

        from ..models import QueryPerformacePopularity

        suggestions = []

        # Try to find category for this query
        try:
            # Check if query contains category names
            categories = Category.objects.filter(Q(name__icontains=query) | Q(code__icontains=query))[:3]

            if not categories:
                # Try to find by query popularity
                popularity = QueryPerformacePopularity.objects.filter(query__icontains=query).first()

                if popularity and popularity.primary_category:
                    categories = Category.objects.filter(name__icontains=popularity.primary_category)[:3]

            for category in categories:
                # Get other popular queries in same category
                category_queries = (
                    QueryPerformacePopularity.objects.filter(
                        Q(primary_category__icontains=category.name) | Q(detected_categories__contains=[category.name]),
                        query__icontains=query[:3] if len(query) > 3 else query,  # Partial match
                    )
                    .exclude(query=query)
                    .order_by("-total_searches", "-trending_score")[:5]
                )

                for cat_query in category_queries:
                    score = self._calculate_category_score(cat_query, query)
                    suggestions.append(
                        {
                            "query": cat_query.query,
                            "score": score,
                            "type": "category",
                            "confidence": 0.6,
                            "reason": f"same_category_{category.name}",
                            "metrics": {
                                "category": category.name,
                                "popularity": cat_query.total_searches,
                                "trending": cat_query.trending_score,
                            },
                        }
                    )
        except Exception as e:
            logger.debug(f"Error in category suggestions: {e}")

        return suggestions

    def _get_attribute_suggestions(self, query: str) -> List[Dict]:
        """
        Get suggestions based on size/color attributes
        """
        from producer.models import Product, MarketplaceProduct

        suggestions = []

        # Check for size/color keywords
        size_keywords = {"xs", "s", "small", "m", "medium", "l", "large", "xl", "xxl", "xxxl", "size", "extra"}
        color_keywords = {
            "red",
            "blue",
            "green",
            "yellow",
            "black",
            "white",
            "gray",
            "brown",
            "orange",
            "purple",
            "pink",
            "navy",
            "beige",
            "gold",
            "silver",
            "color",
            "colour",
        }

        query_words = set(query.lower().split())

        has_size = bool(query_words & size_keywords)
        has_color = bool(query_words & color_keywords)

        if has_size or has_color:
            # Try to find alternative attributes
            try:
                # Find products that match the query (excluding size/color)
                base_query = " ".join(
                    [w for w in query.split() if w.lower() not in size_keywords and w.lower() not in color_keywords]
                )

                if base_query:
                    products = MarketplaceProduct.objects.filter(
                        Q(product__name__icontains=base_query) | Q(product__description__icontains=base_query), is_available=True
                    )[:10]

                    for product in products:
                        # Suggest alternative size
                        if has_color and product.size:
                            alt_query = f"{base_query} {product.size}"
                            suggestions.append(
                                {
                                    "query": alt_query.lower(),
                                    "score": 0.6,
                                    "type": "attribute",
                                    "confidence": 0.5,
                                    "reason": "alternative_size",
                                    "metrics": {"attribute": "size", "value": product.size},
                                }
                            )

                        # Suggest alternative color
                        if has_size and product.color:
                            alt_query = f"{base_query} {product.color}"
                            suggestions.append(
                                {
                                    "query": alt_query.lower(),
                                    "score": 0.6,
                                    "type": "attribute",
                                    "confidence": 0.5,
                                    "reason": "alternative_color",
                                    "metrics": {"attribute": "color", "value": product.color},
                                }
                            )
            except Exception as e:
                logger.debug(f"Error in attribute suggestions: {e}")

        return suggestions

    def _get_complementary_suggestions(self, query: str) -> List[Dict]:
        """
        Get complementary product suggestions
        """
        from ..models import QueryAssociation

        query_hash = self.get_query_hash(query)

        complementary = QueryAssociation.objects.filter(
            Q(source_query_hash=query_hash) | Q(source_query__icontains=query),
            association_type="complementary",
            is_active=True,
            co_occurrence_count__gte=2,
        ).order_by("-co_occurrence_count")[:10]

        suggestions = []
        for comp in complementary:
            score = self._calculate_complementary_score(comp)
            suggestions.append(
                {
                    "query": comp.target_query,
                    "score": score,
                    "type": "complementary",
                    "confidence": comp.confidence_score,
                    "reason": "complementary_product",
                    "metrics": {"co_occurrence": comp.co_occurrence_count, "association_type": comp.association_type},
                }
            )

        return suggestions

    def _get_trending_suggestions(self, query: str) -> List[Dict]:
        """
        Get trending queries as fallback
        """
        from ..models import QueryPerformacePopularity

        trending = (
            QueryPerformacePopularity.objects.filter(trending_score__gt=1.5, total_searches__gte=20)
            .exclude(query=query)
            .order_by("-trending_score", "-total_searches")[:10]
        )

        suggestions = []
        for trend in trending:
            suggestions.append(
                {
                    "query": trend.query,
                    "score": trend.trending_score * 0.5,
                    "type": "trending",
                    "confidence": 0.4,
                    "reason": "trending_now",
                    "metrics": {"trending_score": trend.trending_score, "searches_today": trend.searches_today},
                }
            )

        return suggestions

    def _get_fallback_suggestions(self, query: str, limit: int) -> List[Dict]:
        """
        Fallback when no other suggestions work
        """
        from ..models import QueryPerformacePopularity

        # Get popular queries
        popular = (
            QueryPerformacePopularity.objects.filter(total_searches__gte=10)
            .exclude(query=query)
            .order_by("-total_searches")[: limit * 2]
        )

        suggestions = []
        for i, pop in enumerate(popular):
            suggestions.append(
                {
                    "query": pop.query,
                    "score": 1.0 / (i + 2),  # Decreasing scores
                    "type": "fallback",
                    "confidence": 0.3,
                    "reason": "popular_query",
                    "metrics": {"total_searches": pop.total_searches},
                }
            )

        return suggestions[:limit]

    # Helper methods
    @staticmethod
    def normalize_query(query: str) -> str:
        """Normalize search query"""
        import re

        if not query:
            return ""
        normalized = query.lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"[^\w\s\-\.]", "", normalized)
        return normalized

    @staticmethod
    def get_query_hash(query: str) -> str:
        """Generate hash for query"""
        import hashlib

        normalized = SearchSuggestionService.normalize_query(query)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]

    def _calculate_association_score(self, association) -> float:
        """Calculate score for a query association"""
        import math

        # Base score from co-occurrence
        base_score = math.log1p(association.co_occurrence_count) * 10

        # Boost by CTR
        ctr_boost = association.source_to_target_ctr * 20

        # Boost by conversion rate
        conversion_boost = association.conversion_rate * 30

        # Apply confidence and decay
        confidence_multiplier = association.confidence_score
        decay_multiplier = association.decay_score

        return (base_score + ctr_boost + conversion_boost) * confidence_multiplier * decay_multiplier

    def _calculate_category_score(self, query_pop, original_query) -> float:
        """Calculate score for category-based suggestion"""
        import math

        # Base on popularity
        popularity_score = math.log1p(query_pop.total_searches) * 5

        # Boost if trending
        trending_boost = query_pop.trending_score * 3

        # Penalize if query is very different
        original_words = set(original_query.split())
        target_words = set(query_pop.query.split())
        similarity = len(original_words & target_words) / max(len(original_words | target_words), 1)
        similarity_penalty = similarity * 2

        return popularity_score + trending_boost + similarity_penalty

    def _calculate_complementary_score(self, association) -> float:
        """Calculate score for complementary suggestion"""
        return association.co_occurrence_count * 0.5 + association.confidence_score * 20 + association.decay_score * 10

    def _merge_suggestions(self, all_suggestions: dict, new_suggestions: list, weight: float = 1.0):
        """Merge new suggestions into existing map"""
        for suggestion in new_suggestions:
            query = suggestion["query"]
            weighted_score = suggestion["score"] * weight

            if query in all_suggestions:
                # Average the scores
                existing = all_suggestions[query]
                combined_score = (existing["score"] + weighted_score) / 2
                all_suggestions[query] = {
                    **existing,
                    "score": combined_score,
                    "types": existing.get("types", []) + [suggestion["type"]],
                }
            else:
                all_suggestions[query] = {
                    "score": weighted_score,
                    "type": suggestion["type"],
                    "confidence": suggestion.get("confidence", 0.5),
                    "reason": suggestion.get("reason", ""),
                    "metrics": suggestion.get("metrics", {}),
                    "types": [suggestion["type"]],
                }
