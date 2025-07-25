from django.core.management.base import BaseCommand

from transport.models import Transporter


class Command(BaseCommand):
    help = "Update all transporter ratings based on their delivery ratings"

    def handle(self, *args, **options):
        updated_count = 0

        for transporter in Transporter.objects.all():
            old_rating = transporter.rating
            transporter.update_rating()

            if transporter.rating != old_rating:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully updated ratings for {updated_count} transporters"))
