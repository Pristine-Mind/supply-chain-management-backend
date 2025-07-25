from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from transport.models import DeliveryTracking


class Command(BaseCommand):
    help = "Clean up old delivery tracking records"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90, help="Delete tracking records older than this many days")

    def handle(self, *args, **options):
        days = options["days"]
        cutoff_date = timezone.now() - timedelta(days=days)

        old_tracking = DeliveryTracking.objects.filter(timestamp__lt=cutoff_date)

        count = old_tracking.count()
        old_tracking.delete()

        self.stdout.write(self.style.SUCCESS(f"Successfully deleted {count} old tracking records"))
