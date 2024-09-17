import django_filters
from .models import Bid, ChatMessage


class BidFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product__id", lookup_expr="exact")

    class Meta:
        model = Bid
        fields = ["product"]


class ChatFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product__id", lookup_expr="exact")

    class Meta:
        model = ChatMessage
        fields = ["product"]
