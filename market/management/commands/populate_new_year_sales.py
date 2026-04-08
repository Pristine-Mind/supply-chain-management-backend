"""
Management command to populate NewYearSale with sample data from existing marketplace products.

Usage:
    python manage.py populate_new_year_sales
    python manage.py populate_new_year_sales --discount 25 --days 10
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from market.models import NewYearSale
from producer.models import MarketplaceProduct


class Command(BaseCommand):
    help = "Populate NewYearSale with sample data from existing marketplace products"

    def add_arguments(self, parser):
        parser.add_argument(
            "--discount",
            type=float,
            default=30,
            help="Default discount percentage (default: 30)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days for the sale to run (default: 30)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2026,
            help="Year for the new year sale (default: 2026)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing sales before populating",
        )

    def handle(self, *args, **options):
        discount = Decimal(str(options["discount"]))
        days = options["days"]
        year = options["year"]
        clear_existing = options["clear"]

        # Validate discount
        if discount < 0 or discount > 100:
            self.stdout.write(self.style.ERROR("Discount must be between 0 and 100"))
            return

        # Clear existing sales if requested
        if clear_existing:
            count = NewYearSale.objects.all().count()
            NewYearSale.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} existing sales"))

        # Get the first admin user or create context user
        admin_user = User.objects.filter(is_staff=True).first()
        if not admin_user:
            admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR("No admin user found. Please create a superuser first."))
            return

        # Create main New Year sale
        start_date = timezone.make_aware(datetime(year, 1, 1, 0, 0, 0))
        end_date = start_date + timedelta(days=days)

        new_year_sale = NewYearSale.objects.create(
            name=f"New Year Sale {year}",
            description=f"Welcome the new year with amazing discounts! Get up to {discount}% off on selected products. "
            f"This sale runs from January 1st to January {days}th, {year}.",
            discount_percentage=discount,
            start_date=start_date,
            end_date=end_date,
            is_active=True,
            created_by=admin_user,
        )
        self.stdout.write(self.style.SUCCESS(f"✓ Created main sale: {new_year_sale.name}"))

        # Get marketplace products and add them to the sale
        products = MarketplaceProduct.objects.filter(is_available=True).select_related("product")

        if not products.exists():
            self.stdout.write(self.style.WARNING("No available marketplace products found to add to sale"))
            return

        # Add products to the sale
        new_year_sale.products.add(*products)
        self.stdout.write(self.style.SUCCESS(f"✓ Added {products.count()} available products to the New Year sale"))

        # Create category-specific sales
        categories = ["Electronics", "Fashion", "Home & Living"]
        category_discounts = [Decimal("25"), Decimal("30"), Decimal("35")]

        for category, cat_discount in zip(categories, category_discounts):
            start_date = timezone.make_aware(datetime(year, 1, 5, 0, 0, 0))
            end_date = start_date + timedelta(days=20)

            category_sale = NewYearSale.objects.create(
                name=f"{category} New Year Sale {year}",
                description=f"Special {year} offer on {category}! Enjoy {cat_discount}% discount on all {category} items. "
                f"Limited time offer!",
                discount_percentage=cat_discount,
                start_date=start_date,
                end_date=end_date,
                is_active=True,
                created_by=admin_user,
            )

            # Add some relevant products (you can customize this logic)
            category_products = products.filter(product__name__icontains=category.replace(" & ", ""))[:10]
            if category_products.count() == 0:
                # If no category match, add some random products
                category_products = products[:10]

            category_sale.products.add(*category_products)
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created {category_sale.name} with {category_products.count()} products")
            )

        # Create flash sales (shorter duration, higher discount)
        flash_sale_dates = [
            (1, 3),  # Jan 1-3
            (15, 17),  # Jan 15-17
            (25, 27),  # Jan 25-27
        ]

        for start_day, end_day in flash_sale_dates:
            start_date = timezone.make_aware(datetime(year, 1, start_day, 0, 0, 0))
            end_date = timezone.make_aware(datetime(year, 1, end_day, 23, 59, 59))

            flash_sale = NewYearSale.objects.create(
                name=f"Flash Sale {year} (Jan {start_day}-{end_day})",
                description=f"⚡ FLASH SALE! Limited slots available with 50% discount on select products. "
                f"Hurry, sale ends on January {end_day}!",
                discount_percentage=Decimal("50"),
                start_date=start_date,
                end_date=end_date,
                is_active=True,
                created_by=admin_user,
            )

            # Add select premium products
            flash_products = products[:5]
            flash_sale.products.add(*flash_products)
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created flash sale: {flash_sale.name} with {flash_products.count()} products")
            )

        # Summary
        total_sales = NewYearSale.objects.count()
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 50))
        self.stdout.write(self.style.SUCCESS(f"✓ Successfully populated {total_sales} New Year sales!"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write("\nSales Summary:")
        for sale in NewYearSale.objects.all():
            self.stdout.write(
                f"  • {sale.name}: {sale.discount_percentage}% off - "
                f"{sale.products.count()} products - Status: {sale.sale_status}"
            )
