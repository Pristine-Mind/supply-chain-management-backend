"""
API Views for Advanced Product Filtering with Faceted Search
Enhanced with search relevance ranking, color normalization, and comprehensive filtering
"""

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

        # Get base queryset
        queryset = (
            MarketplaceProduct.objects.filter(is_available=True)
            .select_related("product", "product__user", "product__category")
            .prefetch_related("variants", "reviews")
        )

        # Get all query parameters
        search_query = request.query_params.get("q") or request.query_params.get("search", "").strip()
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

        has_search = search_query and len(search_query) >= 2
        if has_search:
            queryset = queryset.filter(
                Q(product__name__icontains=search_query)
                | Q(product__description__icontains=search_query)
                | Q(search_tags__contains=search_query.lower())
            ).distinct()

            # Annotate with relevance score
            relevance_case = build_relevance_score_case(search_query)
            queryset = queryset.annotate(relevance_score=relevance_case).filter(relevance_score__gt=0)
        else:
            queryset = queryset.annotate(relevance_score=Value(0, output_field=DecimalField()))

        queryset = queryset.annotate(
            avg_rating=Coalesce(Avg("reviews__rating"), Value(0), output_field=DecimalField()),
            num_reviews=Count("reviews", distinct=True),
        )

        if category_id:
            try:
                cat_id = int(category_id)
                queryset = queryset.filter(product__category_id=cat_id)
            except (ValueError, TypeError):
                pass

        if subcategory_id:
            try:
                subcat_id = int(subcategory_id)
                queryset = queryset.filter(product__subcategory_id=subcat_id)
            except (ValueError, TypeError):
                pass

        if sub_subcategory_id:
            try:
                subsubcat_id = int(sub_subcategory_id)
                queryset = queryset.filter(product__sub_subcategory_id=subsubcat_id)
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
                rating = Decimal(str(min_rating))
                queryset = queryset.filter(avg_rating__gte=rating)
            except (ValueError, TypeError):
                pass

        if delivery_days:
            try:
                days = int(delivery_days)
                queryset = queryset.filter(Q(estimated_delivery_days__isnull=True) | Q(estimated_delivery_days__lte=days))
            except (ValueError, TypeError):
                pass

        if brand_ids:
            try:
                brand_ids = [int(b) for b in brand_ids if b]
                if brand_ids:
                    queryset = queryset.filter(product__brand_id__in=brand_ids)
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
        elif sort_by == "price_asc" or sort_by == "price_low":
            queryset = (
                queryset.annotate(effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField()))
                .order_by("effective_price")
                .distinct()
            )
        elif sort_by == "price_desc" or sort_by == "price_high":
            queryset = (
                queryset.annotate(effective_price=Coalesce("discounted_price", "listed_price", output_field=DecimalField()))
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
        else:  # Default: relevance or newest
            if has_search:
                queryset = queryset.order_by("-relevance_score", "-avg_rating", "-view_count", "-listed_date").distinct()
            else:
                queryset = queryset.order_by("-listed_date", "-view_count").distinct()
        total_count = queryset.count()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        if page is not None:
            serializer = MarketplaceProductSerializer(page, many=True, context={"request": request})
            response_data = {
                "results": serializer.data,
                "total_count": total_count,
                "page_size": self.pagination_class.page_size,
            }
            return paginator.get_paginated_response(response_data)

        serializer = MarketplaceProductSerializer(queryset, many=True, context={"request": request})
        return Response(
            {
                "results": serializer.data,
                "total_count": total_count,
            }
        )


class ProductFacetsView(APIView):
    """
    Get available facet counts for products with current filters applied.
    Useful for building dynamic filter UI.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        from django.db.models import Max, Min

        from producer.models import MarketplaceProduct

        # Get base queryset
        queryset = MarketplaceProduct.objects.filter(is_available=True)

        # Apply category filters if specified
        category_id = request.query_params.get("category_id")
        if category_id:
            try:
                cat_id = int(category_id)
                queryset = queryset.filter(product__category_id=cat_id)
            except (ValueError, TypeError):
                pass

        # Get facet counts
        try:
            facets = FacetedSearchService.get_facet_counts(queryset)
        except Exception:
            facets = {}

        # Get price range
        price_stats = queryset.aggregate(min_price=Min("listed_price"), max_price=Max("listed_price"))

        # Get available colors
        colors = list(queryset.values_list("color", flat=True).distinct().exclude(color__isnull=True))

        # Get available sizes
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

    Returns:
    - categories: All active categories
    - brands: All active brands
    - sizes: All available size options
    - colors: All available colors with normalization info
    - price_ranges: Predefined price ranges for quick filtering
    - stock_statuses: Available stock status options
    - delivery_times: Available delivery time slots
    - sort_options: Available sorting methods
    """
    from producer.models import Brand, Category, MarketplaceProduct

    # Categories
    categories = list(Category.objects.filter(is_active=True).values("id", "name", "code"))

    # Brands
    brands = list(Brand.objects.filter(is_active=True).values("id", "name"))

    # Size options
    sizes = [{"value": choice[0], "label": choice[1]} for choice in MarketplaceProduct.SizeChoices.choices]

    # Color options with normalization info
    from producer.search_utils import COLOR_ALIASES

    colors_with_aliases = []
    for color_value, color_label in MarketplaceProduct.ColorChoices.choices:
        color_lower = color_value.lower()
        aliases = COLOR_ALIASES.get(color_lower, [])
        colors_with_aliases.append(
            {"value": color_value, "label": color_label, "aliases": aliases, "normalized_value": color_lower}
        )

    # Price ranges
    price_ranges = [
        {"value": "budget", "label": "Under Rs.1,000", "min": 0, "max": 1000},
        {"value": "economy", "label": "Rs.1,000 - Rs.5,000", "min": 1000, "max": 5000},
        {"value": "mid", "label": "Rs.5,000 - Rs.15,000", "min": 5000, "max": 15000},
        {"value": "premium", "label": "Rs.15,000 - Rs.50,000", "min": 15000, "max": 50000},
        {"value": "luxury", "label": "Over Rs.50,000", "min": 50000, "max": None},
    ]

    # Stock status options
    stock_statuses = [
        {"value": "in_stock", "label": "In Stock"},
        {"value": "low_stock", "label": "Low Stock"},
        {"value": "out_of_stock", "label": "Out of Stock"},
    ]

    # Delivery time options
    delivery_times = [
        {"value": "same_day", "label": "Same Day"},
        {"value": "1_day", "label": "1 Day"},
        {"value": "2_3_days", "label": "2-3 Days"},
        {"value": "1_week", "label": "Within 1 Week"},
    ]

    # Sort options with descriptions
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
    Useful for advanced search forms.
    """
    data = request.data

    # Convert JSON body to filter params
    filter_params = {}

    # Text search
    if "query" in data:
        filter_params["search"] = data["query"]

    # Category filters
    if "category_id" in data:
        filter_params["category_id"] = data["category_id"]
    if "subcategory_id" in data:
        filter_params["subcategory_id"] = data["subcategory_id"]

    # Price filters
    if "min_price" in data:
        filter_params["min_price"] = data["min_price"]
    if "max_price" in data:
        filter_params["max_price"] = data["max_price"]
    if "price_range" in data:
        filter_params["price_range"] = data["price_range"]

    # Rating filters
    if "min_rating" in data:
        filter_params["min_rating"] = data["min_rating"]
    if "min_reviews" in data:
        filter_params["min_reviews"] = data["min_reviews"]

    # Availability
    if "in_stock" in data:
        filter_params["in_stock"] = "true" if data["in_stock"] else "false"
    if "stock_status" in data:
        filter_params["stock_status"] = data["stock_status"]

    # Offers
    if "has_discount" in data:
        filter_params["has_discount"] = "true" if data["has_discount"] else "false"
    if "on_sale" in data:
        filter_params["on_sale"] = "true" if data["on_sale"] else "false"

    # Attributes
    if "brands" in data:
        filter_params["brand_id"] = data["brands"]
    if "sizes" in data:
        filter_params["size"] = data["sizes"]
    if "colors" in data:
        filter_params["color"] = data["colors"]

    # B2B
    if "b2b_only" in data:
        filter_params["b2b_available"] = "true"

    # Sort
    if "sort_by" in data:
        filter_params["sort_by"] = data["sort_by"]

    # Location
    if "near_me" in data:
        filter_params["near_me"] = data["near_me"]

    # Get results
    result = get_filtered_products_with_facets(filter_params)

    # Serialize
    page_size = request.query_params.get("page_size", 20)

    paginator = PageNumberPagination()
    paginator.page_size = int(page_size)

    page_qs = paginator.paginate_queryset(result["products"], request)
    serializer = MarketplaceProductSerializer(page_qs, many=True, context={"request": request})

    return paginator.get_paginated_response(
        {"results": serializer.data, "facets": result["facets"], "total_count": result["total_count"]}
    )
