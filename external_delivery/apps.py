from django.apps import AppConfig


class ExternalDeliveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "external_delivery"
    verbose_name = "External Delivery Integration"

    def ready(self):
        import external_delivery.signals
