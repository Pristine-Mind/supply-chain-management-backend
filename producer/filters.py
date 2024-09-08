import django_filters
from .models import Sale


class SaleFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer__id", lookup_expr='exact')
    product = django_filters.NumberFilter(field_name="product__id", lookup_expr='exact')
    search = django_filters.CharFilter(method='filter_search', label="Search")

    class Meta:
        model = Sale
        fields = ['customer', 'product']

    def filter_search(self, queryset, name, value):
        """
        Custom filter to search by product name or customer name.
        """
        return queryset.filter(
            product__name__icontains=value
        ) | queryset.filter(
            customer__name__icontains=value
        ).distinct()
