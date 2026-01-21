# geo/__init__.py
"""
Geographic location-based product sales restriction system.

Features:
- Geo-spatial product delivery restrictions
- Zone-based sales management
- User location tracking
- Delivery estimate calculations
- Integration with market product filtering

Services:
- GeoLocationService: Core location operations
- GeoProductFilterService: Product filtering by location
- GeoAnalyticsService: Analytics and statistics
"""

default_app_config = "geo.apps.GeoConfig"
