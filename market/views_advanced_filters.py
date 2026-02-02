"""
API Views for Advanced Product Filtering with Faceted Search
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .advanced_filters import (
    AdvancedMarketplaceProductFilter,
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
    Advanced product search with faceted filtering.

    Query Parameters:
    - search: Text search across product name, description, tags
    - category_id, subcategory_id, sub_subcategory_id: Category filters
    - brand_id: Filter by brand (can be multiple: brand_id=1&brand_id=2)
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
    - size, color: Product attributes
    - b2b_available: true/false
    - sort_by: price_asc, price_desc, newest, popular, rating, name_asc, name_desc, discount
    - near_me: lat,lng,radius_km (e.g., 27.7172,85.3240,10)
    """

    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        # Get all query parameters
        filter_params = request.query_params.dict()

        # Handle multiple values for brand_id
        brand_ids = request.query_params.getlist("brand_id")
        if brand_ids:
            filter_params["brand_id"] = brand_ids

        # Handle multiple values for size and color
        sizes = request.query_params.getlist("size")
        if sizes:
            filter_params["size"] = sizes

        colors = request.query_params.getlist("color")
        if colors:
            filter_params["color"] = colors

        # Get filtered results with facets
        result = get_filtered_products_with_facets(filter_params)

        if not result["is_valid"]:
            return Response(
                {"error": "Invalid filter parameters", "details": result["errors"]}, status=status.HTTP_400_BAD_REQUEST
            )

        # Paginate results
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(result["products"], request)

        if page is not None:
            serializer = MarketplaceProductSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(
                {"results": serializer.data, "facets": result["facets"], "total_count": result["total_count"]}
            )

        serializer = MarketplaceProductSerializer(result["products"], many=True, context={"request": request})

        return Response({"results": serializer.data, "facets": result["facets"], "total_count": result["total_count"]})


class ProductFacetsView(APIView):
    """
    Get available facet counts for products.
    Useful for building filter UI.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Get base queryset (can be filtered by category, etc.)
        from producer.models import MarketplaceProduct

        queryset = MarketplaceProduct.objects.filter(is_available=True)

        # Apply any base filters from query params
        category_id = request.query_params.get("category_id")
        if category_id:
            queryset = queryset.filter(product__category_id=category_id)

        facets = FacetedSearchService.get_facet_counts(queryset)

        # Add min/max price info
        from django.db.models import Max, Min

        price_stats = queryset.aggregate(min_price=Min("listed_price"), max_price=Max("listed_price"))

        return Response(
            {"facets": facets, "price_range": {"min": price_stats["min_price"] or 0, "max": price_stats["max_price"] or 0}}
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def product_filter_options(request):
    """
    Get all available filter options and their possible values.
    Useful for building filter dropdowns.
    """
    from producer.models import Brand, Category, MarketplaceProduct

    # Categories
    categories = list(Category.objects.filter(is_active=True).values("id", "name", "code"))

    # Brands
    brands = list(Brand.objects.filter(is_active=True).values("id", "name"))

    # Size options
    sizes = [{"value": choice[0], "label": choice[1]} for choice in MarketplaceProduct.SizeChoices.choices]

    # Color options
    colors = [{"value": choice[0], "label": choice[1]} for choice in MarketplaceProduct.ColorChoices.choices]

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

    # Sort options
    sort_options = [
        {"value": "relevance", "label": "Relevance"},
        {"value": "price_asc", "label": "Price: Low to High"},
        {"value": "price_desc", "label": "Price: High to Low"},
        {"value": "newest", "label": "Newest First"},
        {"value": "popular", "label": "Most Popular"},
        {"value": "rating", "label": "Highest Rated"},
        {"value": "discount", "label": "Biggest Discount"},
    ]

    return Response(
        {
            "categories": categories,
            "brands": brands,
            "sizes": sizes,
            "colors": colors,
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
    page = request.query_params.get("page", 1)
    page_size = request.query_params.get("page_size", 20)

    from rest_framework.pagination import PageNumberPagination

    paginator = PageNumberPagination()
    paginator.page_size = int(page_size)

    page_qs = paginator.paginate_queryset(result["products"], request)
    serializer = MarketplaceProductSerializer(page_qs, many=True, context={"request": request})

    return paginator.get_paginated_response(
        {"results": serializer.data, "facets": result["facets"], "total_count": result["total_count"]}
    )
