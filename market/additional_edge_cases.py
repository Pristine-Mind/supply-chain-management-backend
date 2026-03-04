import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class ConnectivityMode(Enum):
    """Network connectivity states for mobile users."""

    ONLINE = "online"
    SLOW_CONNECTION = "slow"
    OFFLINE_CAPABLE = "offline"
    EMERGENCY_ONLY = "emergency"


class SeasonalAvailability(Enum):
    """Seasonal product availability patterns."""

    YEAR_ROUND = "year_round"
    MONSOON_DEPENDENT = "monsoon"
    WINTER_ONLY = "winter"
    SUMMER_ONLY = "summer"
    FESTIVAL_SEASONAL = "festival"


class EmergencyMode(Enum):
    """Emergency operation modes."""

    NORMAL = "normal"
    WEATHER_ALERT = "weather"
    DISASTER_RESPONSE = "disaster"
    SUPPLY_SHORTAGE = "shortage"
    SYSTEM_OVERLOAD = "overload"


@dataclass
class CrossBorderDeliveryInfo:
    """Information for cross-border deliveries."""

    origin_country: str
    destination_country: str
    customs_required: bool
    estimated_customs_delay_hours: int
    additional_fees: Decimal
    prohibited_items: List[str]
    required_documents: List[str]
    currency_conversion_rate: Optional[Decimal] = None


@dataclass
class TimeZoneDeliveryEstimate:
    """Timezone-aware delivery information."""

    local_timezone: str
    estimated_pickup_time: datetime
    estimated_delivery_time: datetime
    business_hours: Dict[str, Tuple[int, int]]  # day: (start_hour, end_hour)
    holiday_adjustments: List[datetime]


class CrossBorderDeliveryHandler:
    """Handle cross-border delivery scenarios and regulations."""

    # Define border regions and their characteristics
    BORDER_REGIONS = {
        "nepal_india": {
            "countries": ["nepal", "india"],
            "open_border": True,
            "customs_threshold_usd": 100,
            "max_delivery_days": 7,
            "prohibited_categories": ["electronics_restricted", "medicines"],
        },
        "nepal_china": {
            "countries": ["nepal", "china"],
            "open_border": False,
            "customs_threshold_usd": 50,
            "max_delivery_days": 14,
            "prohibited_categories": ["food_fresh", "plants"],
        },
    }

    @classmethod
    def check_cross_border_delivery(
        cls,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        product_category: str,
        order_value_usd: Decimal,
    ) -> CrossBorderDeliveryInfo:
        """Check if delivery crosses borders and handle accordingly."""

        origin_country = cls._detect_country(origin_lat, origin_lon)
        dest_country = cls._detect_country(dest_lat, dest_lon)

        if origin_country == dest_country:
            # Domestic delivery
            return CrossBorderDeliveryInfo(
                origin_country=origin_country,
                destination_country=dest_country,
                customs_required=False,
                estimated_customs_delay_hours=0,
                additional_fees=Decimal("0"),
                prohibited_items=[],
                required_documents=[],
            )

        # Cross-border delivery
        border_key = f"{origin_country}_{dest_country}"
        if border_key not in cls.BORDER_REGIONS:
            border_key = f"{dest_country}_{origin_country}"

        border_info = cls.BORDER_REGIONS.get(border_key)
        if not border_info:
            # Unknown border crossing
            return CrossBorderDeliveryInfo(
                origin_country=origin_country,
                destination_country=dest_country,
                customs_required=True,
                estimated_customs_delay_hours=48,
                additional_fees=order_value_usd * Decimal("0.15"),  # 15% fee
                prohibited_items=["unknown_restrictions"],
                required_documents=["passport_copy", "customs_declaration"],
            )

        customs_required = order_value_usd >= border_info["customs_threshold_usd"]

        return CrossBorderDeliveryInfo(
            origin_country=origin_country,
            destination_country=dest_country,
            customs_required=customs_required,
            estimated_customs_delay_hours=24 if customs_required else 2,
            additional_fees=cls._calculate_border_fees(order_value_usd, border_info),
            prohibited_items=border_info["prohibited_categories"],
            required_documents=cls._get_required_documents(customs_required, border_info),
        )

    @classmethod
    def _detect_country(cls, lat: float, lon: float) -> str:
        """Detect country from coordinates (simplified)."""
        # Nepal bounds
        if 26.3 <= lat <= 30.4 and 80.0 <= lon <= 88.2:
            return "nepal"
        # India (simplified - northern regions)
        elif 20.0 <= lat <= 37.0 and 68.0 <= lon <= 97.25:
            return "india"
        # China (simplified - southern regions)
        elif 27.0 <= lat <= 36.0 and 79.0 <= lon <= 99.0:
            return "china"
        else:
            return "unknown"

    @classmethod
    def _calculate_border_fees(cls, order_value: Decimal, border_info: dict) -> Decimal:
        """Calculate additional fees for border crossing."""
        if border_info.get("open_border", False):
            return Decimal("0")

        # Customs processing fee
        base_fee = Decimal("50")  # Base processing fee
        value_fee = order_value * Decimal("0.05")  # 5% of order value

        return base_fee + value_fee

    @classmethod
    def _get_required_documents(cls, customs_required: bool, border_info: dict) -> List[str]:
        """Get required documents for border crossing."""
        docs = ["shipping_label"]

        if customs_required:
            docs.extend(["customs_declaration", "invoice", "product_certificate"])

        if not border_info.get("open_border", False):
            docs.append("border_permit")

        return docs


