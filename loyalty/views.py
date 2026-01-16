from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import LoyaltyTier, UserLoyalty
from .serializers import (
    LoyaltyTierSerializer,
    LoyaltyTransactionSerializer,
    RedeemPointsSerializer,
    UserLoyaltySerializer,
    UserLoyaltySummarySerializer,
)
from .services import (
    LoyaltyService,
)


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for lists."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class IsAdminUser(permissions.BasePermission):
    """Permission class for admin-only endpoints."""

    def has_permission(self, request, view):
        return request.user and request.user.is_staff


class LoyaltyTierViewSet(viewsets.ReadOnlyModelViewSet):

    serializer_class = LoyaltyTierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return LoyaltyTier.objects.filter(is_active=True).prefetch_related("perks")


class UserLoyaltyViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserLoyaltySerializer

    def list(self, request, *args, **kwargs):
        return self.status(request)

    def get_object(self):
        obj, created = UserLoyalty.objects.select_related("tier").get_or_create(
            user=self.request.user, defaults={"is_active": True}
        )
        return obj

    @action(detail=False, methods=["get"])
    def status(self, request):
        instance = self.get_object()
        serializer = UserLoyaltySerializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        summary = LoyaltyService.get_user_summary(request.user)
        serializer = UserLoyaltySummarySerializer(summary)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def transactions(self, request):
        instance = self.get_object()
        transactions = instance.transactions.all()

        transaction_type = request.query_params.get("type")
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(transactions, request)

        if page is not None:
            serializer = LoyaltyTransactionSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = LoyaltyTransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def redeem(self, request):
        serializer = RedeemPointsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        points = serializer.validated_data["points"]
        description = serializer.validated_data["description"]
        reference_id = serializer.validated_data.get("reference_id")

        try:
            success, message, transaction = LoyaltyService.redeem_points(
                user=request.user, points=points, description=description, reference_id=reference_id, created_by=request.user
            )

            if success:
                return Response(
                    {
                        "success": True,
                        "message": message,
                        "transaction": LoyaltyTransactionSerializer(transaction).data,
                        "remaining_points": UserLoyalty.objects.get(user=request.user).points,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response({"success": False, "error": message}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def perks(self, request):
        perks = LoyaltyService.get_user_perks(request.user)
        from .serializers import LoyaltyPerkSerializer

        serializer = LoyaltyPerkSerializer(perks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def has_perk(self, request):
        perk_code = request.query_params.get("code")

        if not perk_code:
            return Response({"error": "Perk code is required"}, status=status.HTTP_400_BAD_REQUEST)

        has_perk = LoyaltyService.has_perk(request.user, perk_code)

        return Response({"has_perk": has_perk, "perk_code": perk_code})
