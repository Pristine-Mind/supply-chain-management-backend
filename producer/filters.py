import django_filters
from .models import Sale, Producer, Customer, Product, MarketplaceProduct


class ProducerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    class Meta:
        model = Producer
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            name__icontains=value
        ).distinct()


class CustomerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    class Meta:
        model = Customer
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            name__icontains=value
        ).distinct()


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


class ProductFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    class Meta:
        model = Product
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            name__icontains=value
        ).distinct()


class MarketplaceProductFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    class Meta:
        model = MarketplaceProduct
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            product__name__icontains=value
        ).distinct()
