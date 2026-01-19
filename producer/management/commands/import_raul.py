import logging
import os
from decimal import Decimal

import pandas as pd
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from producer.models import (
    Category,
    MarketplaceProduct,
    Producer,
    Product,
)
from user.models import Role, UserProfile

# Set up logging
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    help = "Import Rahal Attar products from Excel file"

    def add_arguments(self, parser):
        _ = parser.add_argument("excel_file", type=str, help="Path to the Excel file containing the Rahal Attar data")

    def get_product_name(self, row):
        """Extract product name from the row"""
        product_name = row.get("Product Name")
        if pd.notna(product_name) and str(product_name).strip() and str(product_name).strip().lower() != "nan":
            return f"Ruhal Attar - {str(product_name).strip()}"
        return None

    def get_price(self, row):
        """Extract and validate price from the row"""
        try:
            price = float(row.get("Price", 0)) if pd.notna(row.get("Price")) else None
            if price and price > 0:
                return price
        except (ValueError, TypeError):
            pass
        return None

    def get_description(self, row):
        """Extract description from the row"""
        description = row.get("Description")
        if pd.notna(description) and str(description).strip() and str(description).strip().lower() != "nan":
            return str(description).strip()
        return None

    def handle(self, *args, **options):
        excel_file_path = options["excel_file"]

        if not os.path.exists(excel_file_path):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file_path}"))
            return

        try:
            # Read the Excel file
            df = pd.read_excel(excel_file_path)

            # Check if required columns exist
            required_columns = ["Product Name", "Price", "Description"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                self.stdout.write(self.style.ERROR(f"Missing required columns: {missing_columns}"))
                return

            with transaction.atomic():
                # Get or create user
                user = User.objects.get(id=118)

                # Get producer
                producer = Producer.objects.get(id=131)

                # Get or create "Fragrances" category
                try:
                    fragrances_category = Category.objects.get(code="HB")
                except Category.DoesNotExist:
                    fragrances_category = Category.objects.create(
                        code="HB", name="Health & Beauty", description="Premium fragrances and attars"
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created category: {fragrances_category.name}"))

                # Process each row in the Excel file
                products_created = 0
                products_updated = 0
                products_skipped = 0

                for index, row in df.iterrows():
                    try:
                        row_num = int(index) + 2

                        # Get product name
                        product_name = self.get_product_name(row)

                        # Skip if no product name found
                        if not product_name:
                            self.stdout.write(
                                self.style.WARNING(f"Row {row_num}: Skipping - no product name found")
                            )
                            products_skipped += 1
                            continue

                        # Get price
                        price = self.get_price(row)

                        # Skip if price is not present or invalid
                        if price is None:
                            self.stdout.write(
                                self.style.WARNING(f'Row {row_num}: Skipping "{product_name}" - no valid price')
                            )
                            products_skipped += 1
                            continue

                        # Get description
                        description = self.get_description(row)

                        # Create or update product
                        product, product_created = Product.objects.get_or_create(
                            name=product_name,
                            producer=producer,
                            defaults={
                                "description": description,
                                "user": user,
                                "category": fragrances_category,
                                "old_category": Product.ProductCategory.HEALTH_BEAUTY,
                                "price": price,
                                "cost_price": price,
                                "stock": 10,
                                "reorder_level": 5,
                                "is_active": True,
                            },
                        )

                        if product_created:
                            products_created += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"Row {row_num}: Created product: {product_name} (Price: {price})")
                            )
                        else:
                            # Update existing product
                            product.description = description
                            product.price = price
                            product.cost_price = price
                            product.category = fragrances_category
                            product.old_category = Product.ProductCategory.HEALTH_BEAUTY
                            if not product.sku:
                                product.sku = f'FR-{product_name[:10].upper().replace(" ", "")}-{int(price)}'
                            product.save()
                            products_updated += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"Row {row_num}: Updated product: {product_name} (Price: {price})")
                            )

                        # Create or update marketplace product for this product
                        try:
                            mp, mp_created = MarketplaceProduct.objects.get_or_create(
                                product=product,
                                defaults={
                                    "listed_price": price,
                                    "is_available": True,
                                },
                            )
                            if mp_created:
                                self.stdout.write(
                                    self.style.SUCCESS(f"Row {row_num}: Created marketplace product for {product_name}")
                                )
                            else:
                                mp.listed_price = price
                                mp.is_available = True
                                mp.save()
                                self.stdout.write(
                                    self.style.SUCCESS(f"Row {row_num}: Updated marketplace product for {product_name}")
                                )
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f"Row {row_num}: Failed to create/update marketplace product: {str(e)}")
                            )

                    except Exception as e:
                        row_num = int(index) + 2
                        self.stdout.write(self.style.ERROR(f"Error processing row {row_num}: {str(e)}"))
                        products_skipped += 1
                        continue

                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n{'='*60}\n"
                        f"Import completed successfully!\n"
                        f"{'='*60}\n"
                        f"Products created: {products_created}\n"
                        f"Products updated: {products_updated}\n"
                        f"Products skipped: {products_skipped}\n"
                        f"{'='*60}"
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {str(e)}"))
            import traceback

            self.stdout.write(self.style.ERROR(traceback.format_exc()))
