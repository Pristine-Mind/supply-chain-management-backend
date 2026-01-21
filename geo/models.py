from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GistIndex
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class GeographicZone(gis_models.Model):
    """
    Represents a geographic zone/region for sales and delivery.

    Features:
    - Polygon or circle-based boundaries
    - Tiered delivery configuration
    - Shipping cost and delivery time estimation

    Example:
        # Create circular zone
        zone = GeographicZone.objects.create(
            name="Kathmandu City",
            center_latitude=27.7172,
            center_longitude=85.3240,
            radius_km=15,
            tier="tier1",
            shipping_cost=Decimal("0"),
            estimated_delivery_days=1
        )
    """

    TIER_CHOICES = [
        ("tier1", _("Tier 1 (0-5km) - Premium/Same-day")),
        ("tier2", _("Tier 2 (5-25km) - Standard")),
        ("tier3", _("Tier 3 (25-50km) - Economy")),
        ("tier4", _("Tier 4 (50km+) - Remote")),
    ]

    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name=_("Zone Name"),
        help_text=_("e.g., 'Kathmandu City', 'Pokhara Valley'"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
    )

    # Geometry: Polygon for regions, Point for delivery centers
    geometry = gis_models.GeometryField(
        srid=4326,
        null=True,
        blank=True,
        verbose_name=_("Geographic Boundary"),
        help_text=_("Polygon boundary or center point (WGS 84)"),
    )

    # Alternative: Circle-based zone (center point + radius)
    center_latitude = models.FloatField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ],
        verbose_name=_("Center Latitude"),
    )

    center_longitude = models.FloatField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ],
        verbose_name=_("Center Longitude"),
    )

    radius_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Radius (km)"),
        help_text=_("Radius in kilometers if using circular zone"),
    )

    # Delivery configuration
    tier = models.CharField(
        max_length=20,
        choices=TIER_CHOICES,
        db_index=True,
        verbose_name=_("Delivery Tier"),
        help_text=_("Used for determining delivery costs and times"),
    )

    shipping_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name=_("Shipping Cost"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    estimated_delivery_days = models.PositiveIntegerField(
        default=3,
        verbose_name=_("Estimated Delivery Days"),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Geographic Zone")
        verbose_name_plural = _("Geographic Zones")
        ordering = ["tier", "name"]
        indexes = [
            GistIndex(fields=["geometry"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"

    def clean(self):
        """Validate zone has either geometry or circle definition"""
        has_geometry = self.geometry is not None
        has_circle = self.center_latitude is not None and self.center_longitude is not None and self.radius_km is not None

        if not has_geometry and not has_circle:
            raise ValidationError(_("Zone must have either geometry or circle definition (center + radius)"))

    def contains_point(self, latitude, longitude):
        """
        Check if point is within zone.

        Args:
            latitude: Point latitude
            longitude: Point longitude

        Returns:
            bool: True if point is in zone
        """
        from django.contrib.gis.geos import Point

        point = Point(longitude, latitude, srid=4326)

        # Check geometric containment
        if self.geometry:
            return self.geometry.contains(point)

        # Check circle containment
        if self.center_latitude and self.center_longitude and self.radius_km:
            distance_km = self.distance_to_point_km(latitude, longitude)
            return distance_km <= self.radius_km

        return False

    def distance_to_point_km(self, latitude, longitude):
        """
        Calculate distance from zone to point.

        Args:
            latitude: Point latitude
            longitude: Point longitude

        Returns:
            float: Distance in kilometers
        """
        from django.contrib.gis.geos import Point

        point = Point(longitude, latitude, srid=4326)

        if self.geometry:
            distance_m = self.geometry.distance(point)
            return (distance_m / 1000) if distance_m else float("inf")

        if self.center_latitude and self.center_longitude:
            # Haversine distance
            from math import asin, cos, radians, sin, sqrt

            lat1, lon1 = radians(self.center_latitude), radians(self.center_longitude)
            lat2, lon2 = radians(latitude), radians(longitude)

            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            c = 2 * asin(sqrt(a))
            km = 6371 * c
            return km

        return float("inf")


class SaleRegion(models.Model):
    """
    Represents a specific region where a sale/promotion is active.
    Links geographic zones to sales with restrictions.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Region Name"),
        help_text=_("e.g., 'Kathmandu Weekend Sale'"),
    )

    zone = models.ForeignKey(
        GeographicZone,
        on_delete=models.CASCADE,
        related_name="sales",
        verbose_name=_("Geographic Zone"),
    )

    is_restricted = models.BooleanField(
        default=False,
        verbose_name=_("Is Restricted"),
        help_text=_("If True, only allowed countries/cities can purchase"),
    )

    allowed_countries = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Allowed Countries"),
        help_text=_("ISO 3166-1 alpha-2 codes: ['NP', 'IN']"),
    )

    allowed_cities = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Allowed Cities"),
        help_text=_("List of allowed city names"),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Sale Region")
        verbose_name_plural = _("Sale Regions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.zone.name}"

    def is_location_allowed(self, latitude, longitude, country_code=None, city_name=None):
        """Check if location is allowed for this sale"""
        if not self.is_restricted:
            return True

        if self.allowed_countries and country_code:
            if country_code not in self.allowed_countries:
                return False

        if self.allowed_cities and city_name:
            if city_name not in self.allowed_cities:
                return False

        return self.zone.contains_point(latitude, longitude)


class UserLocationSnapshot(models.Model):
    """
    Stores user's location snapshots for analytics and delivery optimization.
    More efficient than continuous caching, provides history for analysis.

    Example:
        snapshot = UserLocationSnapshot.objects.create(
            user=user,
            latitude=27.7172,
            longitude=85.3240,
            accuracy_meters=10,
            session_id='session_abc123'
        )
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="location_snapshots",
        verbose_name=_("User"),
    )

    latitude = models.FloatField(
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ],
        verbose_name=_("Latitude"),
    )

    longitude = models.FloatField(
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ],
        verbose_name=_("Longitude"),
    )

    geo_point = gis_models.PointField(
        srid=4326,
        verbose_name=_("Geographic Point"),
    )

    zone = models.ForeignKey(
        GeographicZone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_snapshots",
        verbose_name=_("Detected Zone"),
    )

    accuracy_meters = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("GPS Accuracy (meters)"),
    )

    session_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name=_("Session ID"),
        help_text=_("For tracking user session"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        verbose_name = _("User Location Snapshot")
        verbose_name_plural = _("User Location Snapshots")
        ordering = ["-created_at"]
        indexes = [
            GistIndex(fields=["geo_point"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} at ({self.latitude:.4f}, {self.longitude:.4f})"

    def save(self, *args, **kwargs):
        """Auto-update geo_point and detect zone"""
        from django.contrib.gis.geos import Point

        self.geo_point = Point(self.longitude, self.latitude, srid=4326)

        # Auto-detect zone
        try:
            self.zone = GeographicZone.objects.filter(
                geometry__contains=self.geo_point,
                is_active=True,
            ).first()
        except Exception:
            self.zone = None

        super().save(*args, **kwargs)
