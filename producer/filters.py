import django_filters
from .models import Sale, Producer, Customer, Product, MarketplaceProduct, Order


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
    category = django_filters.MultipleChoiceFilter(
        choices=Product.ProductCategory.choices,
        field_name='category',
    )

    class Meta:
        model = Product
        fields = ['search', 'category']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            name__icontains=value
        ).distinct()


class MarketplaceProductFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")
    category = django_filters.MultipleChoiceFilter(
        choices=Product.ProductCategory.choices,
        field_name='product__category',
    )

    class Meta:
        model = MarketplaceProduct
        fields = ['search', 'category']

    def filter_search(self, queryset, name, value):
        if value:
            return queryset.filter(
                product__name__icontains=value
            ).distinct()
        return queryset

    def filter_category(self, queryset, name, value):
        if value:
            return queryset.filter(
                product__category=value
            ).distinct()
        return queryset


class OrderFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")
    customer = django_filters.NumberFilter(field_name="customer__id", lookup_expr='exact')
    product = django_filters.NumberFilter(field_name="product__id", lookup_expr='exact')

    class Meta:
        model = Order
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            order_number__icontains=value
        ).distinct()