class TimezoneDeliveryCalculator:
    """Calculate delivery times considering timezones and business hours."""

    # Business hours for different regions (24-hour format)
    REGIONAL_BUSINESS_HOURS = {
        "kathmandu": {
            "mon": (9, 18),
            "tue": (9, 18),
            "wed": (9, 18),
            "thu": (9, 18),
            "fri": (9, 18),
            "sat": (9, 15),
            "sun": None,
        },
        "pokhara": {
            "mon": (8, 17),
            "tue": (8, 17),
            "wed": (8, 17),
            "thu": (8, 17),
            "fri": (8, 17),
            "sat": (8, 14),
            "sun": None,
        },
        "default": {
            "mon": (9, 17),
            "tue": (9, 17),
            "wed": (9, 17),
            "thu": (9, 17),
            "fri": (9, 17),
            "sat": (9, 14),
            "sun": None,
        },
    }

    # Nepal public holidays (simplified)
    NEPAL_HOLIDAYS = [
        "2024-04-14",  # Nepali New Year
        "2024-05-01",  # Labor Day
        "2024-08-20",  # Janai Purnima
        "2024-10-15",  # Dashain
        "2024-11-02",  # Tihar
    ]

    @classmethod
    def calculate_delivery_estimate(
        cls, pickup_lat: float, pickup_lon: float, delivery_lat: float, delivery_lon: float, base_delivery_hours: int = 24
    ) -> TimeZoneDeliveryEstimate:
        """Calculate timezone-aware delivery estimate."""

        # Nepal is UTC+5:45
        from django.utils import timezone as django_timezone

        nepal_tz = timezone(timedelta(hours=5, minutes=45))
        current_time = django_timezone.now().astimezone(nepal_tz)

        # Determine region for business hours
        region = cls._get_region_from_coordinates(pickup_lat, pickup_lon)
        business_hours = cls.REGIONAL_BUSINESS_HOURS.get(region, cls.REGIONAL_BUSINESS_HOURS["default"])

        # Calculate pickup time (next business hour)
        pickup_time = cls._next_business_time(current_time, business_hours)

        # Calculate delivery time accounting for business hours and holidays
        delivery_time = pickup_time + timedelta(hours=base_delivery_hours)
        delivery_time = cls._adjust_for_business_hours_and_holidays(delivery_time, business_hours)

        return TimeZoneDeliveryEstimate(
            local_timezone="UTC+5:45",
            estimated_pickup_time=pickup_time,
            estimated_delivery_time=delivery_time,
            business_hours=business_hours,
            holiday_adjustments=cls._get_upcoming_holidays(),
        )

    @classmethod
    def _get_region_from_coordinates(cls, lat: float, lon: float) -> str:
        """Determine region from coordinates."""
        # Kathmandu valley
        if 27.6 <= lat <= 27.8 and 85.2 <= lon <= 85.4:
            return "kathmandu"
        # Pokhara
        elif 28.1 <= lat <= 28.3 and 83.8 <= lon <= 84.1:
            return "pokhara"
        else:
            return "default"

    @classmethod
    def _next_business_time(cls, current_time: datetime, business_hours: dict) -> datetime:
        """Find next available business time."""
        weekday = current_time.strftime("%a").lower()

        today_hours = business_hours.get(weekday)
        if today_hours and today_hours[0] <= current_time.hour < today_hours[1]:
            # Currently in business hours
            return current_time

        # Find next business day
        days_to_add = 0
        for i in range(7):  # Check next 7 days
            check_date = current_time + timedelta(days=i)
            weekday = check_date.strftime("%a").lower()
            day_hours = business_hours.get(weekday)

            if day_hours:
                opening_time = check_date.replace(hour=day_hours[0], minute=0, second=0)
                if opening_time > current_time:
                    return opening_time

        # Fallback to next Monday 9 AM
        days_until_monday = (7 - current_time.weekday()) % 7
        next_monday = current_time + timedelta(days=days_until_monday)
        return next_monday.replace(hour=9, minute=0, second=0)

    @classmethod
    def _adjust_for_business_hours_and_holidays(cls, delivery_time: datetime, business_hours: dict) -> datetime:
        """Adjust delivery time for business hours and holidays."""
        # Check if delivery time falls on a holiday
        delivery_date_str = delivery_time.date().isoformat()
        if delivery_date_str in cls.NEPAL_HOLIDAYS:
            # Move to next business day
            delivery_time += timedelta(days=1)
            return cls._next_business_time(delivery_time, business_hours)

        # Ensure delivery is during business hours
        weekday = delivery_time.strftime("%a").lower()
        day_hours = business_hours.get(weekday)

        if not day_hours:
            # Not a business day, move to next business day
            return cls._next_business_time(delivery_time, business_hours)

        if delivery_time.hour < day_hours[0]:
            # Before business hours, move to opening
            delivery_time = delivery_time.replace(hour=day_hours[0], minute=0)
        elif delivery_time.hour >= day_hours[1]:
            # After business hours, move to next business day
            delivery_time += timedelta(days=1)
            return cls._next_business_time(delivery_time, business_hours)

        return delivery_time

    @classmethod
    def _get_upcoming_holidays(cls) -> List[datetime]:
        """Get upcoming holidays for adjustment calculations."""
        current_date = timezone.now().date()
        upcoming = []

        for holiday_str in cls.NEPAL_HOLIDAYS:
            holiday_date = datetime.fromisoformat(holiday_str).date()
            if holiday_date >= current_date:
                upcoming.append(holiday_date)

        return upcoming


