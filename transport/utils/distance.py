import math
from typing import Optional


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth using Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of the first point in decimal degrees
        lat2, lon2: Latitude and longitude of the second point in decimal degrees

    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of Earth in kilometers
    r = 6371

    return c * r


def calculate_delivery_distance(delivery) -> Optional[float]:
    """
    Calculate distance for a delivery from pickup to delivery location.

    Args:
        delivery: Delivery model instance

    Returns:
        Distance in kilometers or None if coordinates are missing
    """
    if all([delivery.pickup_latitude, delivery.pickup_longitude, delivery.delivery_latitude, delivery.delivery_longitude]):
        return haversine_distance(
            float(delivery.pickup_latitude),
            float(delivery.pickup_longitude),
            float(delivery.delivery_latitude),
            float(delivery.delivery_longitude),
        )
    return None
