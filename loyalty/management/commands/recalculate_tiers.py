from django.core.management.base import BaseCommand

from loyalty.models import UserLoyalty


class Command(BaseCommand):
    help = "Recalculate loyalty tiers for all users"

    def handle(self, *args, **options):
        self.stdout.write("Recalculating tiers for all users...")

        profiles = UserLoyalty.objects.filter(is_active=True).select_related("tier")

        updated = 0
        total = profiles.count()

        for profile in profiles:
            if profile.update_tier():
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully recalculated tiers. " f"Updated: {updated}/{total}"))
