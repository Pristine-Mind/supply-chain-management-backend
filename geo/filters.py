import django_filters

from producer.models import MarketplaceProduct

from .models import GeographicZone


class GeoProductFilter(django_filters.FilterSet):
    """
    Geographic product filter.
    Integrates with market app's existing filtering system.

    Usage in market/filters.py:
        class ProductFilter(GeoProductFilter):
            # Add other filters here
            pass

    Or in views:
        filter_backends = [DjangoFilterBackend]
        filterset_class = GeoProductFilter
    """

    latitude = django_filters.NumberFilter(
        method="filter_by_latitude", label="Delivery Latitude", help_text="User's latitude for geographic filtering"
    )

    longitude = django_filters.NumberFilter(
        method="filter_by_longitude", label="Delivery Longitude", help_text="User's longitude for geographic filtering"
    )

    max_delivery_distance_km = django_filters.NumberFilter(
        field_name="max_delivery_distance_km", lookup_expr="gte", label="Max Delivery Distance (km)"
    )

    zone_id = django_filters.ModelChoiceFilter(
        queryset=GeographicZone.objects.filter(is_active=True),
        field_name="available_delivery_zones",
        label="Delivery Zone",
        help_text="Filter by geographic zone",
    )

    has_geo_restrictions = django_filters.BooleanFilter(
        field_name="enable_geo_restrictions",
        label="Has Geo Restrictions",
        help_text="Filter products with geographic restrictions",
    )

    class Meta:
        model = MarketplaceProduct
        fields = ["latitude", "longitude", "max_delivery_distance_km", "zone_id"]

    def filter_by_latitude(self, queryset, name, value):
        """Filter by latitude - used for location-based search"""
        if value is None:
            return queryset

        # This is typically used with longitude
        # Actual filtering happens in the view using GeoProductFilterService
        return queryset

    def filter_by_longitude(self, queryset, name, value):
        """Filter by longitude - used for location-based search"""
        if value is None:
            return queryset

        return queryset


class ZoneFilter(django_filters.FilterSet):
    """
    Filter geographic zones.
    """

    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains", label="Zone Name")

    tier = django_filters.ChoiceFilter(field_name="tier", choices=GeographicZone.TIER_CHOICES, label="Delivery Tier")

    is_active = django_filters.BooleanFilter(field_name="is_active", label="Active Only")

    min_shipping_cost = django_filters.NumberFilter(field_name="shipping_cost", lookup_expr="gte")

    max_shipping_cost = django_filters.NumberFilter(field_name="shipping_cost", lookup_expr="lte")

    class Meta:
        model = GeographicZone
        fields = ["name", "tier", "is_active"]
