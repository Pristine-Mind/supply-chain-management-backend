import math
from decimal import Decimal

from django.contrib.gis.geos import Point, Polygon
from django.core.management.base import BaseCommand

from geo.models import GeographicZone


class Command(BaseCommand):
    help = "Initialize geographic zones for Nepal"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing zones before creating new ones",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            count = GeographicZone.objects.count()
            GeographicZone.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} existing zones"))

        def create_circle_polygon(center_lat, center_lon, radius_km, num_points=32):
            """
            Create a polygon approximating a circle.

            Args:
                center_lat: Center latitude
                center_lon: Center longitude
                radius_km: Radius in kilometers
                num_points: Number of points to approximate the circle (default 32)

            Returns:
                Polygon object in SRID 4326
            """
            # Earth's radius in kilometers
            earth_radius = 6371.0

            # Convert radius to degrees (approximate)
            # At the equator, 1 degree ≈ 111 km
            # Adjust for latitude
            lat_rad = math.radians(center_lat)
            radius_lat = radius_km / 111.0
            radius_lon = radius_km / (111.0 * math.cos(lat_rad))

            points = []
            for i in range(num_points):
                angle = (2 * math.pi * i) / num_points
                dx = radius_lon * math.cos(angle)
                dy = radius_lat * math.sin(angle)
                points.append((center_lon + dx, center_lat + dy))

            # Close the polygon by adding the first point at the end
            points.append(points[0])

            return Polygon(points, srid=4326)

        zones_data = [
            # ==================================================
            # KATHMANDU (Center: New Road)
            # ==================================================
            {
                "name": "Kathmandu Core",
                "description": "New Road, Asan, Indra Chowk, Ratnapark",
                "center_latitude": 27.7041,
                "center_longitude": 85.3069,
                "radius_km": 4,
                "tier": "tier1",
                "shipping_cost": Decimal("100.00"),
                "estimated_delivery_days": 1,
                "geometry": create_circle_polygon(27.7041, 85.3069, 4),
            },
            {
                "name": "Kathmandu Mid",
                "description": "Thamel, Putalisadak, Baneshwor, Kalanki, Chabahil",
                "center_latitude": 27.7041,
                "center_longitude": 85.3069,
                "radius_km": 8,
                "tier": "tier1",
                "shipping_cost": Decimal("100.00"),
                "estimated_delivery_days": 1,
                "geometry": create_circle_polygon(27.7041, 85.3069, 8),
            },
            {
                "name": "Kathmandu Outer",
                "description": "Koteshwor, Kirtipur, Budhanilkantha, Tokha",
                "center_latitude": 27.7041,
                "center_longitude": 85.3069,
                "radius_km": 15,
                "tier": "tier2",
                "shipping_cost": Decimal("180.00"),
                "estimated_delivery_days": 2,
                "geometry": create_circle_polygon(27.7041, 85.3069, 15),
            },
            # ==================================================
            # LALITPUR (Center: Patan Durbar Square)
            # ==================================================
            {
                "name": "Lalitpur Core",
                "description": "Patan, Mangalbazar, Jawalakhel, Pulchowk",
                "center_latitude": 27.6644,
                "center_longitude": 85.3188,
                "radius_km": 4,
                "tier": "tier2",
                "shipping_cost": Decimal("150.00"),
                "estimated_delivery_days": 2,
                "geometry": create_circle_polygon(27.6644, 85.3188, 4),
            },
            {
                "name": "Lalitpur Mid",
                "description": "Lagankhel, Kupondole, Gwarko, Satdobato",
                "center_latitude": 27.6644,
                "center_longitude": 85.3188,
                "radius_km": 8,
                "tier": "tier2",
                "shipping_cost": Decimal("180.00"),
                "estimated_delivery_days": 2,
                "geometry": create_circle_polygon(27.6644, 85.3188, 8),
            },
            {
                "name": "Lalitpur Outer",
                "description": "Imadol, Bhaisepati, Godawari, Lubhu",
                "center_latitude": 27.6644,
                "center_longitude": 85.3188,
                "radius_km": 15,
                "tier": "tier3",
                "shipping_cost": Decimal("250.00"),
                "estimated_delivery_days": 3,
                "geometry": create_circle_polygon(27.6644, 85.3188, 15),
            },
            # ==================================================
            # BHAKTAPUR (Center: Bhaktapur Durbar Square)
            # ==================================================
            {
                "name": "Bhaktapur Core",
                "description": "Bhaktapur Durbar Square, Taumadhi, Dattatreya",
                "center_latitude": 27.6710,
                "center_longitude": 85.4298,
                "radius_km": 4,
                "tier": "tier2",
                "shipping_cost": Decimal("180.00"),
                "estimated_delivery_days": 2,
                "geometry": create_circle_polygon(27.6710, 85.4298, 4),
            },
            {
                "name": "Bhaktapur Mid",
                "description": "Suryabinayak, Madhyapur Thimi, Lokanthali",
                "center_latitude": 27.6710,
                "center_longitude": 85.4298,
                "radius_km": 8,
                "tier": "tier3",
                "shipping_cost": Decimal("220.00"),
                "estimated_delivery_days": 3,
                "geometry": create_circle_polygon(27.6710, 85.4298, 8),
            },
            {
                "name": "Bhaktapur Outer",
                "description": "Changunarayan, Nagarkot, Tathali",
                "center_latitude": 27.6710,
                "center_longitude": 85.4298,
                "radius_km": 15,
                "tier": "tier3",
                "shipping_cost": Decimal("280.00"),
                "estimated_delivery_days": 3,
                "geometry": create_circle_polygon(27.6710, 85.4298, 15),
            },
            # ==================================================
            # KATHMANDU VALLEY FALLBACK
            # ==================================================
            {
                "name": "Kathmandu Valley Extended",
                "description": "Dhulikhel, Sankhu, Bungamati, outskirts",
                "center_latitude": 27.7041,
                "center_longitude": 85.3069,
                "radius_km": 30,
                "tier": "tier3",
                "shipping_cost": Decimal("350.00"),
                "estimated_delivery_days": 4,
                "geometry": create_circle_polygon(27.7041, 85.3069, 30),
            },
            # ==================================================
            # REMOTE FALLBACK
            # ==================================================
            {
                "name": "Remote Areas – Nepal",
                "description": "Remote and hard-to-reach locations",
                "center_latitude": 28.0000,
                "center_longitude": 84.0000,
                "radius_km": 100,
                "tier": "tier4",
                "shipping_cost": Decimal("750.00"),
                "estimated_delivery_days": 7,
                "geometry": create_circle_polygon(28.0000, 84.0000, 100),
            },
        ]

        created_zones = []
        for zone_data in zones_data:
            zone, created = GeographicZone.objects.get_or_create(name=zone_data["name"], defaults=zone_data)
            created_zones.append((zone.name, created))

        self.stdout.write(self.style.SUCCESS("\nGeographic Zones Summary:"))
        self.stdout.write("=" * 60)

        for zone_name, created in created_zones:
            status = "CREATED" if created else "ALREADY EXISTS"
            style_func = self.style.SUCCESS if created else self.style.WARNING
            self.stdout.write(style_func(f"  {zone_name}: {status}"))

        total_zones = GeographicZone.objects.count()
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS(f"\nTotal zones: {total_zones}"))
