"""
Search and filtering utilities for marketplace products.
Handles relevance ranking, color normalization, and advanced filtering.
"""

from decimal import Decimal

from django.db.models import Avg, Case, Count, DecimalField, F, Q, Value, When
from django.db.models.functions import Coalesce

# Color normalization mapping
COLOR_ALIASES = {
    "red": ["crimson", "rouge", "rojo", "rot", "vermelho"],
    "blue": ["navy", "cyan", "azul", "blau", "azurro"],
    "black": ["noir", "negro", "schwarz", "preto", "black"],
    "white": ["cream", "ivory", "blanco", "weiß", "branco"],
    "yellow": ["gold", "amarillo", "gelb", "giallo"],
    "green": ["lime", "mint", "verde", "grün", "verde"],
    "pink": ["rose", "magenta", "rosa", "rosa"],
    "purple": ["violet", "lavender", "morado", "lila", "viola"],
    "orange": ["naranja", "orange", "arancione"],
    "brown": ["tan", "beige", "marrón", "braun", "marrone"],
    "gray": ["grey", "silver", "gris", "grau", "grigio"],
}


def normalize_color(color_input):
    """
    Normalize color value to standard format (lowercase).

    Args:
        color_input: Raw color value from user input

    Returns:
        Normalized lowercase color or None if not found
    """
    if not color_input:
        return None

    color_lower = str(color_input).lower().strip()

    # Check if it's already a valid color
    valid_colors = list(COLOR_ALIASES.keys())
    if color_lower in valid_colors:
        return color_lower

    # Check aliases
    for standard_color, aliases in COLOR_ALIASES.items():
        if color_lower in [alias.lower() for alias in aliases]:
            return standard_color

    return None


def build_relevance_score_case(query):
    """
    Build a Django Case expression for search relevance scoring.

    Scoring:
    - 100: Exact name match
    - 90: Starts with query
    - 80: Category match
    - 70: Contains full query
    - 50: Contains first word
    - 30: Description contains query
    - 0: No match

    Args:
        query: Search query string

    Returns:
        Case expression for relevance scoring
    """
    if not query or len(query) < 2:
        return Case(default=Value(0, output_field=DecimalField()))

    terms = query.lower().split()
    main_term = terms[0]

    cases = [
        # Exact name match - 100 points
        When(product__name__iexact=query, then=Value(100, output_field=DecimalField())),
        # Exact first word match - 90 points
        When(product__name__istartswith=main_term, then=Value(90, output_field=DecimalField())),
        # All terms in name - 70 points
        When(product__name__icontains=query, then=Value(70, output_field=DecimalField())),
        # Single word contains - 50 points
        When(product__name__icontains=main_term, then=Value(50, output_field=DecimalField())),
        # Description contains - 30 points
        When(product__description__icontains=query, then=Value(30, output_field=DecimalField())),
    ]

    return Case(*cases, default=Value(0, output_field=DecimalField()))


class SearchFilter:
    """Enhanced search filtering for marketplace products."""

    @staticmethod
    def apply_search_with_relevance(queryset, query, category_id=None):
        """
        Apply search with relevance ranking.

        Args:
            queryset: Base MarketplaceProduct queryset
            query: Search query string
            category_id: Optional category filter

        Returns:
            Annotated queryset ordered by relevance score
        """
        if not query or len(query) < 2:
            return queryset

        # Apply search filter
        queryset = queryset.filter(
            Q(product__name__icontains=query)
            | Q(product__description__icontains=query)
            | Q(search_tags__contains=query.lower())
        )

        # Apply category filter if specified
        if category_id:
            queryset = queryset.filter(product__category_id=category_id)

        # Annotate with relevance score
        relevance_case = build_relevance_score_case(query)
        queryset = queryset.annotate(relevance_score=relevance_case).filter(relevance_score__gt=0)

        # Sort by relevance, then by rating and popularity
        queryset = (
            queryset.annotate(
                search_score=F("relevance_score") + (F("reviews__rating") * 5) + (F("view_count") * 0.1),
                avg_rating=Coalesce(Avg("reviews__rating"), Value(0), output_field=DecimalField()),
            )
            .order_by("-search_score", "-avg_rating", "-view_count", "-listed_date")
            .distinct()
        )

        return queryset


