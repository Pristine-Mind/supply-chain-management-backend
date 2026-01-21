from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.contrib.auth.models import User
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db import models
from django.utils.translation import gettext_lazy as _

from .models import GeographicZone, SaleRegion, UserLocationSnapshot


class GeoLocationService:
    """
    Core location management service.
    Handles user location tracking, zone detection, and distance calculations.

    Usage:
        service = GeoLocationService()
        zone = service.get_user_zone(user, latitude, longitude)
        distance = service.calculate_distance(lat1, lon1, lat2, lon2)
    """

    @staticmethod
    def create_location_snapshot(
        user: User,
        latitude: float,
        longitude: float,
        accuracy_meters: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> UserLocationSnapshot:
        """
        Create a location snapshot for user.

        Args:
            user: User instance
            latitude: User latitude
            longitude: User longitude
            accuracy_meters: GPS accuracy
            session_id: Optional session identifier

        Returns:
            UserLocationSnapshot instance

        Raises:
            ValueError: If coordinates are invalid
        """
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError(_("Invalid coordinates"))

        snapshot = UserLocationSnapshot.objects.create(
            user=user,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy_meters,
            session_id=session_id,
        )
        return snapshot

    @staticmethod
    def get_user_zone(
        user: User,
        latitude: float,
        longitude: float,
    ) -> Optional[GeographicZone]:
        """
        Detect which geographic zone user is in.

        Args:
            user: User instance
            latitude: User latitude
            longitude: User longitude

        Returns:
            GeographicZone instance or None
        """
        point = Point(longitude, latitude, srid=4326)

        # First check geometry-based zones (polygon)
        zone = (
            GeographicZone.objects.filter(
                geometry__contains=point,
                is_active=True,
            )
            .order_by("-radius_km")
            .first()
        )

        if zone:
            return zone

        # Check circle-based zones (center + radius)
        zones = GeographicZone.objects.filter(
            center_latitude__isnull=False,
            center_longitude__isnull=False,
            radius_km__isnull=False,
            is_active=True,
        )

        closest_zone = None
        min_distance = float("inf")

        for zone in zones:
            distance_km = zone.distance_to_point_km(latitude, longitude)
            if distance_km <= zone.radius_km and distance_km < min_distance:
                closest_zone = zone
                min_distance = distance_km

        return closest_zone

    @staticmethod
    def get_nearby_zones(
        latitude: float,
        longitude: float,
        distance_km: int = 50,
    ) -> List[GeographicZone]:
        """
        Get all zones within distance from point.

        Args:
            latitude: Reference latitude
            longitude: Reference longitude
            distance_km: Search radius

        Returns:
            List of GeographicZone instances ordered by distance
        """
        point = Point(longitude, latitude, srid=4326)

        # Using Django GIS Distance lookup
        zones = (
            GeographicZone.objects.filter(
                geometry__distance_lte=(point, Distance(km=distance_km)),
                is_active=True,
            )
            .annotate(distance=Distance("geometry", point))
            .order_by("distance")
        )

        return list(zones)

    @staticmethod
    def calculate_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calculate haversine distance between two points in km.

        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates

        Returns:
            Distance in kilometers
        """
        from math import asin, cos, radians, sin, sqrt

        lat1_r, lon1_r = radians(lat1), radians(lon1)
        lat2_r, lon2_r = radians(lat2), radians(lon2)

        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r

        a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        return 6371 * c  # Earth radius in km


class GeoProductFilterService:
    """
    Product filtering based on geographic restrictions.
    Integrates with market app's product filtering.

    Usage:
        service = GeoProductFilterService()
        products = service.get_deliverable_products(user, latitude, longitude)
        allowed = service.can_deliver_to_location(product, latitude, longitude)
    """

    def __init__(self):
        self.location_service = GeoLocationService()

    def can_deliver_to_location(
        self,
        product,
        latitude: float,
        longitude: float,
        seller_latitude: Optional[float] = None,
        seller_longitude: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if product can be delivered to specific location.

        Args:
            product: MarketplaceProduct instance
            latitude: Delivery location latitude
            longitude: Delivery location longitude
            seller_latitude: Seller location latitude
            seller_longitude: Seller location longitude

        Returns:
            Tuple: (is_deliverable, reason_if_not)

        Example:
            can_deliver, reason = service.can_deliver_to_location(
                product, 27.7172, 85.3240
            )
            if not can_deliver:
                print(f"Cannot deliver: {reason}")
        """
        # Check if product has geo restrictions enabled
        if not getattr(product, "enable_geo_restrictions", False):
            return True, None

        # Check delivery distance
        max_distance = getattr(product, "max_delivery_distance_km", None)
        if max_distance and seller_latitude and seller_longitude:
            distance = self.location_service.calculate_distance(
                seller_latitude,
                seller_longitude,
                latitude,
                longitude,
            )
            if distance > max_distance:
                return False, _("Beyond maximum delivery distance")

        # Check zone availability
        available_zones = getattr(product, "available_delivery_zones", None)
        if available_zones:
            user_zone = self.location_service.get_user_zone(None, latitude, longitude)
            if user_zone:
                zone_ids = [z["id"] if isinstance(z, dict) else z for z in available_zones]
                if user_zone.id not in zone_ids:
                    return False, _("Not available in your delivery zone")
            else:
                return False, _("Cannot determine your delivery zone")

        return True, None

    def get_deliverable_products(
        self,
        user: User,
        latitude: float,
        longitude: float,
        queryset=None,
    ):
        """
        Filter products that can be delivered to user location.

        Args:
            user: User instance
            latitude: User latitude
            longitude: User longitude
            queryset: Optional initial queryset

        Returns:
            Filtered queryset of deliverable products
        """
        from producer.models import MarketplaceProduct

        if queryset is None:
            queryset = MarketplaceProduct.objects.filter(is_active=True)

        # Get user's zone
        user_zone = self.location_service.get_user_zone(user, latitude, longitude)

        # Filter products
        filtered_products = []
        for product in queryset:
            can_deliver, _ = self.can_deliver_to_location(product, latitude, longitude)
            if can_deliver:
                filtered_products.append(product.id)

        return queryset.filter(id__in=filtered_products)

    def get_delivery_estimate(
        self,
        product,
        latitude: float,
        longitude: float,
        seller_latitude: Optional[float] = None,
        seller_longitude: Optional[float] = None,
    ) -> Dict[str, any]:
        """
        Get delivery estimate for product to location.

        Args:
            product: MarketplaceProduct instance
            latitude: Delivery latitude
            longitude: Delivery longitude
            seller_latitude: Seller latitude
            seller_longitude: Seller longitude

        Returns:
            Dict with delivery info: {
                'estimated_days': int,
                'shipping_cost': Decimal,
                'zone': str,
                'is_same_day': bool,
            }
        """
        user_zone = self.location_service.get_user_zone(None, latitude, longitude)

        estimate = {
            "estimated_days": 3,  # Default
            "shipping_cost": Decimal("0"),
            "zone": None,
            "is_same_day": False,
        }

        if user_zone:
            estimate["zone"] = user_zone.name
            estimate["estimated_days"] = user_zone.estimated_delivery_days
            estimate["shipping_cost"] = user_zone.shipping_cost
            estimate["is_same_day"] = user_zone.tier == "tier1"

        return estimate


class GeoAnalyticsService:
    """
    Analytics for geographic data.
    Tracks location-based sales, popular zones, etc.

    Usage:
        service = GeoAnalyticsService()
        popular_zones = service.get_popular_zones()
        coverage = service.get_coverage_percentage()
    """

    @staticmethod
    def get_popular_zones(limit: int = 10) -> List[Dict]:
        """
        Get most popular/active geographic zones.

        Args:
            limit: Number of zones to return

        Returns:
            List of zone data with user counts
        """
        zones = (
            GeographicZone.objects.filter(is_active=True)
            .annotate(user_count=models.Count("user_snapshots", distinct=True))
            .order_by("-user_count")[:limit]
        )

        return [
            {
                "id": zone.id,
                "name": zone.name,
                "tier": zone.tier,
                "user_count": zone.user_count,
            }
            for zone in zones
        ]

    @staticmethod
    def get_coverage_percentage() -> float:
        """Calculate percentage of users in tracked zones"""
        from django.contrib.auth.models import User

        total_users = User.objects.count()
        if not total_users:
            return 0.0

        tracked_users = UserLocationSnapshot.objects.values("user").distinct().count()
        return round((tracked_users / total_users) * 100, 2)

    @staticmethod
    def get_zone_statistics(zone_id: int) -> Dict:
        """
        Get statistics for specific zone.

        Args:
            zone_id: GeographicZone ID

        Returns:
            Statistics dict
        """
        from django.db.models import Avg, Count, Max, Min

        zone = GeographicZone.objects.get(id=zone_id)
        snapshots = UserLocationSnapshot.objects.filter(zone=zone)

        return {
            "zone_id": zone.id,
            "zone_name": zone.name,
            "total_snapshots": snapshots.count(),
            "unique_users": snapshots.values("user").distinct().count(),
            "first_snapshot": snapshots.aggregate(Min("created_at"))["created_at__min"],
            "last_snapshot": snapshots.aggregate(Max("created_at"))["created_at__max"],
        }


def calculate_delivery_estimate(user_location, product):
    """
    Calculate delivery cost and time based on user location and product.

    Args:
        user_location: Dict with 'latitude' and 'longitude'
        product: MarketplaceProduct instance

    Returns:
        Dict with shipping_cost, estimated_delivery_days, estimated_delivery_date, zone info
    """
    from datetime import timedelta

    from django.contrib.gis.geos import Point
    from django.utils import timezone

    point = Point(user_location["longitude"], user_location["latitude"], srid=4326)

    # Find nearest zone using Distance lookup
    zone = (
        GeographicZone.objects.filter(is_active=True)
        .annotate(distance=Distance("geometry", point))
        .order_by("distance")
        .first()
    )

    if not zone:
        # Fallback to default
        return {
            "shipping_cost": Decimal("300"),
            "estimated_delivery_days": 7,
            "zone_name": "Remote Area",
            "estimated_delivery_date": (timezone.now() + timedelta(days=7)).date().isoformat(),
        }

    # Calculate estimated delivery date
    estimated_date = (timezone.now() + timedelta(days=zone.estimated_delivery_days)).date()

    return {
        "shipping_cost": zone.shipping_cost,
        "estimated_delivery_days": zone.estimated_delivery_days,
        "estimated_delivery_date": estimated_date.isoformat(),
        "zone_name": zone.name,
        "zone_tier": zone.get_tier_display() if hasattr(zone, "get_tier_display") else zone.tier,
    }


def is_product_available_for_user(product, user_location, country_code="NP"):
    """
    Check if product can be sold to user based on restrictions.

    Args:
        product: MarketplaceProduct instance
        user_location: Dict with 'latitude' and 'longitude'
        country_code: Country code for user

    Returns:
        bool: True if product is available for user
    """
    from django.contrib.gis.geos import Point

    if not getattr(product, "sale_restricted_to_regions", None):
        return True  # No restrictions

    user_point = Point(user_location["longitude"], user_location["latitude"], srid=4326)

    for region_id in product.sale_restricted_to_regions:
        try:
            region = SaleRegion.objects.get(id=region_id)
            # Check if location is in region
            if region.geometry and region.geometry.contains(user_point):
                return True
        except SaleRegion.DoesNotExist:
            continue

    return False


def calculate_product_price_for_user(product, user_location):
    """
    Calculate final price including distance-based adjustments.

    Args:
        product: MarketplaceProduct instance
        user_location: Dict with 'latitude' and 'longitude'

    Returns:
        Decimal: Final price for user
    """
    if not product.seller_geo_point:
        return product.listed_price or Decimal("0")

    user_point = Point(user_location["longitude"], user_location["latitude"], srid=4326)
    distance_m = product.seller_geo_point.distance(user_point)
    distance_km = distance_m / 1000 if distance_m else 0

    base_price = product.listed_price or product.product.price

    # Apply distance-based surcharge
    if distance_km > 50:
        surcharge = base_price * Decimal("0.1")  # 10% surcharge for remote areas
        return base_price + surcharge
    elif distance_km > 25:
        surcharge = base_price * Decimal("0.05")  # 5% surcharge for far areas
        return base_price + surcharge

    return base_price  # No surcharge for nearby


def allocate_stock_by_zone(product, total_stock):
    """
    Allocate product stock to different zones based on population density.

    Args:
        product: MarketplaceProduct instance
        total_stock: Integer total stock to allocate

    Returns:
        Dict with zone_id -> stock allocation
    """
    zones = GeographicZone.objects.filter(is_active=True)

    allocation = {}

    for zone in zones:
        # Allocate based on zone tier and expected popularity
        if zone.tier == "tier1":
            allocation[zone.id] = int(total_stock * 0.4)  # 40% for tier 1 (high priority)
        elif zone.tier == "tier2":
            allocation[zone.id] = int(total_stock * 0.35)  # 35% for tier 2
        elif zone.tier == "tier3":
            allocation[zone.id] = int(total_stock * 0.20)  # 20% for tier 3
        else:
            allocation[zone.id] = int(total_stock * 0.05)  # 5% for tier 4+

    # Update product if it has zone_stock_allocation field
    if hasattr(product, "zone_stock_allocation"):
        product.zone_stock_allocation = allocation
        product.save()

    return allocation


def filter_products_by_seller_radius(queryset, user_location):
    """
    Filter products by seller's service radius capability.

    Args:
        queryset: MarketplaceProduct queryset
        user_location: Dict with 'latitude' and 'longitude'

    Returns:
        Filtered queryset
    """
    user_point = Point(user_location["longitude"], user_location["latitude"], srid=4326)

    # Filter only products from sellers within their service radius
    # This requires the seller to be able to deliver to the user's location
    filtered_ids = []
    for product in queryset.select_related("product__producer"):
        if not product.product.producer:
            continue
        if not product.product.producer.location:
            continue

        distance_m = product.product.producer.location.distance(user_point)
        distance_km = distance_m / 1000 if distance_m else float("inf")
        service_radius = product.product.producer.service_radius_km or 500

        if distance_km <= service_radius:
            filtered_ids.append(product.id)

    return queryset.filter(id__in=filtered_ids)
