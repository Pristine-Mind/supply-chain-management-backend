import hashlib
import json
import logging
import math
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set

from django.db.models import F, Q, Value
from django.utils import timezone
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


class SearchSuggestionService:
    """
    Complete Search Suggestion Engine.
    Integrates Collaborative Filtering (Co-occurrence), Manual Curations,
    and Performance Metrics.
    """

    def __init__(self):
        self.redis_client = get_redis_connection("default")
        self.cache_ttl = 3600
        self.min_cooccurrence = 3

        self.size_keywords = {"xs", "s", "small", "m", "medium", "l", "large", "xl", "xxl", "xxxl", "size"}
        self.color_keywords = {
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
        }

    def get_suggestions(
        self, query: str, user_id: Optional[str] = None, limit: int = 5, use_cache: bool = True
    ) -> List[Dict]:
        """Entry point to get suggestions for a user query."""
        try:
            normalized_query = self.normalize_query(query)
            if len(normalized_query) < 2:
                return []

            query_hash = self.get_query_hash(normalized_query)
            cache_key = f"suggestions:v2:{query_hash}"

            if use_cache:
                cached = self.redis_client.get(cache_key)
                if cached:
                    self.redis_client.zincrby("suggestion_stats:hits", 1, query_hash)
                    return json.loads(cached)[:limit]

            suggestions = self._generate_suggestions(normalized_query, user_id)

            if use_cache and suggestions:
                self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(suggestions))

            return suggestions[:limit]

        except Exception as e:
            logger.exception(f"Error fetching suggestions for '{query}': {e}")
            return self._get_fallback_suggestions(query, limit)

    def _generate_suggestions(self, query: str, user_id: Optional[str] = None) -> List[Dict]:
        """Combines multiple strategies into a single ranked list."""
        all_suggestions = {}

        strategies = [
            (self._get_manual_suggestions, 1.8),
            (self._get_co_search_suggestions, 1.2),
            (self._get_complementary_suggestions, 1.0),
            (self._get_category_suggestions, 0.8),
            (self._get_attribute_suggestions, 0.7),
        ]

        for strategy_fn, weight in strategies:
            try:
                results = strategy_fn(query)
                self._merge_suggestions(all_suggestions, results, weight)
            except Exception as e:
                logger.error(f"Strategy {strategy_fn.__name__} failed: {e}")

        if len(all_suggestions) < 3:
            trending = self._get_trending_suggestions(query)
            self._merge_suggestions(all_suggestions, trending, 0.5)

        suggestions_list = sorted(all_suggestions.values(), key=lambda x: x["score"], reverse=True)

        self._attach_product_ids_batched(suggestions_list[:10])

        return suggestions_list

    def _get_co_search_suggestions(self, query: str) -> List[Dict]:
        """Uses QueryAssociation model to find search patterns."""
        from .models import QueryAssociation

        q_hash = self.get_query_hash(query)
        associations = QueryAssociation.objects.filter(
            source_query_hash=q_hash, is_active=True, co_occurrence_count__gte=self.min_cooccurrence
        ).order_by("-co_occurrence_count", "-confidence_score")[:15]

        return [
            {
                "query": a.target_query,
                "score": self._calculate_association_score(a),
                "type": "co_search",
                "confidence": a.confidence_score,
                "reason": "frequently_searched_together",
                "metrics": {"ctr": a.source_to_target_ctr, "conv": a.conversion_rate},
            }
            for a in associations
        ]

    def _get_manual_suggestions(self, query: str) -> List[Dict]:
        """Uses ManualQueryAssociation model for business-driven overrides."""
        from .models import ManualQueryAssociation

        manuals = ManualQueryAssociation.objects.filter(
            Q(source_query__iexact=query) | Q(source_query__icontains=query), is_active=True
        ).order_by("-priority", "-strength")[:5]

        return [
            {
                "query": m.target_query,
                "score": m.strength * 10,
                "type": "manual",
                "confidence": 1.0,
                "reason": m.relationship_type,
                "metrics": {"priority": m.priority},
            }
            for m in manuals
        ]

    def _get_category_suggestions(self, query: str) -> List[Dict]:
        """Leverages QueryPerformacePopularity to find popular queries in same category."""
        from .models import QueryPerformacePopularity

        current_perf = QueryPerformacePopularity.objects.filter(query__iexact=query).first()
        if not current_perf or not current_perf.primary_category:
            return []

        related_cat_queries = (
            QueryPerformacePopularity.objects.filter(primary_category=current_perf.primary_category)
            .exclude(query__iexact=query)
            .order_by("-trending_score", "-total_searches")[:5]
        )

        return [
            {
                "query": rp.query,
                "score": math.log1p(rp.total_searches) * 2 + (rp.trending_score * 5),
                "type": "category",
                "reason": f"popular_in_{rp.primary_category}",
            }
            for rp in related_cat_queries
        ]

    def _get_attribute_suggestions(self, query: str) -> List[Dict]:
        """Swaps colors/sizes if the query contains them."""
        from producer.models import MarketplaceProduct

        words = query.lower().split()
        found_colors = [w for w in words if w in self.color_keywords]
        found_sizes = [w for w in words if w in self.size_keywords]

        if not (found_colors or found_sizes):
            return []

        base_name = " ".join([w for w in words if w not in self.color_keywords and w not in self.size_keywords])

        variations = (
            MarketplaceProduct.objects.filter(product__name__icontains=base_name, is_available=True)
            .only("color", "size")
            .distinct()[:5]
        )

        suggestions = []
        for var in variations:
            if found_colors and var.color and var.color not in found_colors:
                suggestions.append(
                    {"query": f"{base_name} {var.color}", "score": 5.0, "type": "attribute", "reason": "different_color"}
                )
            if found_sizes and var.size and var.size not in found_sizes:
                suggestions.append(
                    {"query": f"{base_name} {var.size}", "score": 5.0, "type": "attribute", "reason": "different_size"}
                )

        return suggestions

    def _get_complementary_suggestions(self, query: str) -> List[Dict]:
        """Specifically filters for 'complementary' type associations."""
        from .models import QueryAssociation

        comps = QueryAssociation.objects.filter(
            source_query_hash=self.get_query_hash(query), association_type="complementary", is_active=True
        ).order_by("-confidence_score")[:5]

        return [
            {
                "query": c.target_query,
                "score": c.confidence_score * 50,
                "type": "complementary",
                "reason": "customers_also_bought",
            }
            for c in comps
        ]

    def _get_trending_suggestions(self, query: str) -> List[Dict]:
        """Uses Redis ZSet for real-time trending or QueryPerformacePopularity for historical."""
        hot_queries = self.redis_client.zrevrange("global:trending_searches", 0, 5, withscores=True)
        if hot_queries:
            return [
                {"query": q.decode(), "score": score, "type": "trending", "reason": "trending_now"}
                for q, score in hot_queries
            ]

        from .models import QueryPerformacePopularity

        trending = (
            QueryPerformacePopularity.objects.filter(trending_score__gt=0)
            .exclude(query__iexact=query)
            .order_by("-trending_score")[:5]
        )
        return [
            {"query": t.query, "score": t.trending_score * 10, "type": "trending", "reason": "trending_this_week"}
            for t in trending
        ]

    def _calculate_association_score(self, assoc) -> float:
        """
        Custom algorithm to rank associations.
        Score = (log(Volume) + CTR_Bonus + Conv_Bonus) * Time_Decay
        """
        volume_factor = math.log1p(assoc.co_occurrence_count) * 10
        performance_factor = (assoc.source_to_target_ctr * 25) + (assoc.conversion_rate * 40)
        return (volume_factor + performance_factor) * assoc.decay_score

    def _merge_suggestions(self, all_suggestions: dict, new_items: list, weight: float):
        """Merges new suggestions into the main map using weighted averages."""
        for item in new_items:
            q = item["query"].lower().strip()
            weighted_score = item["score"] * weight

            if q in all_suggestions:
                all_suggestions[q]["score"] = (all_suggestions[q]["score"] + weighted_score) / 1.5
                all_suggestions[q]["types"] = list(set(all_suggestions[q].get("types", []) + [item["type"]]))
            else:
                item["types"] = [item["type"]]
                item["score"] = weighted_score
                all_suggestions[q] = item

    def _attach_product_ids_batched(self, suggestions_list: List[Dict]):
        """
        Fetches relevant Product IDs in ONE database query.
        Prevents N+1 query issues in the suggestion loop.
        """
        from producer.models import MarketplaceProduct

        queries = [s["query"] for s in suggestions_list]
        if not queries:
            return

        filter_q = Q()
        for q_text in queries[:5]:
            filter_q |= Q(product__name__icontains=q_text)

        products = MarketplaceProduct.objects.filter(filter_q, is_available=True).only("id", "product__name")

        for s in suggestions_list:
            for p in products:
                if s["query"].lower() in p.product.name.lower():
                    s["product_id"] = p.id
                    break

    def _get_fallback_suggestions(self, query: str, limit: int) -> List[Dict]:
        """Last resort: return global popular queries."""
        from .models import QueryPerformacePopularity

        popular = QueryPerformacePopularity.objects.order_by("-total_searches")[:limit]
        return [{"query": p.query, "score": 1.0, "type": "fallback", "reason": "popular_search"} for p in popular]

    @staticmethod
    def normalize_query(query: str) -> str:
        if not query:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s\-\.]", "", query.lower())).strip()

    @staticmethod
    def get_query_hash(query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]
