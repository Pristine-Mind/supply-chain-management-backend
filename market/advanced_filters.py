import django_filters
from django.db import models
from django.db.models import Avg, Count, F, Max, Min, Q
from django.utils import timezone

from producer.models import Brand, Category, MarketplaceProduct, Product


class PriceRangeFilter(django_filters.FilterSet):
    """Filter for price range with multiple range options"""

    min_price = django_filters.NumberFilter(method="filter_min_price", label="Minimum Price")
    max_price = django_filters.NumberFilter(method="filter_max_price", label="Maximum Price")
    price_range = django_filters.CharFilter(method="filter_price_range", label="Price Range Preset")

    class Meta:
        model = MarketplaceProduct
        fields = ["min_price", "max_price", "price_range"]

    def filter_min_price(self, queryset, name, value):
        """Filter by minimum effective price"""
        if value is not None:
            return queryset.filter(
                Q(discounted_price__gte=value) | Q(discounted_price__isnull=True, listed_price__gte=value)
            )
        return queryset

    def filter_max_price(self, queryset, name, value):
        """Filter by maximum effective price"""
        if value is not None:
            return queryset.filter(
                Q(discounted_price__lte=value) | Q(discounted_price__isnull=True, listed_price__lte=value)
            )
        return queryset

    def filter_price_range(self, queryset, name, value):
        """Filter by predefined price ranges"""
        ranges = {
            "budget": (0, 1000),
            "economy": (1000, 5000),
            "mid": (5000, 15000),
            "premium": (15000, 50000),
            "luxury": (50000, float("inf")),
        }
        if value in ranges:
            min_p, max_p = ranges[value]
            if max_p == float("inf"):
                return queryset.filter(
                    Q(discounted_price__gte=min_p) | Q(discounted_price__isnull=True, listed_price__gte=min_p)
                )
            return queryset.filter(
                (Q(discounted_price__gte=min_p) & Q(discounted_price__lte=max_p))
                | (Q(discounted_price__isnull=True) & Q(listed_price__gte=min_p) & Q(listed_price__lte=max_p))
            )
        return queryset


class RatingFilter(django_filters.FilterSet):
    """Filter products by rating and review count"""

    min_rating = django_filters.NumberFilter(method="filter_min_rating", label="Minimum Rating")
    min_reviews = django_filters.NumberFilter(method="filter_min_reviews", label="Minimum Reviews")
    has_reviews = django_filters.BooleanFilter(method="filter_has_reviews", label="Has Reviews")

    class Meta:
        model = MarketplaceProduct
        fields = ["min_rating", "min_reviews", "has_reviews"]

    def filter_min_rating(self, queryset, name, value):
        """Filter by minimum average rating"""
        if value:
            return queryset.annotate(avg_rating=Avg("reviews__rating")).filter(avg_rating__gte=value)
        return queryset

    def filter_min_reviews(self, queryset, name, value):
        """Filter by minimum number of reviews"""
        if value:
            return queryset.annotate(review_count=Count("reviews")).filter(review_count__gte=value)
        return queryset

    def filter_has_reviews(self, queryset, name, value):
        """Filter products with or without reviews"""
        queryset = queryset.annotate(review_count=Count("reviews"))
        if value:
            return queryset.filter(review_count__gt=0)
        else:
            return queryset.filter(review_count=0)


class AvailabilityFilter(django_filters.FilterSet):
    """Filter by product availability and stock status"""

    in_stock = django_filters.BooleanFilter(method="filter_in_stock", label="In Stock")
    stock_status = django_filters.CharFilter(method="filter_stock_status", label="Stock Status")
    delivery_time = django_filters.CharFilter(method="filter_delivery_time", label="Delivery Time")

    class Meta:
        model = MarketplaceProduct
        fields = ["in_stock", "stock_status", "delivery_time"]

    def filter_in_stock(self, queryset, name, value):
        """Filter by stock availability"""
        if value:
            return queryset.filter(product__stock__gt=0)
        else:
            return queryset.filter(product__stock=0)

    def filter_stock_status(self, queryset, name, value):
        """Filter by stock status: 'in_stock', 'low_stock', 'out_of_stock'"""
        if value == "in_stock":
            return queryset.filter(product__stock__gt=F("product__reorder_level"))
        elif value == "low_stock":
            return queryset.filter(product__stock__gt=0, product__stock__lte=F("product__reorder_level"))
        elif value == "out_of_stock":
            return queryset.filter(product__stock=0)
        return queryset

    def filter_delivery_time(self, queryset, name, value):
        """Filter by delivery time: 'same_day', '1_day', '2_3_days', '1_week', 'more'"""
        ranges = {
            "same_day": (0, 1),
            "1_day": (1, 2),
            "2_3_days": (2, 4),
            "1_week": (0, 8),
            "more": (8, 999),
        }
        if value in ranges:
            min_days, max_days = ranges[value]
            if value == "1_week":
                return queryset.filter(estimated_delivery_days__lte=max_days)
            return queryset.filter(estimated_delivery_days__gte=min_days, estimated_delivery_days__lt=max_days)
        return queryset


