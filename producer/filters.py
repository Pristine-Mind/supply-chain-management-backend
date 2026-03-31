from decimal import Decimal

import django_filters
from django import models
from django.db.models import Coalesce, Count, DecimalField, Q

from user.models import UserProfile

from .models import (
    Brand,
    Category,
    Customer,
    MarketplaceProduct,
    Order,
    Producer,
    Product,
    Sale,
    Subcategory,
    SubSubcategory,
)


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
    category = django_filters.CharFilter(method="filter_category", label="Category")
    category_id = django_filters.CharFilter(method="filter_category_id", label="Category ID")
    subcategory_id = django_filters.CharFilter(method="filter_subcategory_id", label="Subcategory ID")
    sub_subcategory_id = django_filters.CharFilter(method="filter_sub_subcategory_id", label="Sub-subcategory ID")
    size = django_filters.MultipleChoiceFilter(choices=Product.SizeChoices.choices, field_name="size", label="Size")
    color = django_filters.MultipleChoiceFilter(choices=Product.ColorChoices.choices, field_name="color", label="Color")
    has_additional_info = django_filters.BooleanFilter(
        method="filter_has_additional_info", label="Has Additional Information"
    )

    class Meta:
        model = Product
        fields = ["search", "category", "size", "color", "has_additional_info"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(name__icontains=value).distinct()

    def filter_category(self, queryset, name, value):
        """Filter by category - supports both old codes (HL, FA, etc.) and new category IDs"""
        if not value:
            return queryset

        try:
            # Try to parse as integer (new category ID)
            category_id = int(value)
            return queryset.filter(
                Q(category_id=category_id)
                | Q(subcategory__category_id=category_id)
                | Q(sub_subcategory__subcategory__category_id=category_id)
            )
        except ValueError:
            # Not an integer, treat as category code
            if len(value) == 2 and value.isalpha() and value.isupper():
                # New category code (HL, FA, etc.) - filter by category code
                return queryset.filter(
                    Q(category__code=value)
                    | Q(subcategory__category__code=value)
                    | Q(sub_subcategory__subcategory__category__code=value)
                )
            else:
                # Old 2-letter legacy category code - filter by old_category field
                return queryset.filter(old_category=value)

    def filter_has_additional_info(self, queryset, name, value):
        if value is True:
            return queryset.exclude(additional_information__isnull=True).exclude(additional_information__exact="")
        elif value is False:
            return queryset.filter(Q(additional_information__isnull=True) | Q(additional_information__exact=""))
        return queryset


class MarketplaceProductFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")
    category = django_filters.CharFilter(method="filter_category", label="Category")

    # New hierarchy filters
    category_id = django_filters.CharFilter(method="filter_category_id", label="Category ID")
    subcategory_id = django_filters.CharFilter(method="filter_subcategory_id", label="Subcategory ID")
    sub_subcategory_id = django_filters.CharFilter(method="filter_sub_subcategory_id", label="Sub-subcategory ID")
    city = django_filters.CharFilter(method="filter_city", label="City")
    profile_type = django_filters.ChoiceFilter(
        choices=UserProfile.BusinessType.choices,
        field_name="product__user__user_profile__business_type",
        label="Profile Type",
    )
    is_made_in_nepal = django_filters.BooleanFilter(
        field_name="is_made_in_nepal",
        label="Made in Nepal",
    )
    made_for_you = django_filters.BooleanFilter(
        field_name="made_for_you",
        label="Made For You",
    )

    # Size and color filters with effective value support
    size = django_filters.MultipleChoiceFilter(
        choices=MarketplaceProduct.SizeChoices.choices, method="filter_size", label="Size"
    )
    color = django_filters.MultipleChoiceFilter(
        choices=MarketplaceProduct.ColorChoices.choices, method="filter_color", label="Color"
    )
    has_additional_info = django_filters.BooleanFilter(
        method="filter_has_additional_info", label="Has Additional Information"
    )

    # Price range filters
    min_price = django_filters.NumberFilter(method="filter_min_price", label="Minimum Price")
    max_price = django_filters.NumberFilter(method="filter_max_price", label="Maximum Price")

    # Rating filter
    min_rating = django_filters.NumberFilter(method="filter_min_rating", label="Minimum Rating")

    # Delivery time filter
    delivery_days = django_filters.NumberFilter(method="filter_delivery_days", label="Delivery Days")

    class Meta:
        model = MarketplaceProduct
        fields = [
            "search",
            "category",
            "category_id",
            "subcategory_id",
            "sub_subcategory_id",
            "city",
            "profile_type",
            "is_made_in_nepal",
            "made_for_you",
            "size",
            "color",
            "has_additional_info",
            "min_price",
            "max_price",
            "min_rating",
            "delivery_days",
        ]

    def filter_search(self, queryset, name, value):
        """Enhanced search with case-insensitive matching"""
        if not value:
            return queryset

        # Import search utilities
        from django.db.models import DecimalField, F

        from producer.search_utils import SearchFilter, build_relevance_score_case

        # Apply search with relevance ranking
        queryset = queryset.filter(Q(product__name__icontains=value) | Q(product__description__icontains=value)).distinct()

        # Annotate with relevance score
        relevance_case = build_relevance_score_case(value)
        queryset = queryset.annotate(relevance_score=relevance_case).filter(relevance_score__gt=0)

        # Sort by relevance, then by rating and popularity
        queryset = queryset.order_by("-relevance_score", "-average_rating", "-view_count", "-listed_date")

        return queryset

    def filter_city(self, queryset, name, value):
        """Enhanced city filter with case-insensitive matching"""
        if not value:
            return queryset

        # Try as city ID first
        try:
            city_id = int(value)
            return queryset.filter(Q(product__location__id=city_id) | Q(product__user__user_profile__city__id=city_id))
        except (ValueError, TypeError):
            # Fall back to city name (case-insensitive)
            return queryset.filter(
                Q(product__location__name__iexact=value) | Q(product__user__user_profile__city__name__iexact=value)
            )

    def filter_category(self, queryset, name, value):
        """Filter by category - supports both old codes (FA, EG, etc.) and new category names/codes"""
        if not value:
            return queryset

        try:
            # Try to parse as integer (new category ID)
            category_id = int(value)
            return queryset.filter(
                Q(product__category_id=category_id)
                | Q(product__subcategory__category_id=category_id)
                | Q(product__sub_subcategory__subcategory__category_id=category_id)
            )
        except ValueError:
            # Not an integer, treat as category code or name
            if len(value) == 2 and value.isalpha() and value.isupper():
                # New category code (HL, FA, etc.) - filter by category code
                return queryset.filter(
                    Q(product__category__code=value)
                    | Q(product__subcategory__category__code=value)
                    | Q(product__sub_subcategory__subcategory__category__code=value)
                )
            else:
                # Category name search or old legacy codes
                return queryset.filter(
                    Q(product__category__name__icontains=value)
                    | Q(product__subcategory__name__icontains=value)
                    | Q(product__sub_subcategory__name__icontains=value)
                    | Q(product__old_category=value)  # Support for old legacy category codes
                )

    def filter_category_id(self, queryset, name, value):
        """Filter by new category ID"""
        if not value:
            return queryset
        return queryset.filter(
            Q(product__category_id=value)
            | Q(product__subcategory__category_id=value)
            | Q(product__sub_subcategory__subcategory__category_id=value)
        )

    def filter_subcategory_id(self, queryset, name, value):
        """Filter by subcategory ID"""
        if not value:
            return queryset
        return queryset.filter(Q(product__subcategory_id=value) | Q(product__sub_subcategory__subcategory_id=value))

    def filter_sub_subcategory_id(self, queryset, name, value):
        """Filter by sub-subcategory ID"""
        if not value:
            return queryset
        return queryset.filter(product__sub_subcategory_id=value)

    def filter_size(self, queryset, name, value):
        """Filter by size - checks both marketplace and product size with case normalization"""
        if not value:
            return queryset
        # Filter by marketplace size or inherited product size (case-insensitive)
        size_q = Q()
        for size in value:
            size_q |= Q(size__iexact=size) | Q(size__isnull=True, product__size__iexact=size)
        return queryset.filter(size_q).distinct()

    def filter_color(self, queryset, name, value):
        """Filter by color with normalization"""
        if not value:
            return queryset

        # Import normalization function
        from producer.search_utils import normalize_color

        # Normalize all input colors
        normalized_colors = [normalize_color(c) for c in value]
        normalized_colors = [c for c in normalized_colors if c]

        if not normalized_colors:
            return queryset

        # Create filter for marketplace color or product color
        color_filter = Q()
        for color in normalized_colors:
            color_filter |= Q(color__iexact=color) | Q(product__color__iexact=color)

        return queryset.filter(color_filter).distinct()

    def filter_min_price(self, queryset, name, value):
        """Filter products with minimum price"""
        if not value:
            return queryset

        try:
            min_val = Decimal(str(value))
            queryset = queryset.filter(Coalesce("discounted_price", "listed_price", output_field=DecimalField()) >= min_val)
        except (ValueError, TypeError):
            pass

        return queryset

    def filter_max_price(self, queryset, name, value):
        """Filter products with maximum price"""
        if not value:
            return queryset

        try:
            max_val = Decimal(str(value))
            queryset = queryset.filter(Coalesce("discounted_price", "listed_price", output_field=DecimalField()) <= max_val)
        except (ValueError, TypeError):
            pass

        return queryset

    def filter_min_rating(self, queryset, name, value):
        """Filter products with minimum rating"""
        if not value:
            return queryset

        try:
            min_rating = Decimal(str(value))
            queryset = queryset.filter(average_rating__gte=min_rating)
        except (ValueError, TypeError):
            pass

        return queryset

    def filter_delivery_days(self, queryset, name, value):
        """Filter products by maximum delivery days"""
        if not value:
            return queryset

        try:
            days = int(value)
            queryset = queryset.filter(Q(estimated_delivery_days__isnull=True) | Q(estimated_delivery_days__lte=days))
        except (ValueError, TypeError):
            pass

        return queryset

    def filter_has_additional_info(self, queryset, name, value):
        """Filter by presence of additional information"""
        if value is True:
            return queryset.filter(
                Q(additional_information__isnull=False, additional_information__gt="")
                | Q(
                    additional_information__isnull=True,
                    product__additional_information__isnull=False,
                    product__additional_information__gt="",
                )
                | Q(
                    additional_information="",
                    product__additional_information__isnull=False,
                    product__additional_information__gt="",
                )
            )
        elif value is False:
            return queryset.filter(
                Q(additional_information__isnull=True, product__additional_information__isnull=True)
                | Q(additional_information="", product__additional_information__isnull=True)
                | Q(additional_information__isnull=True, product__additional_information="")
                | Q(additional_information="", product__additional_information="")
            )
        return queryset


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


class BrandFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Search")
    is_verified = django_filters.BooleanFilter(field_name="is_verified", label="Is Verified")
    country = django_filters.CharFilter(field_name="country_of_origin", lookup_expr="icontains", label="Country")
    has_products = django_filters.BooleanFilter(method="filter_has_products", label="Has Products")
    category = django_filters.CharFilter(method="filter_category", label="Category")
    min_product_count = django_filters.NumberFilter(method="filter_min_product_count", label="Minimum Product Count")

    class Meta:
        model = Brand
        fields = [
            "search",
            "is_verified",
            "country",
            "has_products",
            "category",
            "category_id",
            "subcategory_id",
            "sub_subcategory_id",
            "min_product_count",
        ]

    def filter_search(self, queryset, name, value):
        """Search brands by name or product names"""
        if not value:
            return queryset

        return queryset.filter(Q(products__name__icontains=value) | Q(products__description__icontains=value)).distinct()

    def filter_has_products(self, queryset, name, value):
        """Filter brands that have or don't have products"""
        if value is True:
            return queryset.filter(products__isnull=False).distinct()
        elif value is False:
            return queryset.filter(products__isnull=True)
        return queryset

    def filter_category(self, queryset, name, value):
        """Filter brands by product category"""
        if not value:
            return queryset

        try:
            # Try to parse as integer (category ID)
            category_id = int(value)
            return queryset.filter(
                Q(products__category_id=category_id)
                | Q(products__subcategory__category_id=category_id)
                | Q(products__sub_subcategory__subcategory__category_id=category_id)
            ).distinct()
        except ValueError:
            # Not an integer, treat as category code or name
            if len(value) == 2 and value.isalpha() and value.isupper():
                # Category code (HL, FA, etc.)
                return queryset.filter(
                    Q(products__category__code=value)
                    | Q(products__subcategory__category__code=value)
                    | Q(products__sub_subcategory__subcategory__category__code=value)
                ).distinct()
            else:
                # Category name search
                return queryset.filter(
                    Q(products__category__name__icontains=value)
                    | Q(products__subcategory__name__icontains=value)
                    | Q(products__sub_subcategory__name__icontains=value)
                ).distinct()

    def filter_category_id(self, queryset, name, value):
        """Filter brands by new category ID"""
        if not value:
            return queryset
        return queryset.filter(
            Q(products__category_id=value)
            | Q(products__subcategory__category_id=value)
            | Q(products__sub_subcategory__subcategory__category_id=value)
        ).distinct()

    def filter_subcategory_id(self, queryset, name, value):
        """Filter brands by subcategory ID"""
        if not value:
            return queryset
        return queryset.filter(
            Q(products__subcategory_id=value) | Q(products__sub_subcategory__subcategory_id=value)
        ).distinct()

    def filter_sub_subcategory_id(self, queryset, name, value):
        """Filter brands by sub-subcategory ID"""
        if not value:
            return queryset
        return queryset.filter(products__sub_subcategory_id=value).distinct()

    def filter_min_product_count(self, queryset, name, value):
        """Filter brands with minimum number of products"""
        if not value:
            return queryset

        return queryset.annotate(product_count=Count("products", filter=Q(products__is_active=True))).filter(
            product_count__gte=value
        )
