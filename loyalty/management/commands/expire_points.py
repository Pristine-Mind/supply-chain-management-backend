from django.core.management.base import BaseCommand

from loyalty.services import LoyaltyService


class Command(BaseCommand):
    help = "Expire old loyalty points based on configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            help="Number of days after which points expire (overrides config)",
        )

    def handle(self, *args, **options):
        days = options.get("days")

        self.stdout.write("Starting points expiration...")

        users_affected = LoyaltyService.expire_old_points(days)

        self.stdout.write(self.style.SUCCESS(f"Successfully expired points for {users_affected} users"))
