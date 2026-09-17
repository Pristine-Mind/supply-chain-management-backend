import re
from decimal import Decimal

from django.db.models import Avg, Case, Count, DecimalField, F, Q, Value, When
from django.db.models.functions import Coalesce
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from producer.search_utils import (
    CityFilter,
    ColorFilter,
    SizeFilter,
    build_relevance_score_case,
)
from producer.utils import smart_ai_search

from .advanced_filters import (
    FacetedSearchService,
    get_filtered_products_with_facets,
)
from .serializers import MarketplaceProductSerializer


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AdvancedProductSearchView(APIView):
    """
    Advanced product search with faceted filtering, relevance ranking, and comprehensive filters.

    Query Parameters:
    - q or search: Text search with relevance ranking
    - city: City name or ID (case-insensitive)
    - category_id, subcategory_id, sub_subcategory_id: Category filters
    - brand_id: Filter by brand (can be multiple: brand_id=1&brand_id=2)
    - colors: Color values (case-insensitive with aliasing support)
    - sizes: Size values (case-insensitive)
    - min_price, max_price: Price range filters
    - price_range: Preset ranges (budget, economy, mid, premium, luxury)
    - min_rating: Minimum average rating (1-5)
    - min_reviews: Minimum number of reviews
    - in_stock: true/false
    - stock_status: in_stock, low_stock, out_of_stock
    - delivery_days_max: Maximum delivery days
    - has_discount: true/false
    - discount_min: Minimum discount percentage
    - on_sale: true/false
    - b2b_available: true/false
    - made_in_nepal: true/false
    - sort_by: relevance, price_asc, price_desc, newest, popular, rating, name_asc, name_desc, discount
    - near_me: lat,lng,radius_km (e.g., 27.7172,85.3240,10)
    """

    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        from producer.models import MarketplaceProduct

        search_query = (request.query_params.get("q") or request.query_params.get("search") or "").strip()
        city = request.query_params.get("city")
        category_id = request.query_params.get("category_id")
        subcategory_id = request.query_params.get("subcategory_id")
        sub_subcategory_id = request.query_params.get("sub_subcategory_id")
        colors = request.query_params.getlist("colors")
        sizes = request.query_params.getlist("sizes")
        min_price = request.query_params.get("min_price")
        max_price = request.query_params.get("max_price")
        min_rating = request.query_params.get("min_rating")
        delivery_days = request.query_params.get("delivery_days_max")
        made_in_nepal = request.query_params.get("made_in_nepal")
        in_stock = request.query_params.get("in_stock")
        has_discount = request.query_params.get("has_discount")
        sort_by = request.query_params.get("sort_by", "relevance")
        brand_ids = request.query_params.getlist("brand_id")

        use_ai_search = bool(search_query and len(search_query) >= 2)

        ai_features = None
        if search_query and len(search_query) >= 2:
            try:
                if use_ai_search:
                    queryset, ai_features = smart_ai_search(search_query)
                    queryset = queryset.select_related(
                        "product", "product__user", "product__category", "product__brand"
                    ).prefetch_related("variants", "reviews")
                else:
                    _, ai_features = smart_ai_search(search_query)
                    queryset = (
                        MarketplaceProduct.objects.filter(is_available=True)
                        .select_related("product", "product__user", "product__category", "product__brand")
                        .prefetch_related("variants", "reviews")
                    )
            except Exception:
                use_ai_search = False
                ai_features = None
                queryset = (
                    MarketplaceProduct.objects.filter(is_available=True)
                    .select_related("product", "product__user", "product__category", "product__brand")
                    .prefetch_related("variants", "reviews")
                )
        else:
            queryset = (
                MarketplaceProduct.objects.filter(is_available=True)
                .select_related("product", "product__user", "product__category", "product__brand")
                .prefetch_related("variants", "reviews")
            )

        queryset = queryset.annotate(
            avg_rating=Coalesce(Avg("reviews__rating"), Value(0), output_field=DecimalField()),
            num_reviews=Count("reviews", distinct=True),
        )

        if not use_ai_search and search_query and len(search_query) >= 2:
            queryset = queryset.filter(
                Q(product__name__icontains=search_query)
                | Q(product__description__icontains=search_query)
                | Q(search_tags__contains=search_query.lower())
            ).distinct()

        if category_id:
            try:
                queryset = queryset.filter(product__category_id=int(category_id))
            except (ValueError, TypeError):
                pass

        if subcategory_id:
            try:
                queryset = queryset.filter(product__subcategory_id=int(subcategory_id))
            except (ValueError, TypeError):
                pass

        if sub_subcategory_id:
            try:
                queryset = queryset.filter(product__sub_subcategory_id=int(sub_subcategory_id))
            except (ValueError, TypeError):
                pass

        if city:
            queryset = CityFilter.apply_city_filter(queryset, city)

        if colors:
            queryset = ColorFilter.apply_color_filter(queryset, colors)

        if sizes:
            queryset = SizeFilter.apply_size_filter(queryset, sizes)

        if min_price:
            try:
                min_val = Decimal(str(min_price))
                queryset = queryset.filter(
                    Coalesce("discounted_price", "listed_price", output_field=DecimalField()) >= min_val
                )
            except (ValueError, TypeError):
                pass

        if max_price:
            try:
                max_val = Decimal(str(max_price))
                queryset = queryset.filter(
                    Coalesce("discounted_price", "listed_price", output_field=DecimalField()) <= max_val
                )
            except (ValueError, TypeError):
                pass

        if min_rating:
            try:
                queryset = queryset.filter(avg_rating__gte=Decimal(str(min_rating)))
            except (ValueError, TypeError):
                pass

        if delivery_days:
            try:
                days = int(delivery_days)
                queryset = queryset.filter(
                    Q(estimated_delivery_days__isnull=True) | Q(estimated_delivery_days__lte=days)
                )
            except (ValueError, TypeError):
                pass

        if brand_ids:
            try:
                valid_bids = [int(b) for b in brand_ids if b]
                if valid_bids:
                    queryset = queryset.filter(product__brand_id__in=valid_bids)
            except (ValueError, TypeError):
                pass

        if made_in_nepal and made_in_nepal.lower() == "true":
            queryset = queryset.filter(is_made_in_nepal=True)

        if in_stock and in_stock.lower() == "true":
            queryset = queryset.filter(product__stock__gt=0)

        if has_discount and has_discount.lower() == "true":
            queryset = queryset.filter(discounted_price__isnull=False, discounted_price__lt=F("listed_price"))

        if sort_by == "rating":
            queryset = queryset.order_by("-avg_rating", "-num_reviews", "-listed_date").distinct()
        elif sort_by in ["price_asc", "price_low"]:
            queryset = (
                queryset.annotate(
                    effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField())
                )
                .order_by("effective_price")
                .distinct()
            )
        elif sort_by in ["price_desc", "price_high"]:
            queryset = (
                queryset.annotate(
                    effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField())
                )
                .order_by("-effective_price")
                .distinct()
            )
        elif sort_by == "newest":
            queryset = queryset.order_by("-listed_date").distinct()
        elif sort_by == "popular":
            queryset = queryset.order_by("-view_count", "-recent_purchases_count").distinct()
        elif sort_by == "discount":
            queryset = (
                queryset.annotate(
                    discount_pct=Case(
                        When(
                            discounted_price__isnull=False,
                            then=(F("listed_price") - F("discounted_price")) / F("listed_price") * 100,
                        ),
                        default=Value(0, output_field=DecimalField()),
                        output_field=DecimalField(),
                    )
                )
                .order_by("-discount_pct")
                .distinct()
            )
        elif sort_by == "name_asc":
            queryset = queryset.order_by("product__name").distinct()
        elif sort_by == "name_desc":
            queryset = queryset.order_by("-product__name").distinct()
        else:
            if not use_ai_search:
                queryset = queryset.order_by("-listed_date", "-view_count").distinct()
        is_fallback = False
        fallback_reason = None
        suggested_keywords = []

        if search_query and not queryset.exists():
            synonym_meta = ai_features.get("synonym_resolution") if ai_features else None
            if synonym_meta and synonym_meta.get("canonical_term"):
                target = synonym_meta["canonical_term"].strip()
                if len(target) <= 3:
                    boundary = r"(^|[\s\-_/.,()])" + re.escape(target) + r"([\s\-_/.,()]|$)"
                    term_q = Q(product__name__iregex=boundary) | Q(search_tags__iregex=boundary)
                else:
                    term_q = Q(product__name__icontains=target) | Q(search_tags__icontains=target)

                fallback_qs = (
                    MarketplaceProduct.objects.filter(is_available=True)
                    .annotate(effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField()))
                    .filter(term_q)
                    .select_related("product", "product__brand", "product__category")
                    .prefetch_related("variants", "reviews")
                    .order_by("-listed_date")
                )
                if ai_features:
                    if ai_features.get("max_price") is not None:
                        fallback_qs = fallback_qs.filter(effective_price__lte=ai_features["max_price"])
                    if ai_features.get("min_price") is not None:
                        fallback_qs = fallback_qs.filter(effective_price__gte=ai_features["min_price"])

                if fallback_qs.exists():
                    queryset = fallback_qs
                    is_fallback = True
                    fallback_reason = f"Exact match unavailable. Showing items matching '{target}'."
                    suggested_keywords = synonym_meta.get("trending_suggestions", [])
            if not is_fallback and synonym_meta and synonym_meta.get("category"):
                cat_name = synonym_meta["category"]
                fallback_qs = (
                    MarketplaceProduct.objects.filter(is_available=True)
                    .annotate(effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField()))
                    .filter(product__category__name__icontains=cat_name)
                    .select_related("product", "product__brand", "product__category")
                    .prefetch_related("variants", "reviews")
                    .order_by("-listed_date")
                )
                if fallback_qs.exists():
                    queryset = fallback_qs
                    is_fallback = True
                    fallback_reason = f"Showing popular items from category '{cat_name}'."
                    suggested_keywords = synonym_meta.get("trending_suggestions", [])

            if not is_fallback:
                fallback_qs = (
                    MarketplaceProduct.objects.filter(is_available=True)
                    .annotate(effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField()))
                    .select_related("product", "product__brand", "product__category")
                    .prefetch_related("variants", "reviews")
                    .order_by("-listed_date")
                )
                queryset = fallback_qs
                is_fallback = True
                fallback_reason = "No direct matches found. Showing trending products."
                suggested_keywords = ["Inverter AC", "Single Door Refrigerator", "Electric Geyser", "Washing Machine"]

        total_count = queryset.count()

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = MarketplaceProductSerializer(page, many=True, context={"request": request})
            paginated_res = paginator.get_paginated_response(serializer.data)
            paginated_res.data["total_count"] = total_count
            paginated_res.data["ai_search_enabled"] = use_ai_search
            paginated_res.data["ai_features"] = ai_features
            paginated_res.data["is_fallback"] = is_fallback
            paginated_res.data["fallback_reason"] = fallback_reason
            paginated_res.data["trending_suggestions"] = suggested_keywords
            return paginated_res

        serializer = MarketplaceProductSerializer(queryset, many=True, context={"request": request})
        return Response({
            "results": serializer.data,
            "total_count": total_count,
            "ai_search_enabled": use_ai_search,
            "ai_features": ai_features,
            "is_fallback": is_fallback,
            "fallback_reason": fallback_reason,
            "trending_suggestions": suggested_keywords,
        })


