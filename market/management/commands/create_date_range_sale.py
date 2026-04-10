"""
Management command to create a specific date range New Year Sale.

Usage:
    python manage.py create_date_range_sale \
        --name "April Sale 2026" \
        --start "2026-04-09" \
        --end "2026-04-19" \
        --discount 35
    
    # With all products
    python manage.py create_date_range_sale \
        --name "April Sale" \
        --start "2026-04-09" \
        --end "2026-04-19" \
        --discount 35 \
        --all-products
    
    # With specific brands (comma-separated IDs or names)
    python manage.py create_date_range_sale \
        --name "Nike & Adidas April Sale" \
        --start "2026-04-09" \
        --end "2026-04-19" \
        --discount 40 \
        --brands "Nike,Adidas"
    
    # With brand-specific discounts (separate sales per brand)
    python manage.py create_date_range_sale \
        --name "Spring Season Sale" \
        --start "2026-04-09" \
        --end "2026-04-19" \
        --brand-discounts
"""

from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from market.models import NewYearSale
from producer.models import Brand, MarketplaceProduct

BRAND_DISCOUNT_MAP = {
    34: 10
}


def _validate_brand_discount_map():
    """Validate that all discount percentages are in valid range (0-100)."""
    for brand_id, discount in BRAND_DISCOUNT_MAP.items():
        if not isinstance(discount, (int, float)) or discount < 0 or discount > 100:
            raise ValueError(f"Invalid discount {discount}% for Brand {brand_id}. " f"Discount must be between 0 and 100.")


# Validate on import
try:
    _validate_brand_discount_map()
except ValueError as e:
    raise CommandError(str(e))


