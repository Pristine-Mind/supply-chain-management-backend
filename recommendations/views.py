from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .engine.hybrid import get_hybrid_recommendations


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def business_recommendations(request):
    recommended_users = get_hybrid_recommendations(request.user, limit=20)
    results = []
    for user in recommended_users:
        profile = user.user_profile
        results.append(
            {
                "user_id": user.id,
                "business_name": profile.registered_business_name or user.username,
                "business_type": profile.get_business_type_display(),
                "location": profile.location.name if profile.location else None,
                "has_active_products": user.product_set.filter(is_active=True).exists(),
            }
        )
    return Response(results)
