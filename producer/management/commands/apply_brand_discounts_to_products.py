"""
Management command to apply brand-specific discounts from BRAND_DISCOUNT_MAP to marketplace products.

This applies the same discount percentages used in NewYearSale to MarketplaceProduct records.

Usage:
    python manage.py apply_brand_discounts_to_products
    python manage.py apply_brand_discounts_to_products --dry-run
    python manage.py apply_brand_discounts_to_products --reset (reset all discounts to 0 first)
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from producer.models import Brand, MarketplaceProduct

# Brand discount mapping (same as in create_date_range_sale.py)
BRAND_DISCOUNT_MAP = {
    32: 17,
    33: 17,
}


class Command(BaseCommand):
    help = "Apply brand-specific discount percentages to marketplace products"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying them",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all marketplace product discounts to 0 before applying new ones",
        )
        parser.add_argument(
            "--brand-id",
            type=int,
            default=None,
            help="Apply discount to products from a specific brand (by ID)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        reset = options.get("reset", False)
        brand_id = options.get("brand_id")

        self.stdout.write(self.style.SUCCESS(f"\n📊 Applying brand-specific discounts to marketplace products"))

        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No changes will be applied"))

        if reset:
            self.stdout.write(self.style.WARNING("⚠️  First resetting all marketplace product discounts to 0"))

        # Reset discounts if requested
        if reset and not dry_run:
            with transaction.atomic():
                reset_count = MarketplaceProduct.objects.filter(discount_percentage__gt=0).update(discount_percentage=0)
                self.stdout.write(self.style.SUCCESS(f"✓ Reset {reset_count} products to 0% discount"))
        elif reset and dry_run:
            reset_count = MarketplaceProduct.objects.filter(discount_percentage__gt=0).count()
            self.stdout.write(f"[DRY RUN] Would reset {reset_count} products to 0% discount")

        total_updated = 0
        total_by_discount = {}
        brands_not_found = []
        brands_no_products = []

        with transaction.atomic():
            for brand_id_map, discount_percentage in sorted(BRAND_DISCOUNT_MAP.items()):
                # Skip if filtering by specific brand
                if brand_id and brand_id_map != brand_id:
                    continue

                try:
                    brand = Brand.objects.get(id=brand_id_map)
                except Brand.DoesNotExist:
                    brands_not_found.append(brand_id_map)
                    self.stdout.write(self.style.WARNING(f"⚠️  Brand ID {brand_id_map} not found"))
                    continue

                # Get products for this brand
                products_queryset = MarketplaceProduct.objects.filter(product__brand=brand)

                if not products_queryset.exists():
                    brands_no_products.append(brand.name)
                    self.stdout.write(self.style.WARNING(f"⚠️  Brand '{brand.name}' has no marketplace products"))
                    continue

                # Apply discount
                if not dry_run:
                    updated_count = products_queryset.update(discount_percentage=Decimal(str(discount_percentage)))
                else:
                    updated_count = products_queryset.count()

                total_updated += updated_count
                total_by_discount[discount_percentage] = total_by_discount.get(discount_percentage, 0) + updated_count

                prefix = "[DRY RUN] Would update" if dry_run else "✓ Updated"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{prefix} {updated_count:4} products | Brand: {brand.name:20} | Discount: {discount_percentage}%"
                    )
                )

        # Summary
        self.stdout.write("\n" + "=" * 80)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"🔍 [DRY RUN] Would update {total_updated} products total"))
        else:
            self.stdout.write(self.style.SUCCESS(f"✓ Updated {total_updated} products total with brand-specific discounts"))

        # Discount breakdown
        self.stdout.write("\n📊 Products by discount percentage:")
        for discount, count in sorted(total_by_discount.items()):
            self.stdout.write(f"  {discount}% discount: {count} products")

        if brands_not_found:
            self.stdout.write(self.style.WARNING(f"\n⚠️  Brands not found: {', '.join(map(str, brands_not_found))}"))

        if brands_no_products:
            self.stdout.write(
                self.style.WARNING(f"\n⚠️  Brands with no marketplace products: {', '.join(brands_no_products)}")
            )

        self.stdout.write("=" * 80)

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\n✓ Dry run complete. Run without --dry-run to apply changes."))
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ Discounts applied successfully!"))
