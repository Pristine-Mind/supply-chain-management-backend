from django.apps import AppConfig


class MarketConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "market"

    def ready(self):
        # Import signals
        import market.receivers  # noqa: F401
        import market.signals  # noqa: F401