class MobileConnectivityHandler:
    """Handle mobile connectivity scenarios for location services."""

    @classmethod
    def detect_connectivity_mode(cls, request) -> ConnectivityMode:
        """Detect user's connectivity mode from request headers."""
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
        connection_type = request.META.get("HTTP_CONNECTION", "").lower()

        # Check for mobile indicators
        is_mobile = any(mobile in user_agent for mobile in ["mobile", "android", "iphone"])

        # Check for slow connection indicators
        if "slow-2g" in connection_type or "save-data" in request.META.get("HTTP_SAVE_DATA", ""):
            return ConnectivityMode.SLOW_CONNECTION

        # Check for offline capability indicators
        if request.META.get("HTTP_X_OFFLINE_CAPABLE"):
            return ConnectivityMode.OFFLINE_CAPABLE

        return ConnectivityMode.ONLINE

    @classmethod
    def optimize_response_for_connectivity(cls, data: dict, connectivity_mode: ConnectivityMode) -> dict:
        """Optimize API response based on connectivity mode."""
        if connectivity_mode == ConnectivityMode.SLOW_CONNECTION:
            # Reduce data size for slow connections
            return cls._reduce_response_size(data)
        elif connectivity_mode == ConnectivityMode.OFFLINE_CAPABLE:
            # Add offline caching hints
            data["cache_duration"] = 3600  # 1 hour
            data["offline_available"] = True
        elif connectivity_mode == ConnectivityMode.EMERGENCY_ONLY:
            # Only essential data
            return cls._emergency_response_only(data)

        return data

    @classmethod
    def _reduce_response_size(cls, data: dict) -> dict:
        """Reduce response size for slow connections."""
        # Remove non-essential fields
        if "products" in data:
            for product in data["products"]:
                # Keep only essential fields
                essential_fields = ["id", "name", "price", "distance_km", "available"]
                product_filtered = {k: v for k, v in product.items() if k in essential_fields}
                product.clear()
                product.update(product_filtered)

        # Remove metadata for slower connections
        data.pop("facets", None)
        data.pop("debug_info", None)

        return data

    @classmethod
    def _emergency_response_only(cls, data: dict) -> dict:
        """Return only emergency-essential data."""
        return {
            "products": data.get("products", [])[:5],  # Max 5 products
            "total_count": min(data.get("total_count", 0), 5),
            "emergency_mode": True,
        }


