import django_filters

from .models import Bid, ChatMessage


class BidFilter(django_filters.FilterSet):
    product = django_filters.CharFilter(field_name="product_id", lookup_expr="exact")
    bidder = django_filters.NumberFilter(field_name="bidder__id", lookup_expr="exact")

    class Meta:
        model = Bid
        fields = ["product", "bidder"]


class UserBidFilter(django_filters.FilterSet):
    product = django_filters.CharFilter(field_name="product__product__name", lookup_expr="icontains")
    bidder = django_filters.NumberFilter(field_name="bidder__id", lookup_expr="exact")

    class Meta:
        model = Bid
        fields = ["product"]


class ChatFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product__id", lookup_expr="exact")

    class Meta:
        model = ChatMessage
        fields = ["product"]
