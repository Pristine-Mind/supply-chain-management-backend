import django_filters
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db.models import Q

from producer.models import City

from .models import Role, UserProfile


class BusinessFilter(django_filters.FilterSet):
    """
    Comprehensive filter class for business listings.
    Supports filtering by business type, location, B2B status, verification,
    and geographical distance-based filtering.
    """

    # Business type filtering
    business_type = django_filters.ChoiceFilter(
        choices=UserProfile.BusinessType.choices, help_text="Filter by business type (distributor/retailer)"
    )

    # Location-based filtering
    city = django_filters.ModelChoiceFilter(field_name="location", queryset=City.objects.all(), help_text="Filter by city")

    city_name = django_filters.CharFilter(
        field_name="location__name",
        lookup_expr="icontains",
        help_text="Filter by city name (case-insensitive partial match)",
    )

    # B2B and verification filters
    b2b_verified = django_filters.BooleanFilter(help_text="Filter by B2B verification status")

    has_marketplace_access = django_filters.BooleanFilter(
        field_name="has_access_to_marketplace", help_text="Filter by marketplace access"
    )

    # User status filters
    is_active = django_filters.BooleanFilter(field_name="user__is_active", help_text="Filter by user active status")

    # Credit limit range filtering
    min_credit_limit = django_filters.NumberFilter(
        field_name="credit_limit", lookup_expr="gte", help_text="Minimum credit limit"
    )

    max_credit_limit = django_filters.NumberFilter(
        field_name="credit_limit", lookup_expr="lte", help_text="Maximum credit limit"
    )

    # Date range filtering
    registered_after = django_filters.DateTimeFilter(
        field_name="user__date_joined", lookup_expr="gte", help_text="Show businesses registered after this date"
    )

    registered_before = django_filters.DateTimeFilter(
        field_name="user__date_joined", lookup_expr="lte", help_text="Show businesses registered before this date"
    )

    # Search filters
    search = django_filters.CharFilter(
        method="filter_search", help_text="Search in business name, user name, or phone number"
    )

    # Geographic distance filtering
    latitude = django_filters.NumberFilter(
        method="filter_by_distance", help_text="Latitude for distance-based filtering (use with longitude and radius)"
    )

    longitude = django_filters.NumberFilter(
        method="filter_by_distance", help_text="Longitude for distance-based filtering (use with latitude and radius)"
    )

    radius_km = django_filters.NumberFilter(
        method="filter_by_distance", help_text="Radius in kilometers for distance-based filtering"
    )

    class Meta:
        model = UserProfile
        fields = [
            "business_type",
            "city",
            "city_name",
            "b2b_verified",
            "has_marketplace_access",
            "is_active",
            "min_credit_limit",
            "max_credit_limit",
            "registered_after",
            "registered_before",
            "search",
            "latitude",
            "longitude",
            "radius_km",
        ]

    def filter_search(self, queryset, name, value):
        """
        Search across multiple fields including business name, user names, and phone.
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(registered_business_name__icontains=value)
            | Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
            | Q(user__username__icontains=value)
            | Q(phone_number__icontains=value)
        )

    def filter_by_distance(self, queryset, name, value):
        """
        Filter businesses within a certain radius of given coordinates.
        Requires latitude, longitude, and radius_km parameters.
        """
        # We need to collect all three parameters before applying the filter
        request_data = self.request.query_params if hasattr(self, "request") else self.data

        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        radius_km = request_data.get("radius_km")

        # Only apply distance filter if we have all required parameters
        if latitude and longitude and radius_km:
            try:
                lat_float = float(latitude)
                lng_float = float(longitude)
                radius_float = float(radius_km)

                # Filter businesses that have coordinates and calculate distance manually
                # This is a simplified distance calculation for small areas
                lat_range = radius_float / 111.0  # Roughly 111 km per degree of latitude
                lng_range = radius_float / (111.0 * abs(lat_float / 90.0))  # Adjust longitude for latitude

                return (
                    queryset.exclude(latitude__isnull=True)
                    .exclude(longitude__isnull=True)
                    .filter(
                        latitude__gte=lat_float - lat_range,
                        latitude__lte=lat_float + lat_range,
                        longitude__gte=lng_float - lng_range,
                        longitude__lte=lng_float + lng_range,
                    )
                )

            except (ValueError, TypeError):
                # If coordinates are invalid, return original queryset
                pass

        return queryset