class ProductFacetsView(APIView):
    """
    Get available facet counts for products with current filters applied.
    Useful for building dynamic filter UI.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        from django.db.models import Max, Min

        from producer.models import MarketplaceProduct
        queryset = MarketplaceProduct.objects.filter(is_available=True)
        category_id = request.query_params.get("category_id")
        if category_id:
            try:
                cat_id = int(category_id)
                queryset = queryset.filter(product__category_id=cat_id)
            except (ValueError, TypeError):
                pass
        try:
            facets = FacetedSearchService.get_facet_counts(queryset)
        except Exception:
            facets = {}
        price_stats = queryset.aggregate(min_price=Min("listed_price"), max_price=Max("listed_price"))
        colors = list(queryset.values_list("color", flat=True).distinct().exclude(color__isnull=True))
        sizes = list(queryset.values_list("size", flat=True).distinct().exclude(size__isnull=True))

        return Response(
            {
                "facets": facets,
                "price_range": {"min": float(price_stats["min_price"] or 0), "max": float(price_stats["max_price"] or 0)},
                "available_colors": colors,
                "available_sizes": sizes,
            }
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def product_filter_options(request):
    """
    Get all available filter options and their possible values.
    Useful for building filter dropdowns and UI elements.
    """
    from producer.models import Brand, Category, MarketplaceProduct

    categories = list(Category.objects.filter(is_active=True).values("id", "name", "code"))
    brands = list(Brand.objects.filter(is_active=True).values("id", "name"))
    sizes = [{"value": choice[0], "label": choice[1]} for choice in MarketplaceProduct.SizeChoices.choices]

    from producer.search_utils import COLOR_ALIASES

    colors_with_aliases = []
    for color_value, color_label in MarketplaceProduct.ColorChoices.choices:
        color_lower = color_value.lower()
        aliases = COLOR_ALIASES.get(color_lower, [])
        colors_with_aliases.append(
            {"value": color_value, "label": color_label, "aliases": aliases, "normalized_value": color_lower}
        )

    price_ranges = [
        {"value": "budget", "label": "Under Rs.1,000", "min": 0, "max": 1000},
        {"value": "economy", "label": "Rs.1,000 - Rs.5,000", "min": 1000, "max": 5000},
        {"value": "mid", "label": "Rs.5,000 - Rs.15,000", "min": 5000, "max": 15000},
        {"value": "premium", "label": "Rs.15,000 - Rs.50,000", "min": 15000, "max": 50000},
        {"value": "luxury", "label": "Over Rs.50,000", "min": 50000, "max": None},
    ]

    stock_statuses = [
        {"value": "in_stock", "label": "In Stock"},
        {"value": "low_stock", "label": "Low Stock"},
        {"value": "out_of_stock", "label": "Out of Stock"},
    ]

    delivery_times = [
        {"value": "same_day", "label": "Same Day"},
        {"value": "1_day", "label": "1 Day"},
        {"value": "2_3_days", "label": "2-3 Days"},
        {"value": "1_week", "label": "Within 1 Week"},
    ]

    sort_options = [
        {"value": "relevance", "label": "Relevance (Default)", "description": "Most relevant results first"},
        {"value": "price_asc", "label": "Price: Low to High", "description": "Cheapest products first"},
        {"value": "price_desc", "label": "Price: High to Low", "description": "Most expensive products first"},
        {"value": "newest", "label": "Newest First", "description": "Recently added products"},
        {"value": "popular", "label": "Most Popular", "description": "Products with most views"},
        {"value": "rating", "label": "Highest Rated", "description": "Best reviewed products"},
        {"value": "discount", "label": "Biggest Discount", "description": "Products with highest discount %"},
        {"value": "name_asc", "label": "Name: A-Z", "description": "Alphabetical order"},
        {"value": "name_desc", "label": "Name: Z-A", "description": "Reverse alphabetical order"},
    ]

    return Response(
        {
            "categories": categories,
            "brands": brands,
            "sizes": sizes,
            "colors": colors_with_aliases,
            "price_ranges": price_ranges,
            "stock_statuses": stock_statuses,
            "delivery_times": delivery_times,
            "sort_options": sort_options,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def advanced_product_search(request):
    """
    POST endpoint for complex search queries with JSON body.
    """
    data = request.data
    filter_params = {}

    if "query" in data:
        filter_params["search"] = data["query"]
    if "category_id" in data:
        filter_params["category_id"] = data["category_id"]
    if "subcategory_id" in data:
        filter_params["subcategory_id"] = data["subcategory_id"]
    if "min_price" in data:
        filter_params["min_price"] = data["min_price"]
    if "max_price" in data:
        filter_params["max_price"] = data["max_price"]
    if "price_range" in data:
        filter_params["price_range"] = data["price_range"]
    if "min_rating" in data:
        filter_params["min_rating"] = data["min_rating"]
    if "min_reviews" in data:
        filter_params["min_reviews"] = data["min_reviews"]
    if "in_stock" in data:
        filter_params["in_stock"] = "true" if data["in_stock"] else "false"
    if "stock_status" in data:
        filter_params["stock_status"] = data["stock_status"]
    if "has_discount" in data:
        filter_params["has_discount"] = "true" if data["has_discount"] else "false"
    if "on_sale" in data:
        filter_params["on_sale"] = "true" if data["on_sale"] else "false"
    if "brands" in data:
        filter_params["brand_id"] = data["brands"]
    if "sizes" in data:
        filter_params["size"] = data["sizes"]
    if "colors" in data:
        filter_params["color"] = data["colors"]
    if "b2b_only" in data:
        filter_params["b2b_available"] = "true"
    if "sort_by" in data:
        filter_params["sort_by"] = data["sort_by"]
    if "near_me" in data:
        filter_params["near_me"] = data["near_me"]

    result = get_filtered_products_with_facets(filter_params)
    page_size = request.query_params.get("page_size", 20)

    paginator = PageNumberPagination()
    paginator.page_size = int(page_size)

    page_qs = paginator.paginate_queryset(result["products"], request)
    serializer = MarketplaceProductSerializer(page_qs, many=True, context={"request": request})

    return paginator.get_paginated_response(
        {"results": serializer.data, "facets": result["facets"], "total_count": result["total_count"]}
    )