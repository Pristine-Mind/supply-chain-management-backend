"""
Batch population script for NewYearSale model.
This script provides different strategies to populate New Year sales with existing marketplace products.

Usage:
    python manage.py shell < market/fixtures/bulk_populate_sales.py
    
    Or inside Django shell:
    >>> exec(open("market/fixtures/bulk_populate_sales.py").read())
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from market.models import NewYearSale
from producer.models import MarketplaceProduct


def get_or_create_admin():
    """Get admin user or raise error if none exists"""
    admin_user = User.objects.filter(is_staff=True).first()
    if not admin_user:
        raise Exception("No admin user found. Please create a superuser first.")
    return admin_user


def populate_strategy_1_simple_sale():
    """
    Strategy 1: Create a simple New Year sale with all available products
    Best for: Quick setup with basic sales structure
    """
    print("\n=== Strategy 1: Simple Sale Structure ===")

    admin_user = get_or_create_admin()

    with transaction.atomic():
        # Get all available products
        products = MarketplaceProduct.objects.filter(is_available=True)

        if not products.exists():
            print("⚠️  No available products found!")
            return

        # Create single sale
        sale = NewYearSale.objects.create(
            name="New Year Sale 2026",
            description="Amazing New Year discounts on all products",
            discount_percentage=Decimal("30"),
            start_date=timezone.make_aware(datetime(2026, 1, 1, 0, 0, 0)),
            end_date=timezone.make_aware(datetime(2026, 1, 31, 23, 59, 59)),
            is_active=True,
            created_by=admin_user,
        )

        # Add all products at once
        sale.products.set(products)

        print(f"✓ Created sale: {sale.name}")
        print(f"✓ Added {sale.products.count()} products")


def populate_strategy_2_tiered_discounts():
    """
    Strategy 2: Create multiple sales with different discount levels
    Best for: Tiered pricing strategy with multiple discount options
    """
    print("\n=== Strategy 2: Tiered Discount Structure ===")

    admin_user = get_or_create_admin()
    products = list(MarketplaceProduct.objects.filter(is_available=True))

    if not products:
        print("⚠️  No available products found!")
        return

    with transaction.atomic():
        # Divide products into tiers
        tier_size = len(products) // 3

        tiers = [
            ("Budget-Friendly New Year Sale", Decimal("15"), products[:tier_size]),
            ("Mid-Range New Year Sale", Decimal("30"), products[tier_size : 2 * tier_size]),
            ("Premium New Year Sale", Decimal("50"), products[2 * tier_size :]),
        ]

        for name, discount, tier_products in tiers:
            sale = NewYearSale.objects.create(
                name=name,
                description=f"New Year sale with {discount}% discount",
                discount_percentage=discount,
                start_date=timezone.make_aware(datetime(2026, 1, 1, 0, 0, 0)),
                end_date=timezone.make_aware(datetime(2026, 1, 31, 23, 59, 59)),
                is_active=True,
                created_by=admin_user,
            )

            if tier_products:
                sale.products.set(tier_products)
                print(f"✓ Created {sale.name} with {sale.products.count()} products")


def populate_strategy_3_time_based_sales():
    """
    Strategy 3: Create time-based flash sales
    Best for: Sequential sales events throughout the month
    """
    print("\n=== Strategy 3: Time-Based Flash Sales ===")

    admin_user = get_or_create_admin()
    products = list(MarketplaceProduct.objects.filter(is_available=True))

    if not products:
        print("⚠️  No available products found!")
        return

    with transaction.atomic():
        # Create 4 weekly sales
        for week in range(1, 5):
            start_day = 1 + (week - 1) * 7
            end_day = min(start_day + 6, 31)

            sale = NewYearSale.objects.create(
                name=f"Week {week} New Year Flash Sale",
                description=f"Special deals during week {week} of January",
                discount_percentage=Decimal(20 + week * 5),  # 25%, 30%, 35%, 40%
                start_date=timezone.make_aware(datetime(2026, 1, start_day, 0, 0, 0)),
                end_date=timezone.make_aware(datetime(2026, 1, end_day, 23, 59, 59)),
                is_active=True,
                created_by=admin_user,
            )

            # Add rotating products for each week
            week_products = products[(week - 1) * 10 : (week) * 10]
            if week_products:
                sale.products.set(week_products)
                print(f"✓ Created {sale.name} ({sale.discount_percentage}% off) - Days {start_day}-{end_day}")


def populate_strategy_4_category_based():
    """
    Strategy 4: Create category-based sales
    Best for: Product category-specific promotions
    """
    print("\n=== Strategy 4: Category-Based Sales ===")

    admin_user = get_or_create_admin()
    products = MarketplaceProduct.objects.filter(is_available=True)

    if not products.exists():
        print("⚠️  No available products found!")
        return

    with transaction.atomic():
        # Define categories with discounts
        categories = {
            "Electronics & Gadgets": Decimal("25"),
            "Fashion & Apparel": Decimal("35"),
            "Home & Living": Decimal("40"),
            "Health & Beauty": Decimal("30"),
            "Groceries & Essentials": Decimal("15"),
        }

        for category, discount in categories.items():
            sale = NewYearSale.objects.create(
                name=f"{category} - New Year Sale",
                description=f"Special New Year offers on {category.lower()}",
                discount_percentage=discount,
                start_date=timezone.make_aware(datetime(2026, 1, 5, 0, 0, 0)),
                end_date=timezone.make_aware(datetime(2026, 1, 25, 23, 59, 59)),
                is_active=True,
                created_by=admin_user,
            )

            # Add subset of products
            category_products = products[:15]
            if category_products.exists():
                sale.products.set(category_products)
                print(f"✓ Created {category} sale ({discount}% off)")


def populate_strategy_5_premium_flash_sales():
    """
    Strategy 5: Create premium/VIP flash sales
    Best for: High-value customer targeting with limited availability
    """
    print("\n=== Strategy 5: Premium Flash Sales ===")

    admin_user = get_or_create_admin()

    # Get top products by view count
    top_products = MarketplaceProduct.objects.filter(is_available=True).order_by("-view_count")[:20]

    if not top_products.exists():
        print("⚠️  No available products found!")
        return

    with transaction.atomic():
        flash_sales = [
            ("48-Hour New Year Mega Flash Sale", 1, 2, Decimal("60")),
            ("Weekend Warrior Flash Sale", 8, 9, Decimal("55")),
            ("Mid-Month Blitz Flash Sale", 15, 16, Decimal("50")),
            ("Last Chance Flash Sale", 28, 29, Decimal("65")),
        ]

        for name, start_day, end_day, discount in flash_sales:
            sale = NewYearSale.objects.create(
                name=name,
                description=f"⚡ LIMITED TIME! {discount}% off on select premium items",
                discount_percentage=discount,
                start_date=timezone.make_aware(datetime(2026, 1, start_day, 0, 0, 0)),
                end_date=timezone.make_aware(datetime(2026, 1, end_day, 23, 59, 59)),
                is_active=True,
                created_by=admin_user,
            )

            sale.products.set(top_products)
            print(f"✓ Created {name} ({discount}% off) - Jan {start_day}-{end_day}")


def populate_strategy_6_bulk_import():
    """
    Strategy 6: Bulk import with transaction handling
    Best for: Large-scale operations with error handling
    """
    print("\n=== Strategy 6: Bulk Import with Error Handling ===")

    admin_user = get_or_create_admin()
    products = list(MarketplaceProduct.objects.filter(is_available=True))

    if not products:
        print("⚠️  No available products found!")
        return

    sales_data = [
        {
            "name": "New Year 2026 Grand Opening Sale",
            "description": "Welcome 2026 with our biggest sale ever!",
            "discount": Decimal("35"),
            "start": (1, 1),
            "end": (1, 31),
            "product_slice": slice(None),  # All products
        },
        {
            "name": "Clearance Extravaganza",
            "description": "Clear out old inventory",
            "discount": Decimal("50"),
            "start": (1, 10),
            "end": (1, 20),
            "product_slice": slice(0, 10),
        },
    ]

    try:
        with transaction.atomic():
            for data in sales_data:
                sale = NewYearSale.objects.create(
                    name=data["name"],
                    description=data["description"],
                    discount_percentage=data["discount"],
                    start_date=timezone.make_aware(datetime(2026, data["start"][0], data["start"][1], 0, 0, 0)),
                    end_date=timezone.make_aware(datetime(2026, data["end"][0], data["end"][1], 23, 59, 59)),
                    is_active=True,
                    created_by=admin_user,
                )

                sale_products = products[data["product_slice"]]
                if sale_products:
                    sale.products.set(sale_products)
                    print(f"✓ Created {sale.name} with {len(sale_products)} products")

        print("\n✓ Bulk import completed successfully")
    except Exception as e:
        print(f"\n✗ Bulk import failed: {str(e)}")


def cleanup_sales():
    """Delete all New Year sales created for testing"""
    print("\n=== Cleanup ===")
    count = NewYearSale.objects.all().count()
    NewYearSale.objects.all().delete()
    print(f"✓ Deleted {count} New Year sales")


def show_summary():
    """Display summary of all created sales"""
    print("\n=== Summary ===")
    sales = NewYearSale.objects.all()

    if not sales.exists():
        print("No New Year sales found")
        return

    total_products = 0
    print(f"\nTotal Sales: {sales.count()}")
    print("-" * 80)
    for sale in sales:
        product_count = sale.products.count()
        total_products += product_count
        print(f"{sale.name}")
        print(f"  Discount: {sale.discount_percentage}% | Period: {sale.start_date.date()} to {sale.end_date.date()}")
        print(f"  Products: {product_count} | Status: {sale.sale_status}")

    print("-" * 80)
    print(f"Total Products (with duplicates): {total_products}")


# Main execution
if __name__ == "__main__":
    print("=" * 80)
    print("NEW YEAR SALE POPULATION SCRIPT")
    print("=" * 80)

    # Choose which strategy to run
    # Uncomment the strategy you want to use

    # Option 1: Run a single strategy
    # populate_strategy_1_simple_sale()

    # Option 2: Run multiple strategies (recommended)
    populate_strategy_1_simple_sale()
    populate_strategy_2_tiered_discounts()
    populate_strategy_3_time_based_sales()
    populate_strategy_4_category_based()
    populate_strategy_5_premium_flash_sales()

    # Option 3: Show summary
    show_summary()

    print("\n" + "=" * 80)
    print("Population complete!")
    print("=" * 80)
