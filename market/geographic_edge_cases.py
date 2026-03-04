import logging
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from django.contrib.gis.geos import GEOSException, LineString, Point, Polygon
from django.contrib.gis.measure import Distance
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class GeographicRegion(Enum):
    """Geographic region classifications for special handling."""

    TROPICAL = "tropical"  # Between tropics
    TEMPERATE = "temperate"  # Temperate zones
    POLAR = "polar"  # Polar regions
    INTERNATIONAL_DATE_LINE = "idl"  # Near International Date Line
    EQUATOR = "equator"  # Near equator
    PRIME_MERIDIAN = "prime"  # Near Prime Meridian
    NEPAL = "nepal"  # Nepal-specific region


@dataclass
class CoordinateBounds:
    """Coordinate boundary definitions."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are within bounds."""
        return self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon


class GeographicEdgeCaseHandler:
    """
    Handle geographic edge cases and coordinate system limitations.
    """

    # Define special regions with their bounds
    REGIONS = {
        GeographicRegion.NEPAL: CoordinateBounds(26.3, 30.4, 80.0, 88.2),
        GeographicRegion.POLAR: CoordinateBounds(66.0, 90.0, -180.0, 180.0),  # Arctic
        GeographicRegion.INTERNATIONAL_DATE_LINE: CoordinateBounds(-90.0, 90.0, 170.0, -170.0),
        GeographicRegion.EQUATOR: CoordinateBounds(-10.0, 10.0, -180.0, 180.0),
    }

    # Nepal-specific city bounds for validation
    NEPAL_CITIES = {
        "kathmandu": CoordinateBounds(27.6, 27.8, 85.2, 85.4),
        "pokhara": CoordinateBounds(28.1, 28.3, 83.8, 84.1),
        "chitwan": CoordinateBounds(27.5, 27.8, 84.2, 84.6),
        "butwal": CoordinateBounds(27.6, 27.8, 83.3, 83.5),
        "biratnagar": CoordinateBounds(26.4, 26.6, 87.2, 87.4),
    }

    @classmethod
    def validate_coordinates_comprehensive(cls, latitude: float, longitude: float) -> Dict:
        """
        Comprehensive coordinate validation with edge case detection.

        Returns:
            Dict with validation results and warnings
        """
        result = {
            "valid": True,
            "warnings": [],
            "region": None,
            "corrected_coordinates": None,
            "confidence": 1.0,
        }

        try:
            # Basic range validation
            if not (-90 <= latitude <= 90):
                result["valid"] = False
                result["warnings"].append(f"Latitude {latitude} out of range [-90, 90]")
                return result

            if not (-180 <= longitude <= 180):
                result["valid"] = False
                result["warnings"].append(f"Longitude {longitude} out of range [-180, 180]")
                return result

            # Check for suspicious coordinates
            result.update(cls._check_suspicious_coordinates(latitude, longitude))

            # Detect geographic region
            region = cls._detect_geographic_region(latitude, longitude)
            result["region"] = region

            # Apply region-specific validations
            region_warnings = cls._apply_region_specific_validation(latitude, longitude, region)
            result["warnings"].extend(region_warnings)

            # Check coordinate precision and suggest corrections
            corrected = cls._check_coordinate_precision(latitude, longitude)
            if corrected != (latitude, longitude):
                result["corrected_coordinates"] = corrected
                result["warnings"].append("Coordinates adjusted for precision")

            # Calculate confidence based on validation results
            result["confidence"] = cls._calculate_coordinate_confidence(latitude, longitude, result)

            return result

        except Exception as e:
            logger.error(f"Error in coordinate validation: {e}")
            return {
                "valid": False,
                "warnings": [f"Validation error: {str(e)}"],
                "region": None,
                "corrected_coordinates": None,
                "confidence": 0.0,
            }

    @classmethod
    def _check_suspicious_coordinates(cls, latitude: float, longitude: float) -> Dict:
        """Check for suspicious coordinate patterns."""
        warnings = []

        # Check for null island (0, 0)
        if latitude == 0.0 and longitude == 0.0:
            warnings.append("Coordinates at Null Island (0,0) - likely invalid")

        # Check for rounded coordinates (might be imprecise)
        if latitude == round(latitude) and longitude == round(longitude):
            warnings.append("Coordinates appear to be rounded - precision may be low")

        # Check for coordinates outside populated areas
        if latitude > 85 or latitude < -85:
            warnings.append("Coordinates in extreme polar regions - verify accuracy")

        # Check for unrealistic precision (too many decimal places)
        lat_decimals = len(str(latitude).split(".")[-1]) if "." in str(latitude) else 0
        lon_decimals = len(str(longitude).split(".")[-1]) if "." in str(longitude) else 0

        if lat_decimals > 6 or lon_decimals > 6:
            warnings.append("Unrealistic coordinate precision - may be artificially generated")

        return {"warnings": warnings}

    @classmethod
    def _detect_geographic_region(cls, latitude: float, longitude: float) -> GeographicRegion:
        """Detect which geographic region coordinates belong to."""
        for region, bounds in cls.REGIONS.items():
            if bounds.contains(latitude, longitude):
                return region

        # Default region based on latitude
        if abs(latitude) < 23.5:
            return GeographicRegion.TROPICAL
        elif abs(latitude) < 66.5:
            return GeographicRegion.TEMPERATE
        else:
            return GeographicRegion.POLAR

    @classmethod
    def _apply_region_specific_validation(cls, latitude: float, longitude: float, region: GeographicRegion) -> List[str]:
        """Apply region-specific validation rules."""
        warnings = []

        if region == GeographicRegion.NEPAL:
            # Nepal-specific validations
            if not cls.REGIONS[GeographicRegion.NEPAL].contains(latitude, longitude):
                warnings.append("Coordinates outside Nepal boundaries")
            else:
                # Check if coordinates match known cities
                city_match = cls._find_nearest_nepal_city(latitude, longitude)
                if city_match:
                    warnings.append(f"Coordinates appear to be near {city_match}")

        elif region == GeographicRegion.POLAR:
            warnings.append("Polar region coordinates - distance calculations may be inaccurate")

        elif region == GeographicRegion.INTERNATIONAL_DATE_LINE:
            warnings.append("Near International Date Line - timezone handling required")

        return warnings

    @classmethod
    def _find_nearest_nepal_city(cls, latitude: float, longitude: float) -> Optional[str]:
        """Find the nearest known Nepal city."""
        for city, bounds in cls.NEPAL_CITIES.items():
            if bounds.contains(latitude, longitude):
                return city
        return None

    @classmethod
    def _check_coordinate_precision(cls, latitude: float, longitude: float) -> Tuple[float, float]:
        """Check and adjust coordinate precision for optimal usage."""
        # Round to 6 decimal places (approximately 0.1 meter precision)
        lat_rounded = round(latitude, 6)
        lon_rounded = round(longitude, 6)

        return lat_rounded, lon_rounded

    @classmethod
    def _calculate_coordinate_confidence(cls, latitude: float, longitude: float, validation_result: Dict) -> float:
        """Calculate confidence score for coordinates."""
        confidence = 1.0

        # Reduce confidence for each warning
        warning_count = len(validation_result["warnings"])
        confidence -= warning_count * 0.1

        # Special penalties
        warnings_text = " ".join(validation_result["warnings"]).lower()

        if "null island" in warnings_text:
            confidence -= 0.5
        if "polar region" in warnings_text:
            confidence -= 0.2
        if "precision" in warnings_text:
            confidence -= 0.1

        return max(0.0, min(1.0, confidence))


