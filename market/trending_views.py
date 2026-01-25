import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import (
    Avg,
    Case,
    CharField,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Max,
    Min,
    Q,
    Sum,
    Value,
    When,
    Window,
)
from django.db.models.functions import Coalesce, Rank
from django.utils import timezone

TRENDING_CACHE_TTL = getattr(settings, "TRENDING_CACHE_TTL", 20)
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from producer.models import MarketplaceProduct

from .trending_serializers import (
    TrendingCategorySerializer,
    TrendingProductSerializer,
    TrendingStatsSerializer,
)


class TrendingProductsManager:
    """
    Manager class to handle trending products calculations and queries
    """

    @staticmethod
    def calculate_trending_score(queryset):
        """
        Calculate trending score based on multiple factors:
        - Recent purchases (40% weight)
        - View count (30% weight)
        - Average rating (20% weight)
        - Recency factor (10% weight)
        """
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        day_ago = now - timedelta(days=1)

        return queryset.annotate(
            # Recent sales metrics
            recent_sales_count=Count("sales", filter=Q(sales__sale_date__gte=day_ago)),
            weekly_sales_count=Count("sales", filter=Q(sales__sale_date__gte=week_ago)),
            total_sales=Count("sales"),
            # View metrics
            weekly_view_count=Count("views", filter=Q(views__timestamp__gte=week_ago)),
            # Sales velocity (sales per day over last week)
            sales_velocity=Case(
                When(weekly_sales_count__gt=0, then=F("weekly_sales_count") / 7.0), default=0.0, output_field=FloatField()
            ),
            # Engagement rate (views to sales ratio)
            engagement_rate=Case(
                When(weekly_view_count__gt=0, then=(F("weekly_sales_count") * 100.0) / F("weekly_view_count")),
                default=0.0,
                output_field=FloatField(),
            ),
            # Calculate final trending score (with explicit type casting)
            trending_score=Case(
                When(
                    is_available=True,
                    then=(
                        # Recent purchases weight (50%) - cast to float
                        (F("recent_purchases_count") * 3.0 + F("weekly_sales_count") * 1.0) * 0.5
                        +
                        # View count weight (30%) - cast to float
                        (F("view_count") * 1.0 / 100.0) * 0.3
                        +
                        # Rating weight (20%) - cast to float
                        (Coalesce(F("rank_score"), 0.0) / 5.0) * 0.2
                    ),
                ),
                default=0.0,
                output_field=FloatField(),
            ),
            # Price trend indicator (simplified)
            price_trend=Case(
                When(discounted_price__isnull=False, then=Value("decreasing")),
                When(Q(offer_start__isnull=False) & Q(offer_end__isnull=False), then=Value("promotional")),
                default=Value("stable"),
                output_field=CharField(),
            ),
        ).annotate(
            # Add ranking based on trending score
            trending_rank=Window(expression=Rank(), order_by=F("trending_score").desc())
        )

    @staticmethod
    def calculate_trending_score_fast(queryset):
        """Lightweight trending score calculation using stored counters.

        This avoids expensive COUNT joins and window functions by relying on
        precomputed fields on `MarketplaceProduct` such as `recent_purchases_count`,
        `view_count`, and `rank_score`. Use this for high-traffic endpoints where
        slight approximation is acceptable in exchange for much faster queries.
        """
        # Build expression using Value() to ensure consistent numeric types
        expr = (
            (Coalesce(F("recent_purchases_count"), Value(0.0)) * Value(3.0) * Value(0.5))
            + (Coalesce(F("view_count"), Value(0.0)) * Value(1.0) / Value(100.0) * Value(0.3))
            + (Coalesce(F("rank_score"), Value(0.0)) / Value(5.0) * Value(0.2))
        )
        return queryset.annotate(trending_score=ExpressionWrapper(expr, output_field=FloatField()))

    @staticmethod
    def get_trending_categories():
        """
        Get trending product categories with metrics
        """
        week_ago = timezone.now() - timedelta(days=7)

        return (
            MarketplaceProduct.objects.filter(is_available=True)
            .values(category_name=F("product__category"))
            .annotate(
                product_count=Count("id"),
                total_sales=Count("sales"),
                weekly_sales=Count("sales", filter=Q(sales__sale_date__gte=week_ago)),
                avg_rating=Avg("rank_score"),
                trending_score=F("weekly_sales") * 2.0 + F("product_count") * 0.5,
            )
            .order_by("-trending_score")[:10]
        )


class TrendingProductsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for trending marketplace products with various filtering options
    """

    serializer_class = TrendingProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        """
        Get base queryset with trending calculations
        """
        queryset = (
            MarketplaceProduct.objects.filter(is_available=True)
            .select_related("product", "product__user", "product__user__user_profile")
            .prefetch_related("bulk_price_tiers", "variants", "reviews")
        )

        return TrendingProductsManager.calculate_trending_score(queryset)

    def list(self, request, *args, **kwargs):
        """
        List trending products with optional filtering
        """
        # Allow bypassing cache with `nocache=1`
        nocache = request.query_params.get("nocache")

        # Build a cache key based on full path and user (if authenticated)
        try:
            user_part = str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        except Exception:
            user_part = "anon"
        cache_key = (
            "trending:list:" + hashlib.sha256((request.get_full_path() + ":" + user_part).encode("utf-8")).hexdigest()
        )

        if not nocache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        queryset = self.get_queryset()

        # Apply filters
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(product__category__name__icontains=category)

        min_price = request.query_params.get("min_price")
        max_price = request.query_params.get("max_price")
        if min_price:
            queryset = queryset.filter(listed_price__gte=min_price)
        if max_price:
            queryset = queryset.filter(listed_price__lte=max_price)

        location = request.query_params.get("location")
        if location:
            queryset = queryset.filter(product__user__user_profile__city__icontains=location)

        # Order by trending score
        queryset = queryset.order_by("-trending_score", "-weekly_sales_count")

        # Limit results
        limit = request.query_params.get("limit", 20)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:20]

        serializer = self.get_serializer(queryset, many=True)
        payload = {"results": serializer.data, "count": len(serializer.data), "timestamp": timezone.now().isoformat()}

        try:
            if not nocache:
                cache.set(cache_key, payload, TRENDING_CACHE_TTL)
        except Exception:
            pass

        return Response(payload)

    @action(detail=False, methods=["get"])
    def top_weekly(self, request):
        """
        Get top trending products for the last week (fast path).
        """
        nocache = request.query_params.get("nocache")
        try:
            user_part = str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        except Exception:
            user_part = "anon"
        cache_key = (
            "trending:top_weekly:" + hashlib.sha256((request.get_full_path() + ":" + user_part).encode("utf-8")).hexdigest()
        )

        if not nocache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        week_ago = timezone.now() - timedelta(days=7)

        # Use an approximation: rely on stored `recent_purchases_count` as a proxy
        base_qs = MarketplaceProduct.objects.filter(
            is_available=True, listed_date__gte=week_ago, recent_purchases_count__gt=0
        )
        queryset = TrendingProductsManager.calculate_trending_score_fast(base_qs).order_by("-trending_score")[:10]

        serializer = self.get_serializer(queryset, many=True)
        payload = {"results": serializer.data, "period": "weekly", "count": len(serializer.data)}
        try:
            if not nocache:
                cache.set(cache_key, payload, TRENDING_CACHE_TTL)
        except Exception:
            pass

        return Response(payload)

    @action(detail=False, methods=["get"])
    def most_viewed(self, request):
        """
        Get most viewed trending products
        """
        nocache = request.query_params.get("nocache")
        try:
            user_part = str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        except Exception:
            user_part = "anon"
        cache_key = (
            "trending:most_viewed:" + hashlib.sha256((request.get_full_path() + ":" + user_part).encode("utf-8")).hexdigest()
        )

        if not nocache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        # Build a fast queryset that annotates a lightweight trending_score
        base_qs = MarketplaceProduct.objects.filter(is_available=True)
        queryset = (
            TrendingProductsManager.calculate_trending_score_fast(base_qs)
            .filter(view_count__gt=0)
            .order_by("-view_count", "-trending_score")[:10]
        )

        serializer = self.get_serializer(queryset, many=True)
        payload = {"results": serializer.data, "period": "most_viewed", "count": len(serializer.data)}
        try:
            if not nocache:
                cache.set(cache_key, payload, TRENDING_CACHE_TTL)
        except Exception:
            pass

        return Response(payload)

    @action(detail=False, methods=["get"])
    def fastest_selling(self, request):
        """
        Get products with highest sales velocity
        """
        nocache = request.query_params.get("nocache")
        try:
            user_part = str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        except Exception:
            user_part = "anon"
        cache_key = (
            "trending:fastest_selling:"
            + hashlib.sha256((request.get_full_path() + ":" + user_part).encode("utf-8")).hexdigest()
        )

        if not nocache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        queryset = self.get_queryset().filter(sales_velocity__gt=0).order_by("-sales_velocity", "-trending_score")[:10]

        serializer = self.get_serializer(queryset, many=True)
        payload = {"results": serializer.data, "period": "fastest_selling", "count": len(serializer.data)}
        try:
            if not nocache:
                cache.set(cache_key, payload, TRENDING_CACHE_TTL)
        except Exception:
            pass

        return Response(payload)

    @action(detail=False, methods=["get"])
    def new_trending(self, request):
        """
        Get newly listed products that are trending
        """
        nocache = request.query_params.get("nocache")
        try:
            user_part = str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        except Exception:
            user_part = "anon"
        cache_key = (
            "trending:new_trending:"
            + hashlib.sha256((request.get_full_path() + ":" + user_part).encode("utf-8")).hexdigest()
        )

        if not nocache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        week_ago = timezone.now() - timedelta(days=7)
        base_qs = MarketplaceProduct.objects.filter(is_available=True, listed_date__gte=week_ago)
        queryset = TrendingProductsManager.calculate_trending_score_fast(base_qs).order_by(
            "-trending_score", "-listed_date"
        )[:10]

        serializer = self.get_serializer(queryset, many=True)
        payload = {"results": serializer.data, "period": "new_trending", "count": len(serializer.data)}
        try:
            if not nocache:
                cache.set(cache_key, payload, TRENDING_CACHE_TTL)
        except Exception:
            pass

        return Response(payload)

    @action(detail=False, methods=["get"])
    def categories(self, request):
        """
        Get trending categories
        """
        categories = TrendingProductsManager.get_trending_categories()
        serializer = TrendingCategorySerializer(categories, many=True)
        return Response({"results": serializer.data, "count": len(serializer.data)})

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Get trending products statistics
        """
        queryset = self.get_queryset()

        total_trending = queryset.filter(trending_score__gt=0).count()
        avg_trending_score = queryset.aggregate(avg_score=Avg("trending_score"))["avg_score"] or 0

        # Price range of trending products
        price_stats = queryset.filter(trending_score__gt=0).aggregate(
            min_price=Min("listed_price"), max_price=Max("listed_price"), avg_price=Avg("listed_price")
        )

        categories = TrendingProductsManager.get_trending_categories()

        stats_data = {
            "total_trending_products": total_trending,
            "trending_categories": categories,
            "top_performing_timeframe": "weekly",
            "average_trending_score": round(avg_trending_score, 2),
            "price_range": {
                "min": price_stats["min_price"] or 0,
                "max": price_stats["max_price"] or 0,
                "average": round(price_stats["avg_price"] or 0, 2),
            },
        }

        serializer = TrendingStatsSerializer(stats_data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def deals(self, request):
        """
        Get all current deals and discounted products
        """
        now = timezone.now()
        queryset = (
            self.get_queryset()
            .filter(
                Q(discounted_price__isnull=False)
                | (
                    Q(offer_start__isnull=False)
                    & Q(offer_end__isnull=False)
                    & Q(offer_start__lte=now)
                    & Q(offer_end__gte=now)
                )
            )
            .order_by("-trending_score")
        )

        # Apply category filter if provided
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(product__category__icontains=category)

        # Apply discount percentage filter
        min_discount = request.query_params.get("min_discount")
        if min_discount:
            try:
                min_discount = float(min_discount)
                # Calculate discount percentage: ((listed - discounted) / listed) * 100
                queryset = queryset.extra(
                    where=["((listed_price - COALESCE(discounted_price, listed_price)) / listed_price * 100) >= %s"],
                    params=[min_discount],
                )
            except (ValueError, TypeError):
                pass

        # Limit results
        limit = request.query_params.get("limit", 20)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:20]

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "results": serializer.data,
                "count": len(serializer.data),
                "timestamp": timezone.now().isoformat(),
                "type": "deals",
            }
        )

    @action(detail=False, methods=["get"])
    def featured(self, request):
        """
        Get featured products marked by admins.
        """
        queryset = self.get_queryset().filter(is_featured=True).order_by("-trending_score")

        # Limit results
        limit = request.query_params.get("limit", 20)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:20]

        nocache = request.query_params.get("nocache")
        try:
            user_part = str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        except Exception:
            user_part = "anon"
        cache_key = (
            "trending:featured:" + hashlib.sha256((request.get_full_path() + ":" + user_part).encode("utf-8")).hexdigest()
        )

        if not nocache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        serializer = self.get_serializer(queryset, many=True)
        payload = {"results": serializer.data, "count": len(serializer.data), "type": "featured"}
        try:
            if not nocache:
                cache.set(cache_key, payload, TRENDING_CACHE_TTL)
        except Exception:
            pass

        return Response(payload)

    @action(detail=False, methods=["get"])
    def flash_sales(self, request):
        """
        Get products with active time-limited offers (flash sales)
        """
        now = timezone.now()
        # Products with active offers ending within 24 hours
        tomorrow = now + timedelta(days=1)

        queryset = (
            self.get_queryset()
            .filter(
                offer_start__isnull=False,
                offer_end__isnull=False,
                offer_start__lte=now,
                offer_end__gte=now,
                offer_end__lte=tomorrow,  # Ending within 24 hours
            )
            .order_by("offer_end", "-trending_score")[:15]
        )

        serializer = self.get_serializer(queryset, many=True)

        # Add countdown information to each product
        results = []
        for product_data in serializer.data:
            # Get the actual product to calculate countdown
            try:
                product = MarketplaceProduct.objects.get(id=product_data["id"])
                countdown_seconds = (product.offer_end - now).total_seconds()
                product_data["countdown_seconds"] = max(0, countdown_seconds)
                product_data["countdown_hours"] = max(0, countdown_seconds / 3600)
            except MarketplaceProduct.DoesNotExist:
                product_data["countdown_seconds"] = 0
                product_data["countdown_hours"] = 0

            results.append(product_data)

        return Response(
            {"results": results, "count": len(results), "timestamp": timezone.now().isoformat(), "type": "flash_sales"}
        )

    @action(detail=False, methods=["get"])
    def best_discounts(self, request):
        """
        Get products with the highest discount percentages
        """
        queryset = (
            self.get_queryset()
            .filter(discounted_price__isnull=False, listed_price__gt=0)
            .extra(select={"discount_percentage": "((listed_price - discounted_price) / listed_price * 100)"})
            .order_by("-discount_percentage", "-trending_score")
        )

        # Filter by minimum discount if specified
        min_discount = request.query_params.get("min_discount", 10)
        try:
            min_discount = float(min_discount)
            queryset = queryset.extra(
                where=["((listed_price - discounted_price) / listed_price * 100) >= %s"], params=[min_discount]
            )
        except (ValueError, TypeError):
            pass

        # Limit results
        limit = request.query_params.get("limit", 15)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:15]

        serializer = self.get_serializer(queryset, many=True)

        # Add discount percentage to each result
        results = []
        for product_data in serializer.data:
            try:
                product = MarketplaceProduct.objects.get(id=product_data["id"])
                if product.discounted_price and product.listed_price > 0:
                    discount_pct = ((product.listed_price - product.discounted_price) / product.listed_price) * 100
                    product_data["discount_percentage"] = round(discount_pct, 1)
                    product_data["savings_amount"] = round(product.listed_price - product.discounted_price, 2)
                else:
                    product_data["discount_percentage"] = 0
                    product_data["savings_amount"] = 0
            except MarketplaceProduct.DoesNotExist:
                product_data["discount_percentage"] = 0
                product_data["savings_amount"] = 0

            results.append(product_data)

        return Response(
            {"results": results, "count": len(results), "timestamp": timezone.now().isoformat(), "type": "best_discounts"}
        )

    @action(detail=False, methods=["get"])
    def seasonal_deals(self, request):
        """
        Get seasonal deals and special promotional products
        """
        now = timezone.now()

        # Products with active offers or discounts
        queryset = self.get_queryset().filter(
            Q(discounted_price__isnull=False)
            | (Q(offer_start__isnull=False) & Q(offer_end__isnull=False) & Q(offer_start__lte=now) & Q(offer_end__gte=now))
        )

        # Filter by season/duration if specified
        duration = request.query_params.get("duration", "week")
        if duration == "today":
            end_time = now + timedelta(days=1)
        elif duration == "week":
            end_time = now + timedelta(days=7)
        elif duration == "month":
            end_time = now + timedelta(days=30)
        else:
            end_time = now + timedelta(days=7)

        # Filter offers ending within the specified duration
        queryset = queryset.filter(
            Q(offer_end__isnull=True)  # No end date (permanent discount)
            | Q(offer_end__lte=end_time)  # Ending within specified duration
        ).order_by("-trending_score")

        # Apply category filter
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(product__category__icontains=category)

        # Limit results
        limit = request.query_params.get("limit", 20)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:20]

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "results": serializer.data,
                "count": len(serializer.data),
                "timestamp": timezone.now().isoformat(),
                "type": "seasonal_deals",
                "duration": duration,
            }
        )

    @action(detail=False, methods=["get"])
    def deal_categories(self, request):
        """
        Get categories with the most deals and their statistics
        """
        now = timezone.now()

        # Get categories with active deals
        categories_with_deals = (
            MarketplaceProduct.objects.filter(is_available=True)
            .filter(
                Q(discounted_price__isnull=False)
                | (
                    Q(offer_start__isnull=False)
                    & Q(offer_end__isnull=False)
                    & Q(offer_start__lte=now)
                    & Q(offer_end__gte=now)
                )
            )
            .values(category_name=F("product__category"))
            .annotate(
                deal_count=Count("id"),
                avg_discount=Avg(
                    Case(
                        When(
                            discounted_price__isnull=False,
                            then=((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100,
                        ),
                        default=0,
                        output_field=FloatField(),
                    )
                ),
                max_discount=Max(
                    Case(
                        When(
                            discounted_price__isnull=False,
                            then=((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100,
                        ),
                        default=0,
                        output_field=FloatField(),
                    )
                ),
                total_savings=Sum(
                    Case(
                        When(discounted_price__isnull=False, then=F("listed_price") - F("discounted_price")),
                        default=0,
                        output_field=FloatField(),
                    )
                ),
            )
            .order_by("-deal_count", "-avg_discount")[:10]
        )

        return Response(
            {
                "results": list(categories_with_deals),
                "count": len(categories_with_deals),
                "timestamp": timezone.now().isoformat(),
                "type": "deal_categories",
            }
        )

    @action(detail=False, methods=["get"])
    def deal_stats(self, request):
        """
        Get comprehensive statistics about current deals
        """
        now = timezone.now()
        queryset = self.get_queryset()

        # Count different types of deals
        total_deals = queryset.filter(
            Q(discounted_price__isnull=False)
            | (Q(offer_start__isnull=False) & Q(offer_end__isnull=False) & Q(offer_start__lte=now) & Q(offer_end__gte=now))
        ).count()

        discount_deals = queryset.filter(discounted_price__isnull=False).count()

        active_offers = queryset.filter(
            offer_start__isnull=False, offer_end__isnull=False, offer_start__lte=now, offer_end__gte=now
        ).count()

        # Calculate average discount
        avg_discount_info = queryset.filter(discounted_price__isnull=False, listed_price__gt=0).aggregate(
            avg_discount=Avg(
                ((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100, output_field=FloatField()
            ),
            max_discount=Max(
                ((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100, output_field=FloatField()
            ),
            total_savings=Sum(F("listed_price") - F("discounted_price"), output_field=FloatField()),
        )

        # Flash sales ending soon (within 24 hours)
        tomorrow = now + timedelta(days=1)
        flash_sales_count = queryset.filter(
            offer_start__isnull=False,
            offer_end__isnull=False,
            offer_start__lte=now,
            offer_end__gte=now,
            offer_end__lte=tomorrow,
        ).count()

        stats_data = {
            "total_deals": total_deals,
            "discount_deals": discount_deals,
            "active_offers": active_offers,
            "flash_sales_ending_soon": flash_sales_count,
            "average_discount_percentage": round(avg_discount_info["avg_discount"] or 0, 2),
            "maximum_discount_percentage": round(avg_discount_info["max_discount"] or 0, 2),
            "total_savings_amount": round(avg_discount_info["total_savings"] or 0, 2),
            "deals_percentage": round((total_deals / queryset.count() * 100) if queryset.count() > 0 else 0, 2),
        }

        return Response({"stats": stats_data, "timestamp": timezone.now().isoformat(), "type": "deal_statistics"})

    @action(detail=False, methods=["get"], url_path="made-in-nepal", permission_classes=[AllowAny])
    def made_in_nepal(self, request):
        # Get base queryset filtered for made in Nepal products
        qs = self.get_queryset().filter(is_made_in_nepal=True)
        qs = self.filter_queryset(qs)
        paginator = self.paginator
        page_size = request.query_params.get("page_size")
        if page_size:
            try:
                paginator.page_size = int(page_size)
            except (ValueError, TypeError):
                pass
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.get_serializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)
