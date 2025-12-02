from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from producer.models import Brand, Product


class Command(BaseCommand):
    help = "Update products with brand associations based on username patterns"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Define username to brand mappings
        username_brand_mappings = {
            "himstar_nepal": "Himstar",
            "asus_nagmani": "Asus",
            "hitech_nepal": "Hi-tech",
        }

        updated_count = 0
        errors = []

        for username, brand_name in username_brand_mappings.items():
            try:
                # Get the user
                try:
                    user = User.objects.get(username=username)
                    self.stdout.write(f"Found user: {username}")
                except User.DoesNotExist:
                    error_msg = f"User '{username}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
                    continue

                # Get the brand
                try:
                    brand = Brand.objects.get(name=brand_name)
                    self.stdout.write(f"Found brand: {brand_name}")
                except Brand.DoesNotExist:
                    error_msg = f"Brand '{brand_name}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
                    continue

                # Get products for this user
                products = Product.objects.filter(user=user)
                product_count = products.count()

                if product_count == 0:
                    self.stdout.write(f"No products found for user '{username}'")
                    continue

                self.stdout.write(f"Found {product_count} products for user '{username}'")

                # Show products that would be updated
                if dry_run:
                    self.stdout.write(f"DRY RUN - Would update {product_count} products:")
                    for product in products[:5]:  # Show first 5 products
                        current_brand = product.brand.name if product.brand else "No brand"
                        self.stdout.write(f"  - '{product.name}' (current brand: {current_brand}) -> {brand_name}")
                    if product_count > 5:
                        self.stdout.write(f"  ... and {product_count - 5} more products")
                else:
                    # Actually update the products
                    updated = products.update(brand=brand)
                    updated_count += updated
                    self.stdout.write(
                        self.style.SUCCESS(f"Updated {updated} products for user '{username}' to brand '{brand_name}'")
                    )

                    # Show some examples of updated products
                    example_products = products[:3]
                    for product in example_products:
                        self.stdout.write(f"  - Updated: '{product.name}' -> Brand: {product.brand.name}")

            except Exception as e:
                error_msg = f"Error processing user '{username}': {str(e)}"
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
