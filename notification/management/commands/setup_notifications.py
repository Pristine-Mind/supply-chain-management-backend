from django.core.management.base import BaseCommand
from django.db import transaction

from notification.utils import setup_notification_system


class Command(BaseCommand):
    help = "Setup notification system with default templates and rules"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force setup even if templates/rules already exist",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Setting up notification system..."))

        try:
            with transaction.atomic():
                result = setup_notification_system()

                templates_created = len(result["templates"])
                rules_created = len(result["rules"])

                if templates_created > 0:
                    self.stdout.write(self.style.SUCCESS(f"Created {templates_created} notification templates"))
                else:
                    self.stdout.write(self.style.WARNING("No new templates created (already exist)"))

                if rules_created > 0:
                    self.stdout.write(self.style.SUCCESS(f"Created {rules_created} notification rules"))
                else:
                    self.stdout.write(self.style.WARNING("No new rules created (already exist)"))

                self.stdout.write(self.style.SUCCESS("Notification system setup completed successfully!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error setting up notification system: {e}"))
            raise
