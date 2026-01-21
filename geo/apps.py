# geo/apps.py
"""
Django app configuration for geographic location features.
"""

from django.apps import AppConfig


class GeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "geo"
    verbose_name = "Geographic Location Management"

    def ready(self):
        """Initialize app signals"""
        import geo.signals  # noqa
