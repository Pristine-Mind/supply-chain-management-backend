from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .trending_utils import TrendingProductUtils


@api_view(["POST"])
@permission_classes([AllowAny])
def track_product_view(request):
    """
    API endpoint to track product views for trending calculations

    POST data:
    {
        "product_id": 123,
        "user_id": 456  # optional
    }
    """
    product_id = request.data.get("product_id")
    user_id = request.data.get("user_id")

    if not product_id:
        return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        success = TrendingProductUtils.update_product_view_count(product_id, user_id)
        if success:
            return Response(
                {"message": "Product view tracked successfully", "product_id": product_id}, status=status.HTTP_200_OK
            )
        else:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": f"Error tracking product view: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([AllowAny])
def trending_summary(request):
    """
    Get a quick summary of trending products statistics
    """
    try:
        summary = TrendingProductUtils.get_trending_summary()
        return Response(summary, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error getting trending summary: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
