from django.apps import AppConfig


class ProducerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "producer"

    def ready(self):
        import producer.admin  # Import admin to register models
        import producer.receivers  # Import receivers to register signals