class CityFilter:
    """Enhanced city filtering with case-insensitive and flexible matching."""

    @staticmethod
    def apply_city_filter(queryset, city_value):
        """
        Apply city filter with flexible matching.

        Supports:
        - City name (case-insensitive): "Kathmandu"
        - City ID: 1

        Args:
            queryset: Base MarketplaceProduct queryset
            city_value: City name or ID

        Returns:
            Filtered queryset
        """
        if not city_value:
            return queryset

        try:
            # Try as city ID first
            city_id = int(city_value)
            return queryset.filter(Q(product__location__id=city_id) | Q(product__user__user_profile__city__id=city_id))
        except (ValueError, TypeError):
            # Fall back to city name (case-insensitive)
            return queryset.filter(
                Q(product__location__name__iexact=city_value) | Q(product__user__user_profile__city__name__iexact=city_value)
            )


class ColorFilter:
    """Enhanced color filtering with normalization."""

    @staticmethod
    def apply_color_filter(queryset, colors):
        """
        Apply color filter with normalization.

        Args:
            queryset: Base MarketplaceProduct queryset
            colors: List of color values to filter by

        Returns:
            Filtered queryset
        """
        if not colors:
            return queryset

        # Normalize all input colors
        normalized_colors = [normalize_color(c) for c in colors]
        normalized_colors = [c for c in normalized_colors if c]

        if not normalized_colors:
            return queryset

        # Create filter for marketplace color or product color
        color_filter = Q()
        for color in normalized_colors:
            # Match against both marketplace color and product color
            color_filter |= Q(color__iexact=color) | Q(product__color__iexact=color)

        return queryset.filter(color_filter)


class SizeFilter:
    """Enhanced size filtering."""

    @staticmethod
    def apply_size_filter(queryset, sizes):
        """
        Apply size filter checking marketplace and product levels.

        Args:
            queryset: Base MarketplaceProduct queryset
            sizes: List of size values to filter by

        Returns:
            Filtered queryset
        """
        if not sizes:
            return queryset

        # Filter by marketplace size or inherited product size
        size_filter = Q()
        for size in sizes:
            size_filter |= Q(size__iexact=size) | Q(product__size__iexact=size)

        return queryset.filter(size_filter).distinct()


class DeliveryFilter:
    """Enhanced delivery time filtering."""

    @staticmethod
    def apply_delivery_filter(queryset, delivery_days):
        """
        Apply delivery time filter.

        Args:
            queryset: Base MarketplaceProduct queryset
            delivery_days: Maximum delivery days

        Returns:
            Filtered queryset
        """
        if not delivery_days:
            return queryset

        try:
            days = int(delivery_days)
            return queryset.filter(Q(estimated_delivery_days__isnull=True) | Q(estimated_delivery_days__lte=days))
        except (ValueError, TypeError):
            return queryset


class PriceFilter:
    """Enhanced price range filtering."""

    @staticmethod
    def apply_price_filter(queryset, min_price=None, max_price=None):
        """
        Apply price range filter.

        Args:
            queryset: Base MarketplaceProduct queryset
            min_price: Minimum price (optional)
            max_price: Maximum price (optional)

        Returns:
            Filtered queryset
        """
        if min_price:
            try:
                min_val = Decimal(str(min_price))
                queryset = queryset.filter(
                    Q(discounted_price__gte=min_val) | Q(discounted_price__isnull=True, listed_price__gte=min_val)
                )
            except (ValueError, TypeError):
                pass

        if max_price:
            try:
                max_val = Decimal(str(max_price))
                queryset = queryset.filter(
                    Q(discounted_price__lte=max_val) | Q(discounted_price__isnull=True, listed_price__lte=max_val)
                )
            except (ValueError, TypeError):
                pass

        return queryset


class RatingFilter:
    """Rating-based filtering."""

    @staticmethod
    def apply_rating_filter(queryset, min_rating=None):
        """
        Apply minimum rating filter.

        Args:
            queryset: Base MarketplaceProduct queryset
            min_rating: Minimum average rating

        Returns:
            Filtered queryset
        """
        if not min_rating:
            return queryset

        try:
            rating = Decimal(str(min_rating))
            return queryset.annotate(
                avg_rating=Coalesce(Avg("reviews__rating"), Value(0), output_field=DecimalField())
            ).filter(avg_rating__gte=rating)
        except (ValueError, TypeError):
            return queryset
