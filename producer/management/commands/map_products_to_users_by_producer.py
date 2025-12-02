from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from producer.models import Producer, Product


class Command(BaseCommand):
    help = "Update products with user associations based on their producer names to username mappings"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Show debugging information
        self.stdout.write("=== DEBUGGING INFO ===")

        # Show all available users
        all_users = User.objects.all()[:15]
        self.stdout.write(f"Available users (first 15):")
        for user in all_users:
            self.stdout.write(f"  - {user.username}")

        # Show all available producers
        all_producers = Producer.objects.all()[:15]
        self.stdout.write(f"\nAvailable producers (first 15):")
        for producer in all_producers:
            self.stdout.write(f"  - {producer.name}")

        # Show products count by producer
        products_by_producer = Product.objects.select_related("producer").values("producer__name").distinct()[:10]
        self.stdout.write(f"\nProducts grouped by producer (first 10):")
        for item in products_by_producer:
            if item["producer__name"]:
                product_count = Product.objects.filter(producer__name=item["producer__name"]).count()
                self.stdout.write(f"  - {item['producer__name']}: {product_count} products")

        self.stdout.write("\n=== STARTING UPDATES ===\n")

        # Define producer name to username mappings
        producer_user_mappings = {
            "ITEAM PVT. LTD.": "iteam_nepal",
            "Himstar Nepal Pvt Ltd": "himstar_nepal",
            "Asus Nagmani Pvt Ltd": "asus_nagmani",
            "Hitech Nepal Pvt Ltd": "hitech_nepal",
            "SHYAM SPORTS AND FITNESS PVT LTD": "shyam_sports",
            "Gunina Technotronix and Research Center Pvt Ltd": "gtc_nepal",
            "Baladu Co": "baladu_co",
            "Aspire Nepal": "aspire_np",
            "Agro Unicorn": "agro_unicorn",
            "70mai Nepal": "70mai_nepal",
            "Clamp Nepal": "clamp_nepal",
            "Panipokhari Liquor Shop": "panipokhari_liquor_shop",
            "VaryGood Perfumes": "varygood_perfumes",
            "Bymo Nepal": "bymo_np",
            "Hamro Local Mart": "hamro_local_mart",
            "PeeKaboo": "peekaboo",
            "Ezee kart Nepal": "ezee_kart_nepal",
        }

        updated_count = 0
        errors = []

        for producer_name, username in producer_user_mappings.items():
            try:
                # Get the producer (using icontains for flexible matching)
                producer = Producer.objects.filter(name__icontains=producer_name).first()
                if not producer:
                    # Try exact match as fallback
                    producer = Producer.objects.filter(name=producer_name).first()

                if not producer:
                    error_msg = f"Producer with name containing '{producer_name}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
                    continue

                self.stdout.write(f"Found producer: {producer.name}")

                # Get the user (using icontains for flexible matching)
                user = User.objects.filter(username__icontains=username).first()
                if not user:
                    # Try exact match as fallback
                    user = User.objects.filter(username=username).first()

                if not user:
                    error_msg = f"User with username containing '{username}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
                    continue

                self.stdout.write(f"Found user: {user.username}")

                # Get products for this producer
                products = Product.objects.filter(producer=producer)
                product_count = products.count()

                if product_count == 0:
                    self.stdout.write(f"No products found for producer '{producer.name}'")
                    continue

                self.stdout.write(f"Found {product_count} products for producer '{producer.name}'")

                # Count products that would actually be updated (different user)
                products_to_update = products.exclude(user=user)
                update_count = products_to_update.count()

                if update_count == 0:
                    self.stdout.write(f"All {product_count} products already mapped to user '{user.username}' - skipping")
                    continue

                # Show products that would be updated
                if dry_run:
                    self.stdout.write(f"DRY RUN - Would update {update_count} products:")
                    for product in products_to_update[:5]:  # Show first 5 products
                        current_user = product.user.username if product.user else "No user"
                        self.stdout.write(f"  - '{product.name}' (current user: {current_user}) -> {user.username}")
                    if update_count > 5:
                        self.stdout.write(f"  ... and {update_count - 5} more products")
                else:
                    # Actually update the products
                    updated = products_to_update.update(user=user)
                    updated_count += updated
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated {updated} products for producer '{producer.name}' to user '{user.username}'"
                        )
                    )

                    # Show some examples of updated products
                    example_products = Product.objects.filter(producer=producer, user=user)[:3]
                    for product in example_products:
                        self.stdout.write(f"  - Updated: '{product.name}' -> User: {product.user.username}")

            except Exception as e:
                error_msg = f"Error processing producer '{producer_name}': {str(e)}"
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))

        # Summary
        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN SUMMARY ==="))
            self.stdout.write("No changes were made. Use --dry-run=False to apply changes.")
        else:
            self.stdout.write(self.style.SUCCESS(f"\n=== SUMMARY ==="))
            self.stdout.write(self.style.SUCCESS(f"Total products updated: {updated_count}"))

        if errors:
            self.stdout.write(self.style.ERROR(f"Errors encountered: {len(errors)}"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"  - {error}"))
        else:
            self.stdout.write(self.style.SUCCESS("No errors encountered"))
