from math import atan2, cos, radians, sin, sqrt

from django.db.models import Case, F, FloatField, Q, Value, When
from django.db.models.functions import ATan2, Cos, Power, Radians, Sin, Sqrt

from transport.models import Delivery, TransportStatus


class DeliverySuggestionService:
    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the great circle distance between two points
        on the earth specified in decimal degrees
        """
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        r = 6371  # Radius of Earth in kilometers
        return r * c

    def get_suggested_deliveries(self, latitude, longitude, max_distance_km=20, vehicle_type=None, limit=10):
        """
        Get suggested deliveries for a transporter based on their location
        """
        # First filter by status and other basic criteria
        queryset = (
            Delivery.objects.filter(status=TransportStatus.AVAILABLE)
            .select_related("marketplace_sale", "marketplace_sale__seller")
            .prefetch_related("items")
        )

        # If vehicle type is specified, filter by compatible vehicle types
        if vehicle_type:
            queryset = queryset.filter(Q(required_vehicle_type=vehicle_type) | Q(required_vehicle_type__isnull=True))

        # Annotate with distance calculation
        queryset = queryset.annotate(
            distance_km=Case(
                When(
                    pickup_latitude__isnull=False,
                    pickup_longitude__isnull=False,
                    then=Sqrt(
                        Power(Radians(F("pickup_latitude") - latitude) * 111.32, 2)
                        + Power(
                            (Radians(F("pickup_longitude") - longitude) * 111.32 * Cos(Radians(F("pickup_latitude")))), 2
                        )
                    ),
                ),
                default=Value(float("inf")),
                output_field=FloatField(),
            )
        )

        # Filter by max distance and order by distance and priority
        queryset = queryset.filter(distance_km__lte=max_distance_km).order_by("distance_km", "-priority")

        return queryset[:limit]
