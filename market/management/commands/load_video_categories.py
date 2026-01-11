from django.core.management.base import BaseCommand
from market.models import ShoppableVideoCategory


class Command(BaseCommand):
    help = "Loads default shoppable video categories into the database"

    def handle(self, *args, **options):
        # Default categories list: (Name, Order)
        default_categories = [
            ("Fashion & Style", 1),
            ("Electronics & Gadgets", 2),
            ("Home Decor", 3),
            ("Health & Beauty", 4),
            ("Groceries", 5),
            ("Lifestyle", 6),
            ("Made in Nepal", 7),
            ("New Arrivals", 8),
            ("Best Sellers", 9),
            ("Gifts", 10),
        ]

        self.stdout.write("Starting to load shoppable video categories...")

        created_count = 0
        updated_count = 0

        for name, order in default_categories:
            category, created = ShoppableVideoCategory.objects.update_or_create(
                name=name, defaults={"order": order, "is_active": True}
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed categories: {created_count} created, {updated_count} updated.")
        )
