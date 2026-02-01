from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .semantic_search import get_semantic_search_service
from .serializers import MarketplaceProductSerializer


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class SemanticSearchView(APIView):
    """
    Enhanced product search endpoint with query understanding.

    Query Parameters:
    - q: Search query (required)
    - category_id: Filter by category
    - brand_id: Filter by brand
    - min_price: Minimum price
    - max_price: Maximum price
    - in_stock: Only show in-stock items
    """

    permission_classes = [AllowAny]
    pagination_class = StandardResultsPagination

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if not query:
            return Response(
                {"error": 'Query parameter "q" is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build filters
        filters = {}
        if "category_id" in request.query_params:
            filters["category_id"] = int(request.query_params["category_id"])
        if "brand_id" in request.query_params:
            filters["brand_id"] = int(request.query_params["brand_id"])
        if "min_price" in request.query_params:
            filters["min_price"] = float(request.query_params["min_price"])
        if "max_price" in request.query_params:
            filters["max_price"] = float(request.query_params["max_price"])
        if request.query_params.get("in_stock", "").lower() == "true":
            filters["in_stock"] = True

        # Perform search
        try:
            service = get_semantic_search_service()
            results = service.search(query=query, k=50, filters=filters if filters else None)
        except Exception as e:
            return Response(
                {"error": f"Search failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Serialize results
        serialized_results = []
        for result in results["results"]:
            product_data = MarketplaceProductSerializer(result["product"], context={"request": request}).data

            serialized_results.append(
                {
                    "product": product_data,
                    "relevance_score": result["relevance_score"],
                    "keyword_score": result["keyword_score"],
                    "match_type": result["match_type"],
                }
            )

        # Paginate
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(serialized_results, request)

        if page is not None:
            return paginator.get_paginated_response(
                {
                    "results": page,
                    "query_info": {
                        "original_query": results["query"],
                        "intent": results["parsed_query"]["intent"],
                        "entities": results["parsed_query"]["entities"],
                        "keywords": results["parsed_query"]["keywords"],
                    },
                    "search_method": results["search_method"],
                    "total_found": results["total_found"],
                }
            )

        return Response(
            {
                "results": serialized_results,
                "query_info": {
                    "original_query": results["query"],
                    "intent": results["parsed_query"]["intent"],
                    "entities": results["parsed_query"]["entities"],
                },
                "search_method": results["search_method"],
                "total_found": results["total_found"],
            }
        )

    def post(self, request):
        """
        POST endpoint for complex search with JSON body.

        Request Body:
        {
            "query": "comfortable running shoes under 5000",
            "filters": {
                "category_id": 1,
                "in_stock": true
            }
        }
        """
        query = request.data.get("query", "").strip()

        if not query:
            return Response(
                {"error": "query field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filters = request.data.get("filters", {})

        try:
            service = get_semantic_search_service()
            results = service.search(query=query, k=50, filters=filters if filters else None)
        except Exception as e:
            return Response(
                {"error": f"Search failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Serialize and return
        serialized_results = []
        for result in results["results"]:
            product_data = MarketplaceProductSerializer(result["product"], context={"request": request}).data

            serialized_results.append(
                {
                    "product": product_data,
                    "relevance_score": result["relevance_score"],
                    "match_type": result["match_type"],
                }
            )

        return Response(
            {
                "results": serialized_results,
                "query_analysis": results["parsed_query"],
                "search_method": results["search_method"],
                "total_found": results["total_found"],
            }
        )


class SimilarProductsView(APIView):
    """
    Find products similar to a given product.

    URL Parameters:
    - product_id: The product to find similarities for

    Query Parameters:
    - limit: Number of similar products (default: 10, max: 20)
    """

    permission_classes = [AllowAny]

    def get(self, request, product_id):
        limit = min(int(request.query_params.get("limit", 10)), 20)

        try:
            service = get_semantic_search_service()
            similar = service.get_similar_products(product_id, k=limit)
        except Exception as e:
            return Response(
                {"error": f"Failed to find similar products: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Serialize
        results = []
        for item in similar:
            product_data = MarketplaceProductSerializer(item["product"], context={"request": request}).data

            results.append(
                {
                    "product": product_data,
                    "similarity_score": item["similarity_score"],
                }
            )

        return Response(
            {
                "product_id": product_id,
                "similar_products": results,
                "total_found": len(results),
            }
        )


class QueryUnderstandingView(APIView):
    """
    Analyze a search query to understand intent and entities.
    Useful for building advanced search UIs.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if not query:
            return Response(
                {"error": 'Query parameter "q" is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            service = get_semantic_search_service()
            parsed = service.query_service.parse_query(query)

            return Response(
                {
                    "original_query": parsed.original_query,
                    "normalized_query": parsed.normalized_query,
                    "intent": parsed.intent,
                    "entities": parsed.entities,
                    "keywords": parsed.keywords,
                    "expanded_queries": parsed.expanded_queries,
                }
            )
        except Exception as e:
            return Response(
                {"error": f"Query analysis failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["GET"])
@permission_classes([AllowAny])
def search_suggestions(request):
    """
    Get search suggestions as user types.

    Query Parameters:
    - q: Partial query string
    - limit: Number of suggestions (default: 5)
    """
    query = request.query_params.get("q", "").strip()
    limit = min(int(request.query_params.get("limit", 5)), 10)

    if len(query) < 2:
        return Response({"suggestions": []})

    # Get suggestions from products
    from producer.models import MarketplaceProduct

    # Product name suggestions (include product_id)
    name_matches = (
        MarketplaceProduct.objects.filter(product__name__icontains=query, is_available=True)
        .values("id", "product__name")
        .distinct()[:limit]
    )

    # Category suggestions
    from producer.models import Category

    category_matches = Category.objects.filter(name__icontains=query, is_active=True).values("id", "name")[:3]

    # Brand suggestions
    from producer.models import Brand

    brand_matches = Brand.objects.filter(name__icontains=query, is_active=True).values("id", "name")[:3]

    suggestions = []

    for item in name_matches:
        name = item["product__name"]
        suggestions.append(
            {
                "type": "product",
                "text": name,
                "highlighted": _highlight_match(name, query),
                "product_id": item["id"],
            }
        )

    for item in category_matches:
        cat = item["name"]
        suggestions.append(
            {
                "type": "category",
                "text": cat,
                "highlighted": _highlight_match(cat, query),
                "category_id": item["id"],
            }
        )

    for item in brand_matches:
        brand = item["name"]
        suggestions.append(
            {
                "type": "brand",
                "text": brand,
                "highlighted": _highlight_match(brand, query),
                "brand_id": item["id"],
            }
        )

    return Response({"query": query, "suggestions": suggestions[:limit]})


def _highlight_match(text: str, query: str) -> str:
    """Highlight matching portion of text"""
    import re

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(lambda m: f"<strong>{m.group()}</strong>", text)


@api_view(["POST"])
# @permission_classes([IsAuthenticated])
def natural_language_search(request):
    """
    Advanced natural language search with conversation context.

    Request Body:
    {
        "query": "I need comfortable office chairs for my team",
        "context": {
            "previous_searches": ["office furniture"],
            "user_preferences": {"max_price": 10000}
        }
    }
    """
    query = request.data.get("query", "").strip()
    context = request.data.get("context", {})

    if not query:
        return Response(
            {"error": "query is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        service = get_semantic_search_service()
        # Parse query with context
        parsed = service.query_service.parse_query(query)
        # Enhance with user preferences from context
        filters = {}
        if "user_preferences" in context:
            prefs = context["user_preferences"]
            if "max_price" in prefs:
                filters["max_price"] = prefs["max_price"]

        # Perform search
        results = service.search(query=query, k=20, filters=filters if filters else None)

        # Generate natural language response
        response_text = _generate_nl_response(query, results, parsed)

        return Response(
            {
                "query_understanding": {
                    "intent": parsed.intent,
                    "entities": parsed.entities,
                },
                "response": response_text,
                "results_count": len(results["results"]),
                "products": [
                    {
                        "product": MarketplaceProductSerializer(r["product"], context={"request": request}).data,
                        "relevance": r["relevance_score"],
                    }
                    for r in results["results"][:10]
                ],
            }
        )

    except Exception as e:
        return Response(
            {"error": f"Search failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _generate_nl_response(query: str, results: dict, parsed) -> str:
    """Generate a natural language response to the search query"""
    count = len(results["results"])

    if count == 0:
        return f"I couldn't find any products matching '{query}'. Try broadening your search or using different keywords."

    intent_responses = {
        "product_search": f"I found {count} products that match your search for '{query}'.",
        "comparison": f"Here are {count} products you can compare for '{query}'.",
        "question": f"Based on your question about '{query}', here are {count} relevant products.",
        "price_search": f"I found {count} products matching your price criteria for '{query}'.",
    }

    base_response = intent_responses.get(parsed.intent, f"Found {count} results for '{query}'.")

    # Add entity-specific additions
    if parsed.entities.get("price_constraints"):
        pc = parsed.entities["price_constraints"]
        if "descriptor" in pc:
            base_response += f" I've filtered for {pc['descriptor']} options."

    if parsed.entities.get("use_cases"):
        use_cases = parsed.entities["use_cases"]
        base_response += f" These are great for {', '.join(use_cases)}."

    return base_response