class Command(BaseCommand):
    help = "Create a New Year Sale for a specific date range with optional brand-specific discounts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            type=str,
            required=True,
            help="Name of the sale",
        )
        parser.add_argument(
            "--start",
            type=str,
            required=True,
            help="Start date in format YYYY-MM-DD (e.g., 2026-04-09)",
        )
        parser.add_argument(
            "--end",
            type=str,
            required=True,
            help="End date in format YYYY-MM-DD (e.g., 2026-04-19)",
        )
        parser.add_argument(
            "--discount",
            type=float,
            default=30,
            help="Discount percentage (default: 30)",
        )
        parser.add_argument(
            "--description",
            type=str,
            default="",
            help="Sale description",
        )
        parser.add_argument(
            "--all-products",
            action="store_true",
            help="Add all available products to the sale",
        )
        parser.add_argument(
            "--brands",
            type=str,
            default="",
            help="Comma-separated brand IDs or names (e.g., 'Nike,Adidas' or '1,2,3')",
        )
        parser.add_argument(
            "--brand-discounts",
            action="store_true",
            help="Create separate sales for each brand with their specific discount percentages",
        )

    def handle(self, *args, **options):
        # Validate brand-discounts flag usage
        if options["brand_discounts"]:
            if options["brands"]:
                raise CommandError(
                    "Cannot use both --brand-discounts and --brands. "
                    "--brand-discounts creates sales for all brands in BRAND_DISCOUNT_MAP."
                )
            if options["all_products"]:
                raise CommandError(
                    "Cannot use --all-products with --brand-discounts. "
                    "Brand-specific sales automatically use products from their respective brand."
                )

        try:
            # Parse dates
            start_date = datetime.strptime(options["start"], "%Y-%m-%d")
            end_date = datetime.strptime(options["end"], "%Y-%m-%d")

            # Make aware (add timezone info) with complete precision
            start_date = timezone.make_aware(start_date)
            end_date = timezone.make_aware(end_date.replace(hour=23, minute=59, second=59, microsecond=999999))

        except ValueError as e:
            raise CommandError(f"Invalid date format. Use YYYY-MM-DD format. Error: {e}")

        # Validate dates
        if start_date >= end_date:
            raise CommandError("End date must be after start date")

        # Get any user (fallback to first user if exists)
        creator_user = User.objects.first()
        if not creator_user:
            self.stdout.write(self.style.WARNING("⚠️  No users found. Sales will be created without creator."))
            creator_user = None

        # Handle brand-specific discounts
        if options["brand_discounts"]:
            return self._create_brand_specific_sales(options, creator_user, start_date, end_date)

        # Standard single sale creation
        return self._create_single_sale(options, creator_user, start_date, end_date)

    def _create_brand_specific_sales(self, options, creator_user, start_date, end_date):
        """Create separate sales for each brand with their specific discount percentage."""
        self.stdout.write(
            self.style.SUCCESS(f"\n📊 Creating brand-specific sales for {start_date.date()} to {end_date.date()}")
        )
        self.stdout.write(f"Found {len(BRAND_DISCOUNT_MAP)} brands with custom discounts\n")

        total_products = 0
        sales_created = 0
        brands_not_found = []
        brands_no_products = []

        with transaction.atomic():
            for brand_id, discount_percentage in sorted(BRAND_DISCOUNT_MAP.items()):
                try:
                    brand = Brand.objects.get(id=brand_id)
                except Brand.DoesNotExist:
                    brands_not_found.append(brand_id)
                    self.stdout.write(self.style.WARNING(f"⚠️  Brand ID {brand_id} not found"))
                    continue

                # Get products for this brand
                brand_products = MarketplaceProduct.objects.filter(product__brand=brand, is_available=True).distinct()

                if not brand_products.exists():
                    brands_no_products.append(brand.name)
                    self.stdout.write(self.style.WARNING(f"⚠️  Brand '{brand.name}' has no available products"))
                    continue

                # Check for duplicate sale name
                sale_name = f"{options['name']} - {brand.name}"
                if NewYearSale.objects.filter(name=sale_name).exists():
                    self.stdout.write(
                        self.style.WARNING(f"⚠️  Sale '{sale_name}' already exists, skipping to avoid duplicates")
                    )
                    continue

                # Create sale for this brand
                sale = NewYearSale.objects.create(
                    name=sale_name,
                    description=options["description"]
                    or f"{brand.name} exclusive: {discount_percentage}% off from {options['start']} to {options['end']}",
                    discount_percentage=Decimal(str(discount_percentage)),
                    start_date=start_date,
                    end_date=end_date,
                    is_active=True,
                    created_by=creator_user,
                )

                # Add products to sale
                sale.products.add(*brand_products)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {brand.name:20} | Discount: {discount_percentage}% | Products: {brand_products.count()}"
                    )
                )

                total_products += brand_products.count()
                sales_created += 1

        # Summary
        self.stdout.write("\n" + "=" * 70)
        if sales_created == 0:
            self.stdout.write(self.style.WARNING("⚠️  No sales were created."))
        else:
            self.stdout.write(self.style.SUCCESS(f"✓ Created {sales_created} brand-specific sales"))
        self.stdout.write(f"  Total products added: {total_products}")
        if brands_not_found:
            self.stdout.write(self.style.WARNING(f"  Brands not found: {', '.join(map(str, brands_not_found))}"))
        if brands_no_products:
            self.stdout.write(self.style.WARNING(f"  Brands skipped (no products): {', '.join(brands_no_products)}"))
        self.stdout.write("=" * 70)

    def _create_single_sale(self, options, creator_user, start_date, end_date):
        """Create a single sale with optional product selection."""
        # Validate discount
        try:
            discount = Decimal(str(options["discount"]))
        except (ValueError, TypeError):
            raise CommandError(f"Invalid discount value: {options['discount']}")

        if discount < 0 or discount > 100:
            raise CommandError("Discount must be between 0 and 100")

        # Check for duplicate sale name
        if NewYearSale.objects.filter(name=options["name"]).exists():
            raise CommandError(
                f"A sale with name '{options['name']}' already exists. Use a different name or delete the existing sale."
            )

        with transaction.atomic():
            # Create the sale
            sale = NewYearSale.objects.create(
                name=options["name"],
                description=options["description"] or f"Sale from {options['start']} to {options['end']}",
                discount_percentage=discount,
                start_date=start_date,
                end_date=end_date,
                is_active=True,
                created_by=creator_user,
            )

            self.stdout.write(self.style.SUCCESS(f"✓ Created sale: {sale.name}"))
            self.stdout.write(f"  Period: {start_date.date()} to {end_date.date()}")
            self.stdout.write(f"  Discount: {discount}%")

            # Track products to add
            products_to_add = MarketplaceProduct.objects.none()

            # Add products by brand if specified
            if options["brands"]:
                brand_inputs = [b.strip() for b in options["brands"].split(",") if b.strip()]

                if not brand_inputs:
                    self.stdout.write(self.style.WARNING("⚠️  --brands flag provided but no valid brand names/IDs"))
                else:
                    brands = []

                    for brand_input in brand_inputs:
                        # Try to find by ID first
                        try:
                            brand_id = int(brand_input)
                            brand = Brand.objects.get(id=brand_id)
                            if brand not in brands:
                                brands.append(brand)
                                self.stdout.write(f"  ✓ Found brand by ID: {brand.name}")
                        except (ValueError, Brand.DoesNotExist):
                            # Try to find by name (case-insensitive)
                            brand = Brand.objects.filter(name__iexact=brand_input).first()
                            if brand and brand not in brands:
                                brands.append(brand)
                                self.stdout.write(f"  ✓ Found brand by name: {brand.name}")
                            else:
                                self.stdout.write(self.style.WARNING(f"  ⚠️  Brand not found: {brand_input}"))

                    if brands:
                        # Get products for these brands
                        brand_products = MarketplaceProduct.objects.filter(
                            product__brand__in=brands, is_available=True
                        ).distinct()
                        products_to_add = products_to_add | brand_products
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Found {brand_products.count()} products from {len(brands)} brand(s)")
                        )

            # Add all available products if requested
            if options["all_products"]:
                all_products = MarketplaceProduct.objects.filter(is_available=True)
                products_to_add = products_to_add | all_products
                self.stdout.write(self.style.SUCCESS(f"✓ Added all {all_products.count()} available products to selection"))

            # Add products to sale (explicit deduplication)
            if products_to_add.exists():
                product_list = list(products_to_add.distinct())
                sale.products.add(*product_list)
                self.stdout.write(self.style.SUCCESS(f"✓ Added {len(product_list)} total unique products to the sale"))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "No products added. Use --all-products and/or --brands to add products, "
                        "or add them manually via admin or API."
                    )
                )

        self.stdout.write(self.style.SUCCESS("\n✓ Sale created successfully!"))