class OfferFilter(django_filters.FilterSet):
    """Filter by offers and promotions"""

    has_discount = django_filters.BooleanFilter(method="filter_has_discount", label="Has Discount")
    discount_min = django_filters.NumberFilter(method="filter_discount_min", label="Minimum Discount %")
    on_sale = django_filters.BooleanFilter(method="filter_on_sale", label="Currently On Sale")
    b2b_available = django_filters.BooleanFilter(field_name="enable_b2b_sales", label="B2B Available")

    class Meta:
        model = MarketplaceProduct
        fields = ["has_discount", "discount_min", "on_sale", "b2b_available"]

    def filter_has_discount(self, queryset, name, value):
        """Filter products with active discounts"""
        if value:
            return queryset.filter(discounted_price__isnull=False, discounted_price__lt=F("listed_price"))
        else:
            return queryset.filter(Q(discounted_price__isnull=True) | Q(discounted_price__gte=F("listed_price")))

    def filter_discount_min(self, queryset, name, value):
        """Filter by minimum discount percentage"""
        if value:
            return (
                queryset.filter(discounted_price__isnull=False, discounted_price__lt=F("listed_price"))
                .annotate(discount_pct=((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100)
                .filter(discount_pct__gte=value)
            )
        return queryset

    def filter_on_sale(self, queryset, name, value):
        """Filter products currently on sale (offer period active)"""
        now = timezone.now()
        if value:
            return queryset.filter(
                Q(offer_start__isnull=True) | Q(offer_start__lte=now),
                Q(offer_end__isnull=True) | Q(offer_end__gte=now),
                discounted_price__isnull=False,
            )
        else:
            return queryset.exclude(
                Q(offer_start__isnull=True) | Q(offer_start__lte=now),
                Q(offer_end__isnull=True) | Q(offer_end__gte=now),
                discounted_price__isnull=False,
            )


class AdvancedMarketplaceProductFilter(django_filters.FilterSet):
    """
    Comprehensive filter combining all advanced filtering capabilities
    with faceted search support.
    """

    # Text search
    search = django_filters.CharFilter(method="filter_search", label="Search")

    # Category filters
    category = django_filters.CharFilter(method="filter_category", label="Category")
    category_id = django_filters.NumberFilter(method="filter_category_id", label="Category ID")
    subcategory_id = django_filters.NumberFilter(method="filter_subcategory_id", label="Subcategory ID")
    sub_subcategory_id = django_filters.NumberFilter(method="filter_sub_subcategory_id", label="Sub-subcategory ID")

    # Brand filter
    brand_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Brand.objects.all(), field_name="product__brand", label="Brands"
    )

    # Location filters
    city = django_filters.CharFilter(field_name="product__location__name", lookup_expr="iexact")
    near_me = django_filters.CharFilter(method="filter_near_me", label="Near Me (lat,lng,radius_km)")

    # Price filters
    min_price = django_filters.NumberFilter(method="filter_min_price", label="Minimum Price")
    max_price = django_filters.NumberFilter(method="filter_max_price", label="Maximum Price")
    price_range = django_filters.CharFilter(method="filter_price_range", label="Price Range")

    # Rating filters
    min_rating = django_filters.NumberFilter(method="filter_min_rating", label="Minimum Rating")
    min_reviews = django_filters.NumberFilter(method="filter_min_reviews", label="Minimum Reviews")

    # Availability filters
    in_stock = django_filters.BooleanFilter(method="filter_in_stock", label="In Stock")
    stock_status = django_filters.CharFilter(method="filter_stock_status", label="Stock Status")
    delivery_days_max = django_filters.NumberFilter(
        field_name="estimated_delivery_days", lookup_expr="lte", label="Max Delivery Days"
    )

    # Offer filters
    has_discount = django_filters.BooleanFilter(method="filter_has_discount", label="Has Discount")
    discount_min = django_filters.NumberFilter(method="filter_discount_min", label="Min Discount %")
    on_sale = django_filters.BooleanFilter(method="filter_on_sale", label="On Sale")

    # Product attributes
    size = django_filters.MultipleChoiceFilter(
        choices=MarketplaceProduct.SizeChoices.choices, method="filter_size", label="Size"
    )
    color = django_filters.MultipleChoiceFilter(
        choices=MarketplaceProduct.ColorChoices.choices, method="filter_color", label="Color"
    )

    # B2B filters
    b2b_available = django_filters.BooleanFilter(field_name="enable_b2b_sales", label="B2B Available")
    b2b_price_max = django_filters.NumberFilter(field_name="b2b_price", lookup_expr="lte", label="Max B2B Price")

    # Sorting
    sort_by = django_filters.CharFilter(method="filter_sort_by", label="Sort By")

    class Meta:
        model = MarketplaceProduct
        fields = [
            "search",
            "category",
            "category_id",
            "subcategory_id",
            "sub_subcategory_id",
            "brand_id",
            "city",
            "near_me",
            "min_price",
            "max_price",
            "price_range",
            "min_rating",
            "min_reviews",
            "in_stock",
            "stock_status",
            "delivery_days_max",
            "has_discount",
            "discount_min",
            "on_sale",
            "size",
            "color",
            "b2b_available",
            "b2b_price_max",
            "sort_by",
        ]

    def filter_search(self, queryset, name, value):
        """Multi-field search across product details"""
        if not value:
            return queryset
        return queryset.filter(
            Q(product__name__icontains=value)
            | Q(product__description__icontains=value)
            | Q(search_tags__icontains=value)
            | Q(product__brand__name__icontains=value)
            | Q(additional_information__icontains=value)
        ).distinct()

    def filter_category(self, queryset, name, value):
        """Filter by category name, code, or ID"""
        if not value:
            return queryset
        try:
            category_id = int(value)
            return queryset.filter(
                Q(product__category_id=category_id)
                | Q(product__subcategory__category_id=category_id)
                | Q(product__sub_subcategory__subcategory__category_id=category_id)
            )
        except ValueError:
            if len(value) == 2 and value.isalpha() and value.isupper():
                return queryset.filter(
                    Q(product__category__code=value)
                    | Q(product__subcategory__category__code=value)
                    | Q(product__sub_subcategory__subcategory__category__code=value)
                )
            return queryset.filter(
                Q(product__category__name__icontains=value)
                | Q(product__subcategory__name__icontains=value)
                | Q(product__sub_subcategory__name__icontains=value)
            )

    def filter_category_id(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(product__category_id=value)
                | Q(product__subcategory__category_id=value)
                | Q(product__sub_subcategory__subcategory__category_id=value)
            )
        return queryset

    def filter_subcategory_id(self, queryset, name, value):
        if value:
            return queryset.filter(Q(product__subcategory_id=value) | Q(product__sub_subcategory__subcategory_id=value))
        return queryset

    def filter_sub_subcategory_id(self, queryset, name, value):
        if value:
            return queryset.filter(product__sub_subcategory_id=value)
        return queryset

    def filter_near_me(self, queryset, name, value):
        """Filter by geographic proximity. Value format: 'lat,lng,radius_km'"""
        if not value:
            return queryset
        try:
            parts = value.split(",")
            if len(parts) >= 2:
                lat, lng = float(parts[0]), float(parts[1])
                radius_km = float(parts[2]) if len(parts) > 2 else 10

                # Use PostGIS distance if available, otherwise skip
                from django.contrib.gis.db.models.functions import Distance
                from django.contrib.gis.geos import Point

                user_location = Point(lng, lat, srid=4326)
                return (
                    queryset.filter(seller_geo_point__distance_lte=(user_location, radius_km * 1000))
                    .annotate(distance=Distance("seller_geo_point", user_location))
                    .order_by("distance")
                )
        except (ValueError, ImportError):
            pass
        return queryset

    def filter_min_price(self, queryset, name, value):
        if value is not None:
            return queryset.filter(
                Q(discounted_price__gte=value) | Q(discounted_price__isnull=True, listed_price__gte=value)
            )
        return queryset

    def filter_max_price(self, queryset, name, value):
        if value is not None:
            return queryset.filter(
                Q(discounted_price__lte=value) | Q(discounted_price__isnull=True, listed_price__lte=value)
            )
        return queryset

    def filter_price_range(self, queryset, name, value):
        ranges = {
            "budget": (0, 1000),
            "economy": (1000, 5000),
            "mid": (5000, 15000),
            "premium": (15000, 50000),
            "luxury": (50000, float("inf")),
        }
        if value in ranges:
            min_p, max_p = ranges[value]
            if max_p == float("inf"):
                return queryset.filter(
                    Q(discounted_price__gte=min_p) | Q(discounted_price__isnull=True, listed_price__gte=min_p)
                )
            return queryset.filter(
                (Q(discounted_price__gte=min_p) & Q(discounted_price__lte=max_p))
                | (Q(discounted_price__isnull=True) & Q(listed_price__gte=min_p) & Q(listed_price__lte=max_p))
            )
        return queryset

    def filter_min_rating(self, queryset, name, value):
        if value:
            return queryset.annotate(avg_rating=Avg("reviews__rating")).filter(avg_rating__gte=value)
        return queryset

    def filter_min_reviews(self, queryset, name, value):
        if value:
            return queryset.annotate(review_count=Count("reviews")).filter(review_count__gte=value)
        return queryset

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(product__stock__gt=0)
        return queryset.filter(product__stock=0)

    def filter_stock_status(self, queryset, name, value):
        if value == "in_stock":
            return queryset.filter(product__stock__gt=F("product__reorder_level"))
        elif value == "low_stock":
            return queryset.filter(product__stock__gt=0, product__stock__lte=F("product__reorder_level"))
        elif value == "out_of_stock":
            return queryset.filter(product__stock=0)
        return queryset

    def filter_has_discount(self, queryset, name, value):
        if value:
            return queryset.filter(discounted_price__isnull=False, discounted_price__lt=F("listed_price"))
        return queryset.filter(Q(discounted_price__isnull=True) | Q(discounted_price__gte=F("listed_price")))

    def filter_discount_min(self, queryset, name, value):
        if value:
            return (
                queryset.filter(discounted_price__isnull=False, discounted_price__lt=F("listed_price"))
                .annotate(discount_pct=((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100)
                .filter(discount_pct__gte=value)
            )
        return queryset

    def filter_on_sale(self, queryset, name, value):
        now = timezone.now()
        if value:
            return queryset.filter(
                Q(offer_start__isnull=True) | Q(offer_start__lte=now),
                Q(offer_end__isnull=True) | Q(offer_end__gte=now),
                discounted_price__isnull=False,
            )
        return queryset.exclude(
            Q(offer_start__isnull=True) | Q(offer_start__lte=now),
            Q(offer_end__isnull=True) | Q(offer_end__gte=now),
            discounted_price__isnull=False,
        )

    def filter_size(self, queryset, name, value):
        if not value:
            return queryset
        size_q = Q()
        for size in value:
            size_q |= Q(size=size) | Q(size__isnull=True, product__size=size)
        return queryset.filter(size_q)

    def filter_color(self, queryset, name, value):
        if not value:
            return queryset
        color_q = Q()
        for color in value:
            color_q |= Q(color=color) | Q(color__isnull=True, product__color=color)
        return queryset.filter(color_q)

    def filter_sort_by(self, queryset, name, value):
        """Sort results by various criteria"""
        sort_options = {
            "price_asc": "effective_price",
            "price_desc": "-effective_price",
            "newest": "-listed_date",
            "popular": "-recent_purchases_count",
            "rating": "-avg_rating",
            "name_asc": "product__name",
            "name_desc": "-product__name",
            "discount": "-discount_pct",
        }

        if value in sort_options:
            sort_field = sort_options[value]

            # Annotate for sorting
            if "effective_price" in sort_field:
                queryset = queryset.annotate(
                    effective_price=Min("discounted_price", output_field=models.FloatField())
                ).annotate(
                    effective_price=models.Case(
                        models.When(discounted_price__isnull=False, then=F("discounted_price")),
                        default=F("listed_price"),
                        output_field=models.FloatField(),
                    )
                )
            elif "avg_rating" in sort_field:
                queryset = queryset.annotate(avg_rating=Avg("reviews__rating"))
            elif "discount_pct" in sort_field:
                queryset = queryset.annotate(
                    discount_pct=((F("listed_price") - F("discounted_price")) / F("listed_price")) * 100
                )

            return queryset.order_by(sort_field)

        return queryset


class FacetedSearchService:
    """
    Service to provide faceted search results with counts for each filter option.
    This enables the frontend to show filter counts dynamically.
    """

    @staticmethod
    def get_facet_counts(queryset):
        """
        Get facet counts for various filter dimensions.
        Returns a dictionary with counts for each facet.
        """
        from django.db.models import Case, IntegerField, Value, When

        facets = {}

        # Price range facets
        price_ranges = [
            ("budget", 0, 1000),
            ("economy", 1000, 5000),
            ("mid", 5000, 15000),
            ("premium", 15000, 50000),
            ("luxury", 50000, float("inf")),
        ]

        price_counts = {}
        for label, min_p, max_p in price_ranges:
            if max_p == float("inf"):
                count = queryset.filter(
                    Q(discounted_price__gte=min_p) | Q(discounted_price__isnull=True, listed_price__gte=min_p)
                ).count()
            else:
                count = queryset.filter(
                    (Q(discounted_price__gte=min_p) & Q(discounted_price__lte=max_p))
                    | (Q(discounted_price__isnull=True) & Q(listed_price__gte=min_p) & Q(listed_price__lte=max_p))
                ).count()
            price_counts[label] = count
        facets["price_ranges"] = price_counts

        # Category facets
        facets["categories"] = list(
            queryset.filter(product__category__isnull=False)
            .values("product__category__id", "product__category__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Brand facets
        facets["brands"] = list(
            queryset.filter(product__brand__isnull=False)
            .values("product__brand__id", "product__brand__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Rating facets
        rating_ranges = [
            ("4_and_up", 4),
            ("3_and_up", 3),
            ("2_and_up", 2),
        ]
        rating_counts = {}
        for label, min_rating in rating_ranges:
            count = queryset.annotate(avg_rating=Avg("reviews__rating")).filter(avg_rating__gte=min_rating).count()
            rating_counts[label] = count
        facets["ratings"] = rating_counts

        # Stock status facets
        facets["stock_status"] = {
            "in_stock": queryset.filter(product__stock__gt=F("product__reorder_level")).count(),
            "low_stock": queryset.filter(product__stock__gt=0, product__stock__lte=F("product__reorder_level")).count(),
            "out_of_stock": queryset.filter(product__stock=0).count(),
        }

        # Discount facets
        facets["discounts"] = {
            "has_discount": queryset.filter(discounted_price__isnull=False, discounted_price__lt=F("listed_price")).count(),
            "no_discount": queryset.filter(
                Q(discounted_price__isnull=True) | Q(discounted_price__gte=F("listed_price"))
            ).count(),
        }

        # Delivery time facets
        facets["delivery_time"] = {
            "same_day": queryset.filter(estimated_delivery_days__lte=1).count(),
            "1_2_days": queryset.filter(estimated_delivery_days__in=[1, 2]).count(),
            "3_5_days": queryset.filter(estimated_delivery_days__range=[3, 5]).count(),
            "1_week_plus": queryset.filter(estimated_delivery_days__gt=5).count(),
        }

        return facets


def get_filtered_products_with_facets(filter_params):
    """
    Convenience function to get filtered products and facet counts.

    Usage:
        result = get_filtered_products_with_facets({
            'category_id': 1,
            'min_price': 1000,
            'sort_by': 'price_asc'
        })
        # result['products'] - filtered queryset
        # result['facets'] - facet counts
        # result['total_count'] - total matching products
    """
    # Start with active products
    queryset = MarketplaceProduct.objects.filter(is_available=True)

    # Apply filters
    filter_set = AdvancedMarketplaceProductFilter(filter_params, queryset=queryset)
    filtered_qs = filter_set.qs

    # Get facet counts (based on filtered results)
    facets = FacetedSearchService.get_facet_counts(filtered_qs)

    return {
        "products": filtered_qs,
        "facets": facets,
        "total_count": filtered_qs.count(),
        "is_valid": filter_set.is_valid(),
        "errors": filter_set.errors if not filter_set.is_valid() else None,
    }
