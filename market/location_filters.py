import django_filters
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.db import models
from django.db.models import F, Prefetch, Q

from geo.services import GeoLocationService
from market.models import MarketplaceUserProduct
from producer.models import MarketplaceProduct


class LocationBaseMixin:
    """
    Base mixin for location-based filtering with performance optimizations.
    """

    @staticmethod
    def get_distance_annotation(latitude: float, longitude: float, location_field: str = "location"):
        """
        Get distance annotation for QuerySet optimization.

        Args:
            latitude: User latitude
            longitude: User longitude
            location_field: Field name for location (varies by model)

        Returns:
            Distance annotation dict
        """
        user_location = Point(longitude, latitude, srid=4326)
        return {"distance_km": Distance(location_field, user_location) / 1000}

    @staticmethod
    def apply_performance_optimization(queryset, model_type: str):
        """
        Apply model-specific performance optimizations.

        Args:
            queryset: Base QuerySet
            model_type: 'marketplace' or 'user'

        Returns:
            Optimized QuerySet
        """
        if model_type == "marketplace":
            return queryset.select_related("product__producer", "product__category", "product__user").prefetch_related(
                Prefetch("product__images"),
                Prefetch("marketplaceproductreview_set", queryset=models.QuerySet().only("rating", "review_text")),
            )
        elif model_type == "user":
            return queryset.select_related("user", "location").prefetch_related(
                Prefetch("images", queryset=models.QuerySet().only("image", "alt_text", "order"))
            )
        return queryset