class SeasonalAvailabilityManager:
    """Manage seasonal availability of products based on location and time."""

    SEASONAL_PATTERNS = {
        "agriculture": {
            SeasonalAvailability.MONSOON_DEPENDENT: {
                "months": [6, 7, 8, 9],  # June-September
                "regions": ["kathmandu", "pokhara", "chitwan"],
                "multiplier": 1.5,  # Higher availability during monsoon
            },
            SeasonalAvailability.WINTER_ONLY: {
                "months": [12, 1, 2, 3],  # December-March
                "regions": ["mustang", "manang"],
                "multiplier": 2.0,
            },
        },
        "handicrafts": {
            SeasonalAvailability.FESTIVAL_SEASONAL: {
                "months": [9, 10, 11],  # Festival season
                "regions": ["all"],
                "multiplier": 3.0,  # Much higher during festivals
            }
        },
    }

    @classmethod
    def adjust_availability_for_season(cls, products_queryset, current_month: int, region: str, category: str):
        """Adjust product availability based on seasonal patterns."""
        patterns = cls.SEASONAL_PATTERNS.get(category, {})

        availability_multipliers = {}

        for seasonal_type, pattern in patterns.items():
            if current_month in pattern["months"]:
                if region in pattern["regions"] or "all" in pattern["regions"]:
                    availability_multipliers[seasonal_type] = pattern["multiplier"]

        # If no seasonal patterns apply, return original queryset
        if not availability_multipliers:
            return products_queryset

        # Apply seasonal filtering/boosting logic
        # This is a simplified example - in practice, you'd have seasonal flags in your models
        return products_queryset.annotate(
            seasonal_boost=Value(max(availability_multipliers.values(), default=1.0))
        ).order_by("-seasonal_boost", "distance_km")


