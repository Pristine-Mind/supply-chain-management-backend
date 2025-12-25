from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from producer.models import Product


class B2BUserProductsSerializer(serializers.ModelSerializer):
    """Serializer to return B2B-verified user info along with their marketplace products."""

    registered_business_name = serializers.CharField(source="user_profile.registered_business_name", read_only=True)
    business_type = serializers.CharField(source="user_profile.business_type", read_only=True)
    # products = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "registered_business_name",
            "business_type",
            # "products",
        ]

    def get_products(self, obj):
        from producer.serializers import MiniProductSerializer

        prefetched = getattr(obj, "prefetched_products", None)
        if prefetched is not None:
            products = prefetched
        else:
            from producer.models import Product

            products = Product.objects.filter(user=obj, is_active=True)

        request = self.context.get("request")
        return MiniProductSerializer(products, many=True, context={"request": request}).data


class B2BVerifiedUsersProductsView(viewsets.ReadOnlyModelViewSet):
    """List and search users who are B2B verified and include their products."""

    permission_classes = (AllowAny,)
    serializer_class = B2BUserProductsSerializer

    def get_queryset(self):
        q = (self.request.query_params.get("q") or "").strip()
        qs = User.objects.filter(user_profile__b2b_verified=True)
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(user_profile__registered_business_name__icontains=q)
                | Q(user_profile__business_type__icontains=q)
            )
        # Prefetch related Product objects and a few useful relations to avoid N+1 queries
        try:
            from producer.models import Product

            product_qs = Product.objects.filter(is_active=True).select_related("brand").prefetch_related("images")
            qs = (
                qs.select_related("user_profile")
                .prefetch_related(Prefetch("product_set", queryset=product_qs, to_attr="prefetched_products"))
                .order_by("username")
            )
        except Exception:
            qs = qs.select_related("user_profile").order_by("username")

        return qs

    @action(detail=True, methods=["get"], url_path="products")
    def products(self, request, *args, **kwargs):
        """Return paginated products for this B2B-verified user (detail action)."""
        from producer.models import Product
        from producer.serializers import MiniProductSerializer

        user = self.get_object()

        products = getattr(user, "prefetched_products", None)
        if products is None:
            products = Product.objects.filter(user=user, is_active=True).select_related("brand").prefetch_related("images")

        q = (request.query_params.get("q") or "").strip()
        if q:
            try:
                products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
            except Exception:
                products = [p for p in products if q.lower() in (p.name or "").lower() or q.lower() in (p.sku or "").lower()]

        page = self.paginate_queryset(products)
        serializer = MiniProductSerializer(page or products, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get", "post"],
        url_path=r"products/(?P<product_id>[^/.]+)/chat",
        permission_classes=[IsAuthenticated],
    )
    def product_chat(self, request, product_id=None, *args, **kwargs):
        """List or create chat messages for a specific product of this B2B user."""
        # Use ProductChatMessage (tied to producer.Product) for B2B product chats
        from market.serializers import ProductChatMessageSerializer

        user = self.get_object()
        # Ensure the base Product belongs to the B2B user
        product = get_object_or_404(Product, id=product_id, user=user)

        # List product-level chats tied to the base Product
        if request.method == "GET":
            from market.models import ProductChatMessage

            qs = ProductChatMessage.objects.filter(product=product).select_related("sender").all().order_by("-timestamp")
            page = self.paginate_queryset(qs)
            serializer = ProductChatMessageSerializer(page or qs, many=True, context={"request": request})
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return Response(serializer.data)

        # POST - create a new product-level chat message
        data = request.data.copy()
        data["product"] = product.id
        serializer = ProductChatMessageSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        chat = serializer.save()
        return Response(ProductChatMessageSerializer(chat, context={"request": request}).data, status=201)
