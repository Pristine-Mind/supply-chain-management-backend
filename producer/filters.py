import django_filters
from django.db.models import Q

from user.models import UserProfile

from .models import Customer, MarketplaceProduct, Order, Producer, Product, Sale, Category, Subcategory, SubSubcategory


class ProducerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Producer
        fields = ["search"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(name__icontains=value).distinct()


class CustomerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Customer
        fields = ["search"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(name__icontains=value).distinct()


class SaleFilter(django_filters.FilterSet):
    customer = django_filters.ModelChoiceFilter(
        field_name="order__customer", queryset=Customer.objects.none(), label="Customer"
    )
    product = django_filters.ModelChoiceFilter(field_name="order__product", queryset=Product.objects.none(), label="Product")
    sale_date_from = django_filters.DateFilter(field_name="sale_date", lookup_expr="gte", label="Sale Date From")
    sale_date_to = django_filters.DateFilter(field_name="sale_date", lookup_expr="lte", label="Sale Date To")
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Sale
        fields = ["customer", "product", "sale_date_from", "sale_date_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.request
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            user_profile = getattr(user, "user_profile", None)
            if user_profile:
                self.filters["customer"].queryset = Customer.objects.filter(user__user_profile__shop_id=user_profile.shop_id)
                self.filters["product"].queryset = Product.objects.filter(user__user_profile__shop_id=user_profile.shop_id)
            else:
                self.filters["customer"].queryset = Customer.objects.none()
                self.filters["product"].queryset = Product.objects.none()

    def filter_search(self, queryset, name, value):
        """
        Custom filter to search by product name or customer name.
        """
        qs1 = queryset.filter(product__name__icontains=value)
        qs2 = queryset.filter(customer__name__icontains=value)
        return (qs1 | qs2).distinct()


class ProductFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")
    category = django_filters.MultipleChoiceFilter(
        choices=Product.ProductCategory.choices,
        field_name="category",
    )

    class Meta:
        model = Product
        fields = ["search", "category"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(name__icontains=value).distinct()


class MarketplaceProductFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")
    category = django_filters.CharFilter(method="filter_category", label="Category")
    category = django_filters.CharFilter(method="filter_category", label="Category")
    
    # New hierarchy filters
    category_id = django_filters.CharFilter(method="filter_category_id", label="Category ID")
    subcategory_id = django_filters.CharFilter(method="filter_subcategory_id", label="Subcategory ID")
    sub_subcategory_id = django_filters.CharFilter(method="filter_sub_subcategory_id", label="Sub-subcategory ID")
    city = django_filters.CharFilter(field_name="product__location__name", lookup_expr="exact")
    profile_type = django_filters.ChoiceFilter(
        choices=UserProfile.BusinessType.choices,
        field_name="product__user__user_profile__business_type",
        label="Profile Type",
    )

    class Meta:
        model = MarketplaceProduct
        fields = ["search", "category", "category_id", "subcategory_id", "sub_subcategory_id", "city", "profile_type"]

    def filter_search(self, queryset, name, value):
        if value:
            return queryset.filter(product__name__icontains=value).distinct()
        return queryset

    def filter_category(self, queryset, name, value):
        """Filter by category - supports both old codes (FA, EG, etc.) and new category names/codes"""
        if not value:
            return queryset
            
        try:
            # Try to parse as integer (new category ID)
            category_id = int(value)
            return queryset.filter(
                Q(product__category_id=category_id) |
                Q(product__subcategory__category_id=category_id) |
                Q(product__sub_subcategory__subcategory__category_id=category_id)
            )
        except ValueError:
            # Not an integer, treat as old category code or name
            if len(value) == 2 and value.isalpha() and value.isupper():
                # Old 2-letter category code (FA, EG, etc.)
                return queryset.filter(product__category__icontains=value)
            else:
                # Category name search
                return queryset.filter(
                    Q(product__category__name__icontains=value) |
                    Q(product__subcategory__name__icontains=value) |
                    Q(product__sub_subcategory__name__icontains=value)
                )

    def filter_category_id(self, queryset, name, value):
        """Filter by new category ID"""
        if not value:
            return queryset
        return queryset.filter(
            Q(product__category_id=value) |
            Q(product__subcategory__category_id=value) |
            Q(product__sub_subcategory__subcategory__category_id=value)
        )

    def filter_subcategory_id(self, queryset, name, value):
        """Filter by subcategory ID"""
        if not value:
            return queryset
        return queryset.filter(
            Q(product__subcategory_id=value) |
            Q(product__sub_subcategory__subcategory_id=value)
        )

    def filter_sub_subcategory_id(self, queryset, name, value):
        """Filter by sub-subcategory ID"""
        if not value:
            return queryset
        return queryset.filter(product__sub_subcategory_id=value)

class OrderFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")
    customer = django_filters.ModelChoiceFilter(field_name="customer", queryset=Customer.objects.none(), label="Customer")
    product = django_filters.ModelChoiceFilter(field_name="product", queryset=Product.objects.none(), label="Product")
    order_date_from = django_filters.DateFilter(field_name="order_date", lookup_expr="gte", label="Order Date From")
    order_date_to = django_filters.DateFilter(field_name="order_date", lookup_expr="lte", label="Order Date To")

    class Meta:
        model = Order
        fields = ["search", "customer", "product", "order_date_from", "order_date_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(self, "request", None)
        user = getattr(request, "user", None) if request else None
        if user and user.is_authenticated:
            user_profile = getattr(user, "user_profile", None)
            if user_profile:
                self.filters["customer"].queryset = Customer.objects.filter(user__user_profile__shop_id=user_profile.shop_id)
                self.filters["product"].queryset = Product.objects.filter(user__user_profile__shop_id=user_profile.shop_id)
            else:
                self.filters["customer"].queryset = Customer.objects.none()
                self.filters["product"].queryset = Product.objects.none()

    def filter_search(self, queryset, name, value):
        return queryset.filter(order_number__icontains=value).distinct()
