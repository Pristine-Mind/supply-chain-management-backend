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

        # Show debugging information
        self.stdout.write("=== DEBUGGING INFO ===")

        # Show all available users
        all_users = User.objects.all()[:10]
        self.stdout.write(f"Available users (first 10):")
        for user in all_users:
            self.stdout.write(f"  - {user.username}")

        # Show all available brands
        all_brands = Brand.objects.all()
        self.stdout.write(f"\nAvailable brands:")
        for brand in all_brands:
            self.stdout.write(f"  - {brand.name} (active: {brand.is_active})")

        self.stdout.write("\n=== STARTING UPDATES ===\n")

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
                # Get the user (using icontains for flexible matching)
                user = User.objects.filter(username__icontains=username).first()
                if not user:
                    # Try exact match as fallback
                    user = User.objects.filter(username=username).first()

                if not user:
                    error_msg = f"User with username containing '{username}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))

                    # Show available usernames that might match
                    similar_users = User.objects.filter(username__icontains=username.split("_")[0])[:5]
                    if similar_users:
                        self.stdout.write("  Similar usernames found:")
                        for similar_user in similar_users:
                            self.stdout.write(f"    - {similar_user.username}")
                    continue

                self.stdout.write(f"Found user: {user.username}")

                # Get the brand (using icontains for flexible matching)
                brand = Brand.objects.filter(name__icontains=brand_name).first()
                if not brand:
                    # Try exact match as fallback
                    brand = Brand.objects.filter(name=brand_name).first()

                if not brand:
                    error_msg = f"Brand with name containing '{brand_name}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))

                    # Show available brands that might match
                    available_brands = Brand.objects.filter(is_active=True)[:10]
                    if available_brands:
                        self.stdout.write("  Available brands:")
                        for available_brand in available_brands:
                            self.stdout.write(f"    - {available_brand.name}")
                    continue

                self.stdout.write(f"Found brand: {brand.name}")

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