class MarketplaceProductLocationFilter(django_filters.FilterSet, LocationBaseMixin):
    """
    Advanced location-based filtering for MarketplaceProduct with performance optimization.
    """

    # Location parameters
    latitude = django_filters.NumberFilter(method="filter_by_location", help_text="User latitude (-90 to 90)")
    longitude = django_filters.NumberFilter(method="filter_by_location", help_text="User longitude (-180 to 180)")
    max_distance_km = django_filters.NumberFilter(method="filter_by_distance", help_text="Maximum distance in kilometers")

    # Price filters
    min_price = django_filters.NumberFilter(field_name="listed_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="listed_price", lookup_expr="lte")
    price_range = django_filters.RangeFilter(field_name="listed_price")

    # Product attributes
    category = django_filters.CharFilter(field_name="product__category__name", lookup_expr="iexact")
    categories = django_filters.BaseInFilter(field_name="product__category__name", lookup_expr="in")
    brand = django_filters.CharFilter(field_name="product__brand", lookup_expr="icontains")

    # Status filters
    is_available = django_filters.BooleanFilter(field_name="is_available")
    is_featured = django_filters.BooleanFilter(field_name="is_featured")
    is_made_in_nepal = django_filters.BooleanFilter(field_name="is_made_in_nepal")

    # Search
    search = django_filters.CharFilter(method="filter_search", help_text="Search in product name, description, tags")

    # Delivery filters
    max_delivery_days = django_filters.NumberFilter(field_name="estimated_delivery_days", lookup_expr="lte")
    max_shipping_cost = django_filters.NumberFilter(field_name="shipping_cost", lookup_expr="lte")

    # Sorting
    ordering = django_filters.OrderingFilter(
        fields=(
            ("distance_km", "distance"),
            ("listed_price", "price"),
            ("rank_score", "popularity"),
            ("recent_purchases_count", "recent_purchases"),
            ("view_count", "views"),
            ("listed_date", "date_listed"),
        ),
        field_labels={
            "distance": "Distance",
            "price": "Price",
            "popularity": "Popularity Score",
            "recent_purchases": "Recent Purchases",
            "views": "View Count",
            "date_listed": "Date Listed",
        },
    )

    class Meta:
        model = MarketplaceProduct
        fields = {
            "listed_price": ["exact", "gte", "lte"],
            "is_available": ["exact"],
            "is_featured": ["exact"],
            "is_made_in_nepal": ["exact"],
            "estimated_delivery_days": ["exact", "lte"],
            "shipping_cost": ["exact", "lte"],
            "size": ["exact"],
            "color": ["exact"],
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._location_cache = {}

    def filter_by_location(self, queryset, name, value):
        """
        Filter by location and add distance annotation.
        This method is called for both latitude and longitude.
        """
        request = getattr(self, "request", None)
        if not request:
            return queryset

        lat = request.GET.get("latitude")
        lon = request.GET.get("longitude")

        if not lat or not lon:
            return queryset

        try:
            lat, lon = float(lat), float(lon)
        except ValueError:
            return queryset

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return queryset

        # Check cache for location-based queryset
        cache_key = f"marketplace_location:{lat}:{lon}:{hash(str(queryset.query))}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        # Apply location filtering based on producer location
        user_location = Point(lon, lat, srid=4326)

        # Annotate with distance and filter by service radius
        queryset = (
            queryset.select_related("product__producer")
            .filter(product__producer__location__isnull=False)
            .annotate(distance_km=Distance("product__producer__location", user_location) / 1000)
        )

        # Apply service radius constraints
        queryset = queryset.filter(
            Q(product__producer__service_radius_km__isnull=True)
            | Q(distance_km__lte=F("product__producer__service_radius_km"))
        )

        # Cache for 5 minutes
        cache.set(cache_key, queryset, 300)
        return queryset

    def filter_by_distance(self, queryset, name, value):
        """Filter by maximum distance."""
        if value and hasattr(queryset.model, "_distance_annotated"):
            return queryset.filter(distance_km__lte=value)
        return queryset

    def filter_search(self, queryset, name, value):
        """
        Full-text search across multiple fields.
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(product__name__icontains=value)
            | Q(product__description__icontains=value)
            | Q(product__brand__icontains=value)
            | Q(search_tags__icontains=value)
            | Q(product__producer__name__icontains=value)
        ).distinct()

    @property
    def qs(self):
        """
        Override to apply performance optimizations.
        """
        queryset = super().qs

        # Apply base filters
        queryset = queryset.filter(is_available=True)

        # Apply performance optimization
        queryset = self.apply_performance_optimization(queryset, "marketplace")

        # Add location context if available
        request = getattr(self, "request", None)
        if request:
            lat = request.GET.get("latitude")
            lon = request.GET.get("longitude")
            if lat and lon:
                try:
                    lat, lon = float(lat), float(lon)
                    queryset._distance_annotated = True
                    queryset._user_location = {"latitude": lat, "longitude": lon}
                except ValueError:
                    pass

        return queryset


class MarketplaceUserProductLocationFilter(django_filters.FilterSet, LocationBaseMixin):
    """
    Advanced location-based filtering for MarketplaceUserProduct with performance optimization.
    """

    # Location parameters
    latitude = django_filters.NumberFilter(method="filter_by_location")
    longitude = django_filters.NumberFilter(method="filter_by_location")
    max_distance_km = django_filters.NumberFilter(method="filter_by_distance")

    # Price filters
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    price_range = django_filters.RangeFilter(field_name="price")

    # Product attributes
    category = django_filters.ChoiceFilter(choices=MarketplaceUserProduct.ProductCategory.choices)
    categories = django_filters.BaseInFilter(field_name="category", lookup_expr="in")
    unit = django_filters.ChoiceFilter(choices=MarketplaceUserProduct.ProductUnit.choices)

    # Status filters
    is_verified = django_filters.BooleanFilter(field_name="is_verified")
    is_sold = django_filters.BooleanFilter(field_name="is_sold")

    # Location filters
    location_city = django_filters.CharFilter(field_name="location__name", lookup_expr="icontains")

    # Search
    search = django_filters.CharFilter(method="filter_search")

    # Stock filter
    min_stock = django_filters.NumberFilter(field_name="stock", lookup_expr="gte")

    # Sorting
    ordering = django_filters.OrderingFilter(
        fields=(
            ("distance_km", "distance"),
            ("price", "price"),
            ("stock", "stock"),
            ("created_at", "date_created"),
        ),
        field_labels={
            "distance": "Distance",
            "price": "Price",
            "stock": "Stock",
            "date_created": "Date Created",
        },
    )

    class Meta:
        model = MarketplaceUserProduct
        fields = {
            "price": ["exact", "gte", "lte"],
            "category": ["exact"],
            "unit": ["exact"],
            "is_verified": ["exact"],
            "is_sold": ["exact"],
            "stock": ["exact", "gte"],
        }

    def filter_by_location(self, queryset, name, value):
        """
        Filter by location using city coordinates.
        """
        request = getattr(self, "request", None)
        if not request:
            return queryset

        lat = request.GET.get("latitude")
        lon = request.GET.get("longitude")

        if not lat or not lon:
            return queryset

        try:
            lat, lon = float(lat), float(lon)
        except ValueError:
            return queryset

        # Check cache
        cache_key = f"user_product_location:{lat}:{lon}:{hash(str(queryset.query))}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        # Filter by city location and add distance
        user_location = Point(lon, lat, srid=4326)

        queryset = (
            queryset.select_related("location")
            .filter(location__location__isnull=False)
            .annotate(distance_km=Distance("location__location", user_location) / 1000)
        )

        # Cache for 5 minutes
        cache.set(cache_key, queryset, 300)
        return queryset

    def filter_by_distance(self, queryset, name, value):
        """Filter by maximum distance."""
        if value and hasattr(queryset, "_distance_annotated"):
            return queryset.filter(distance_km__lte=value)
        return queryset

    def filter_search(self, queryset, name, value):
        """Search in product fields."""
        if not value:
            return queryset

        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(user__username__icontains=value)
            | Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
        ).distinct()

    @property
    def qs(self):
        """Apply performance optimizations."""
        queryset = super().qs

        # Base filters
        queryset = queryset.filter(is_sold=False, is_verified=True)

        # Apply performance optimization
        queryset = self.apply_performance_optimization(queryset, "user")

        return queryset


class CombinedLocationFilter(django_filters.FilterSet):
    """
    Combined filter for searching both MarketplaceProduct and MarketplaceUserProduct
    with unified location-based filtering.
    """

    # Location parameters
    latitude = django_filters.NumberFilter()
    longitude = django_filters.NumberFilter()
    max_distance_km = django_filters.NumberFilter()

    # Common filters
    min_price = django_filters.NumberFilter()
    max_price = django_filters.NumberFilter()
    search = django_filters.CharFilter()

    # Product type filter
    product_types = django_filters.MultipleChoiceFilter(
        choices=[
            ("marketplace", "Marketplace Products"),
            ("user", "User Products"),
        ]
    )

    def get_combined_queryset(self):
        """
        Get combined results from both product types.
        Returns a list of dictionaries with unified structure.
        """
        results = []

        # Get request parameters
        params = self.data
        lat = params.get("latitude")
        lon = params.get("longitude")
        product_types = params.getlist("product_types", ["marketplace", "user"])

        if not lat or not lon:
            return results

        # Filter MarketplaceProduct if requested
        if "marketplace" in product_types:
            mp_filter = MarketplaceProductLocationFilter(
                data=params, queryset=MarketplaceProduct.objects.all(), request=getattr(self, "request", None)
            )

            for product in mp_filter.qs[:25]:  # Limit for performance
                results.append(
                    {
                        "id": product.id,
                        "type": "marketplace",
                        "name": product.product.name,
                        "price": float(product.listed_price),
                        "distance_km": getattr(product, "distance_km", None),
                        "seller": product.product.producer.name if product.product.producer else None,
                        "location": {
                            "latitude": (
                                product.product.producer.location.y
                                if product.product.producer and product.product.producer.location
                                else None
                            ),
                            "longitude": (
                                product.product.producer.location.x
                                if product.product.producer and product.product.producer.location
                                else None
                            ),
                        },
                    }
                )

        # Filter MarketplaceUserProduct if requested
        if "user" in product_types:
            mup_filter = MarketplaceUserProductLocationFilter(
                data=params, queryset=MarketplaceUserProduct.objects.all(), request=getattr(self, "request", None)
            )

            for product in mup_filter.qs[:25]:  # Limit for performance
                results.append(
                    {
                        "id": product.id,
                        "type": "user",
                        "name": product.name,
                        "price": float(product.price),
                        "distance_km": getattr(product, "distance_km", None),
                        "seller": f"{product.user.first_name} {product.user.last_name}".strip() or product.user.username,
                        "location": {
                            "latitude": (
                                product.location.location.y if product.location and product.location.location else None
                            ),
                            "longitude": (
                                product.location.location.x if product.location and product.location.location else None
                            ),
                        },
                    }
                )

        # Sort by distance
        results.sort(key=lambda x: x.get("distance_km", float("inf")))

        return results[:50]  # Return top 50 results


# Custom filter fields for advanced location queries
class DistanceFilter(django_filters.NumberFilter):
    """
    Custom filter for distance-based queries with validation.
    """

    def filter(self, qs, value):
        if value is None:
            return qs

        if value < 0 or value > 500:  # Max 500km
            return qs.none()

        return qs.filter(distance_km__lte=value)


class ZoneFilter(django_filters.CharFilter):
    """
    Filter products by geographic zone name.
    """

    def filter(self, qs, value):
        if not value:
            return qs

        # This would need to be implemented with zone boundary checks
        # For now, return the original queryset
        return qs