class DistanceCalculationHandler:
    """
    Handle distance calculations with edge case considerations.
    """

    @staticmethod
    def calculate_distance_robust(lat1: float, lon1: float, lat2: float, lon2: float, method: str = "haversine") -> Dict:
        """
        Calculate distance with robust error handling and method selection.

        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            method: Calculation method ('haversine', 'vincenty', 'geodesic')

        Returns:
            Dict with distance and metadata
        """
        try:
            # Validate inputs
            for coord, name in [(lat1, "lat1"), (lon1, "lon1"), (lat2, "lat2"), (lon2, "lon2")]:
                if not isinstance(coord, (int, float)) or math.isnan(coord) or math.isinf(coord):
                    raise ValueError(f"Invalid coordinate: {name}={coord}")

            # Choose appropriate method based on coordinates
            if method == "auto":
                method = DistanceCalculationHandler._select_best_method(lat1, lon1, lat2, lon2)

            # Calculate distance
            if method == "haversine":
                distance_km = DistanceCalculationHandler._haversine_distance(lat1, lon1, lat2, lon2)
                accuracy = "medium"  # ~0.5% error
            elif method == "vincenty":
                distance_km = DistanceCalculationHandler._vincenty_distance(lat1, lon1, lat2, lon2)
                accuracy = "high"  # ~0.05% error
            elif method == "geodesic":
                distance_km = DistanceCalculationHandler._geodesic_distance(lat1, lon1, lat2, lon2)
                accuracy = "highest"  # ~0.001% error
            else:
                raise ValueError(f"Unknown distance method: {method}")

            # Validate result
            if distance_km < 0 or distance_km > 20037.5:  # Half Earth's circumference
                raise ValueError(f"Calculated distance {distance_km} is unrealistic")

            return {
                "distance_km": round(distance_km, 3),
                "method": method,
                "accuracy": accuracy,
                "valid": True,
                "warnings": [],
            }

        except Exception as e:
            logger.error(f"Distance calculation failed: {e}")
            return {
                "distance_km": None,
                "method": method,
                "accuracy": "unknown",
                "valid": False,
                "warnings": [str(e)],
            }

    @staticmethod
    def _select_best_method(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
        """Select best distance calculation method based on coordinates."""
        # Check if near poles (lat > 85° or lat < -85°)
        if any(abs(lat) > 85 for lat in [lat1, lat2]):
            return "geodesic"  # Most accurate for polar regions

        # Check distance (rough estimate)
        rough_distance = abs(lat1 - lat2) + abs(lon1 - lon2)

        if rough_distance > 60:  # Large distances
            return "vincenty"
        else:  # Short distances
            return "haversine"

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance using Haversine formula."""
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth's radius in kilometers
        r = 6371.0
        return r * c

    @staticmethod
    def _vincenty_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance using Vincenty's formula."""
        try:
            from geopy.distance import distance

            return distance((lat1, lon1), (lat2, lon2)).kilometers
        except ImportError:
            # Fallback to Haversine if geopy not available
            logger.warning("geopy not available, falling back to Haversine")
            return DistanceCalculationHandler._haversine_distance(lat1, lon1, lat2, lon2)

    @staticmethod
    def _geodesic_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance using geodesic formula."""
        try:
            from geopy.distance import geodesic

            return geodesic((lat1, lon1), (lat2, lon2)).kilometers
        except ImportError:
            # Fallback to Vincenty
            return DistanceCalculationHandler._vincenty_distance(lat1, lon1, lat2, lon2)


class GeographicDataIntegrityManager:
    """
    Manage data integrity for geographic information.
    """

    @staticmethod
    def validate_producer_location_integrity(producer):
        """Validate producer location data integrity."""
        issues = []

        try:
            if not producer.location:
                issues.append("Producer has no location set")
                return issues

            lat, lon = producer.location.y, producer.location.x

            # Validate coordinates
            validation = GeographicEdgeCaseHandler.validate_coordinates_comprehensive(lat, lon)
            if not validation["valid"]:
                issues.extend(validation["warnings"])

            # Check if location matches producer's address region
            if hasattr(producer, "address") and producer.address:
                # Simple check for Nepal-based addresses
                nepal_keywords = ["nepal", "kathmandu", "pokhara", "chitwan"]
                address_lower = producer.address.lower()
                has_nepal_keyword = any(keyword in address_lower for keyword in nepal_keywords)

                nepal_region = GeographicEdgeCaseHandler.REGIONS[GeographicRegion.NEPAL]
                is_in_nepal = nepal_region.contains(lat, lon)

                if has_nepal_keyword and not is_in_nepal:
                    issues.append("Producer address suggests Nepal but coordinates are outside Nepal")
                elif not has_nepal_keyword and is_in_nepal:
                    issues.append("Coordinates in Nepal but address doesn't mention Nepal")

            # Check service radius reasonableness
            if hasattr(producer, "service_radius_km") and producer.service_radius_km:
                if producer.service_radius_km > 500:
                    issues.append(f"Service radius {producer.service_radius_km}km seems unrealistic")

        except Exception as e:
            issues.append(f"Error validating producer location: {str(e)}")

        return issues

    @staticmethod
    def validate_city_location_integrity(city):
        """Validate city location data integrity."""
        issues = []

        try:
            if not city.location:
                issues.append("City has no location coordinates")
                return issues

            lat, lon = city.location.y, city.location.x

            # Validate coordinates
            validation = GeographicEdgeCaseHandler.validate_coordinates_comprehensive(lat, lon)
            if not validation["valid"]:
                issues.extend(validation["warnings"])

            # Check if coordinates match city name (Nepal context)
            city_name_lower = city.name.lower()

            for known_city, bounds in GeographicEdgeCaseHandler.NEPAL_CITIES.items():
                if known_city in city_name_lower:
                    if not bounds.contains(lat, lon):
                        issues.append(f"City name '{city.name}' suggests {known_city} but coordinates don't match")
                    break

        except Exception as e:
            issues.append(f"Error validating city location: {str(e)}")

        return issues

    @staticmethod
    def repair_coordinate_data(model_instance, field_name: str = "location") -> bool:
        """
        Attempt to repair coordinate data using various strategies.

        Returns:
            True if repair was successful, False otherwise
        """
        try:
            location_field = getattr(model_instance, field_name)
            if not location_field:
                return False

            lat, lon = location_field.y, location_field.x

            # Get validation results
            validation = GeographicEdgeCaseHandler.validate_coordinates_comprehensive(lat, lon)

            if validation["corrected_coordinates"]:
                # Apply correction
                corrected_lat, corrected_lon = validation["corrected_coordinates"]

                with transaction.atomic():
                    corrected_point = Point(corrected_lon, corrected_lat, srid=4326)
                    setattr(model_instance, field_name, corrected_point)
                    model_instance.save(update_fields=[field_name])

                logger.info(
                    f"Corrected coordinates for {model_instance}: " f"({lat}, {lon}) -> ({corrected_lat}, {corrected_lon})"
                )
                return True

        except Exception as e:
            logger.error(f"Error repairing coordinate data: {e}")

        return False

    @staticmethod
    def audit_all_location_data() -> Dict:
        """
        Audit all location data in the system for integrity issues.

        Returns:
            Comprehensive audit report
        """
        from geo.models import City
        from producer.models import Producer

        audit_report = {
            "producers": {"total": 0, "issues": 0, "details": []},
            "cities": {"total": 0, "issues": 0, "details": []},
            "summary": {},
        }

        try:
            # Audit producers
            for producer in Producer.objects.filter(location__isnull=False):
                audit_report["producers"]["total"] += 1

                issues = GeographicDataIntegrityManager.validate_producer_location_integrity(producer)
                if issues:
                    audit_report["producers"]["issues"] += 1
                    audit_report["producers"]["details"].append(
                        {
                            "id": producer.id,
                            "name": producer.name,
                            "issues": issues,
                        }
                    )

            # Audit cities
            for city in City.objects.filter(location__isnull=False):
                audit_report["cities"]["total"] += 1

                issues = GeographicDataIntegrityManager.validate_city_location_integrity(city)
                if issues:
                    audit_report["cities"]["issues"] += 1
                    audit_report["cities"]["details"].append(
                        {
                            "id": city.id,
                            "name": city.name,
                            "issues": issues,
                        }
                    )

            # Generate summary
            audit_report["summary"] = {
                "total_locations": (audit_report["producers"]["total"] + audit_report["cities"]["total"]),
                "total_issues": (audit_report["producers"]["issues"] + audit_report["cities"]["issues"]),
                "integrity_score": 1.0
                - (
                    (audit_report["producers"]["issues"] + audit_report["cities"]["issues"])
                    / max(1, audit_report["producers"]["total"] + audit_report["cities"]["total"])
                ),
            }

        except Exception as e:
            logger.error(f"Error during location data audit: {e}")
            audit_report["error"] = str(e)

        return audit_report


class CoordinateSystemConverters:
    """
    Handle coordinate system conversions and projections.
    """

    @staticmethod
    def convert_to_utm(latitude: float, longitude: float) -> Dict:
        """
        Convert WGS84 coordinates to appropriate UTM zone.

        Returns:
            Dict with UTM coordinates and zone information
        """
        try:
            # Determine UTM zone
            utm_zone = int((longitude + 180) / 6) + 1

            # Handle special cases for Norway and Svalbard
            if 56 <= latitude < 64 and 3 <= longitude < 12:
                utm_zone = 32
            elif 72 <= latitude <= 84 and longitude >= 0:
                if longitude < 9:
                    utm_zone = 31
                elif longitude < 21:
                    utm_zone = 33
                elif longitude < 33:
                    utm_zone = 35
                elif longitude < 42:
                    utm_zone = 37

            # Determine hemisphere
            hemisphere = "N" if latitude >= 0 else "S"

            try:
                from pyproj import Transformer

                # Create transformer
                src_crs = "EPSG:4326"  # WGS84
                dst_crs = f'EPSG:{32600 + utm_zone if hemisphere == "N" else 32700 + utm_zone}'

                transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
                utm_x, utm_y = transformer.transform(longitude, latitude)

                return {
                    "utm_x": utm_x,
                    "utm_y": utm_y,
                    "zone": utm_zone,
                    "hemisphere": hemisphere,
                    "epsg_code": dst_crs,
                    "success": True,
                }

            except ImportError:
                logger.warning("pyproj not available, UTM conversion unavailable")
                return {
                    "success": False,
                    "error": "pyproj library not available",
                }

        except Exception as e:
            logger.error(f"UTM conversion failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def normalize_longitude(longitude: float) -> float:
        """
        Normalize longitude to [-180, 180] range handling date line crossing.
        """
        while longitude > 180:
            longitude -= 360
        while longitude < -180:
            longitude += 360
        return longitude

    @staticmethod
    def handle_antimeridian_crossing(coordinates: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Handle antimeridian (International Date Line) crossing in coordinate sequences.
        """
        if not coordinates or len(coordinates) < 2:
            return coordinates

        normalized_coords = []

        for i, (lat, lon) in enumerate(coordinates):
            norm_lon = CoordinateSystemConverters.normalize_longitude(lon)

            # Check for antimeridian crossing
            if i > 0:
                prev_lon = normalized_coords[-1][1]
                lon_diff = abs(norm_lon - prev_lon)

                if lon_diff > 180:  # Likely crossing antimeridian
                    # Adjust longitude to maintain continuity
                    if norm_lon > prev_lon:
                        norm_lon -= 360
                    else:
                        norm_lon += 360

            normalized_coords.append((lat, norm_lon))

        return normalized_coords