class EmergencyModeManager:
    """Handle emergency mode operations for location services."""

    EMERGENCY_CONFIGURATIONS = {
        EmergencyMode.WEATHER_ALERT: {
            "max_delivery_distance_km": 5,
            "priority_categories": ["medical", "food", "emergency_supplies"],
            "delivery_surcharge_multiplier": 1.5,
            "response_timeout_seconds": 10,
        },
        EmergencyMode.DISASTER_RESPONSE: {
            "max_delivery_distance_km": 2,
            "priority_categories": ["medical", "emergency_supplies"],
            "delivery_surcharge_multiplier": 0,  # Free delivery during disasters
            "response_timeout_seconds": 5,
        },
        EmergencyMode.SUPPLY_SHORTAGE: {
            "max_delivery_distance_km": 10,
            "priority_categories": ["food", "water", "fuel"],
            "delivery_surcharge_multiplier": 2.0,
            "response_timeout_seconds": 15,
        },
    }

    @classmethod
    def get_current_emergency_mode(cls) -> EmergencyMode:
        """Get current emergency mode from cache or external service."""
        cached_mode = cache.get("emergency_mode")
        if cached_mode:
            return EmergencyMode(cached_mode)

        # Check external weather/disaster APIs here
        # For now, return normal mode
        return EmergencyMode.NORMAL

    @classmethod
    def apply_emergency_restrictions(
        cls, products_queryset, emergency_mode: EmergencyMode, user_location_lat: float, user_location_lon: float
    ):
        """Apply emergency mode restrictions to product queries."""
        if emergency_mode == EmergencyMode.NORMAL:
            return products_queryset

        config = cls.EMERGENCY_CONFIGURATIONS[emergency_mode]

        # Filter by maximum distance
        max_distance = config["max_delivery_distance_km"]

        # Filter by priority categories if in emergency mode
        priority_categories = config["priority_categories"]
        if priority_categories:
            products_queryset = products_queryset.filter(product__category__in=priority_categories)

        # Apply distance restriction (simplified - would use PostGIS in practice)
        return products_queryset[:50]  # Limit results in emergency mode

    @classmethod
    def get_emergency_delivery_info(cls, emergency_mode: EmergencyMode, base_cost: Decimal) -> dict:
        """Calculate emergency delivery information."""
        if emergency_mode == EmergencyMode.NORMAL:
            return {"surcharge": Decimal("0"), "priority": "normal"}

        config = cls.EMERGENCY_CONFIGURATIONS[emergency_mode]
        surcharge_multiplier = config["delivery_surcharge_multiplier"]

        return {
            "surcharge": base_cost * Decimal(str(surcharge_multiplier)),
            "priority": "emergency",
            "mode": emergency_mode.value,
            "estimated_hours": 2 if emergency_mode == EmergencyMode.DISASTER_RESPONSE else 4,
        }


class GDPRLocationComplianceManager:
    """Handle GDPR compliance for location data processing."""

    @classmethod
    def check_location_consent(cls, user, request_ip: str) -> dict:
        """Check if user has given consent for location processing."""
        # Check if user has given explicit consent
        consent_record = None  # Would check user's consent records from database

        # Check if request is from EU (simplified IP-based check)
        is_eu_request = cls._is_eu_ip(request_ip)

        return {
            "consent_required": is_eu_request,
            "consent_given": consent_record is not None,
            "can_process_location": not is_eu_request or consent_record is not None,
            "retention_days": 365 if consent_record else 0,
        }

    @classmethod
    def anonymize_location_data(cls, lat: float, lon: float, precision_level: str = "city") -> Tuple[float, float]:
        """Anonymize location data to reduce precision."""
        if precision_level == "city":
            # Round to ~1km precision
            return round(lat, 2), round(lon, 2)
        elif precision_level == "region":
            # Round to ~10km precision
            return round(lat, 1), round(lon, 1)
        elif precision_level == "country":
            # Round to ~100km precision
            return round(lat, 0), round(lon, 0)

        return lat, lon

    @classmethod
    def _is_eu_ip(cls, ip: str) -> bool:
        """Check if IP address is from EU (simplified)."""
        # In practice, use a proper GeoIP service
        # This is a simplified placeholder
        eu_ip_ranges = ["192.168."]  # Placeholder
        return any(ip.startswith(range_prefix) for range_prefix in eu_ip_ranges)

    @classmethod
    def get_data_retention_policy(cls, user_type: str) -> dict:
        """Get data retention policy based on user type and legal requirements."""
        policies = {
            "anonymous": {"retention_days": 1, "can_profile": False},
            "registered": {"retention_days": 365, "can_profile": True},
            "business": {"retention_days": 2555, "can_profile": True},  # 7 years for business
        }

        return policies.get(user_type, policies["registered"])


# Utility function to integrate all edge case handlers
def get_comprehensive_edge_case_handlers():
    """Get all edge case handlers for integration."""
    return {
        "cross_border": CrossBorderDeliveryHandler,
        "timezone": TimezoneDeliveryCalculator,
        "mobile": MobileConnectivityHandler,
        "seasonal": SeasonalAvailabilityManager,
        "emergency": EmergencyModeManager,
        "gdpr": GDPRLocationComplianceManager,
    }
