import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from producer.models import Producer, Product, Category
from user.models import UserProfile, Role
import pandas as pd
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    help = "Import Rudra Kitchen Store data from Excel file"

    def add_arguments(self, parser):
        _ = parser.add_argument("excel_file", type=str, help="Path to the Excel file containing the data")

    def handle(self, *args, **options):
        excel_file_path = options["excel_file"]

        if not os.path.exists(excel_file_path):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file_path}"))
            return

        try:
            # Read the Excel file
            df = pd.read_excel(excel_file_path)

            # Check if required columns exist
            required_columns = ["Particulars", "UNIT", "MRP"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                self.stdout.write(self.style.ERROR(f"Missing required columns: {missing_columns}"))
                return

            with transaction.atomic():
                # Create or get business_owner role
                business_owner_role, _ = Role.objects.get_or_create(
                    code="business_owner",
                    defaults={
                        "name": "Business Owner",
                        "level": 3,
                        "description": "Owners of distributor/retailer businesses with full business access.",
                    },
                )

                # Create user with username "rudra_kitchen_store"
                username = "rudra_kitchen_store"
                user, user_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": "test@gmail.com",
                        "first_name": "Rudra",
                        "last_name": "Kitchen Store",
                        "is_active": True,
                    },
                )

                if user_created:
                    user.set_password("defaultpassword123")  # Set a default password
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"Created user: {username}"))
                else:
                    self.stdout.write(self.style.WARNING(f"User already exists: {username}"))

                # Create or update user profile with business_owner role
                user_profile, profile_created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "role": business_owner_role,
                        "phone_number": "9800000001",
                        "business_type": "retailer",
                        "registered_business_name": "Rudra Kitchen Store",
                        "has_access_to_marketplace": True,
                    },
                )

                if profile_created:
                    self.stdout.write(self.style.SUCCESS(f"Created user profile for: {username}"))
                else:
                    # Update existing profile
                    user_profile.role = business_owner_role
                    user_profile.phone_number = "9800000001"
                    user_profile.business_type = "retailer"
                    user_profile.registered_business_name = "Rudra Kitchen Store"
                    user_profile.has_access_to_marketplace = True
                    user_profile.save()
                    self.stdout.write(self.style.WARNING(f"Updated user profile for: {username}"))

                # Create producer
                producer, producer_created = Producer.objects.get_or_create(
                    registration_number="8833",
                    defaults={
                        "name": "Rudra Kitchen Store",
                        "contact": "9800000001",
                        "email": "test@gmail.com",
                        "address": "Kathmandu, Nepal",
                        "user": user,
                    },
                )

                if producer_created:
                    self.stdout.write(self.style.SUCCESS(f"Created producer: {producer.name}"))
                else:
                    self.stdout.write(self.style.WARNING(f"Producer already exists: {producer.name}"))

                # Get or create "Home & Living" category
                try:
                    home_living_category = Category.objects.get(code="HL")
                except Category.DoesNotExist:
                    home_living_category = Category.objects.create(
                        code="HL", name="Home & Living", description="Home and living products"
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created category: {home_living_category.name}"))

                # Process each row in the Excel file
                products_created = 0
                products_updated = 0

                for index, row in df.iterrows():
                    try:
                        row_num = int(index) + 1 if isinstance(index, (int, float)) else "unknown"

                        # Extract data from row
                        product_name = str(row["Particulars"]).strip()
                        unit = str(row["UNIT"]).strip() if pd.notna(row["UNIT"]) else ""

                        # Handle MRP conversion more safely
                        try:
                            mrp = float(row["MRP"]) if pd.notna(row["MRP"]) else 0.0
                        except (ValueError, TypeError):
                            self.stdout.write(
                                self.style.WARNING(f'Row {row_num}: Invalid MRP value "{row["MRP"]}", using 0.0')
                            )
                            mrp = 0.0

                        # Skip if product name is empty or NaN
                        if not product_name or product_name.lower() == "nan" or len(product_name.strip()) == 0:
                            self.stdout.write(self.style.WARNING(f"Row {row_num}: Skipping empty product name"))
                            continue

                        # Create or update product
                        product, product_created = Product.objects.get_or_create(
                            name=product_name,
                            producer=producer,
                            defaults={
                                "description": "Rudra Kitchen Store",
                                "user": user,
                                "category": home_living_category,
                                "old_category": Product.ProductCategory.HOME_LIVING,
                                "additional_information": unit,
                                "price": mrp,
                                "cost_price": mrp,
                                "stock": 0,  # Default stock to 0
                                "reorder_level": 10,
                                "is_active": True,
                                "sku": f'RKS-{product_name[:10].upper().replace(" ", "")}-{int(mrp)}',
                            },
                        )

                        if product_created:
                            products_created += 1
                            self.stdout.write(f"Row {row_num}: Created product: {product_name} (MRP: {mrp})")
                        else:
                            # Update existing product
                            product.description = "Rudra Kitchen Store"
                            product.additional_information = unit
                            product.price = mrp
                            product.cost_price = mrp
                            product.category = home_living_category
                            product.old_category = Product.ProductCategory.HOME_LIVING
                            if not product.sku:
                                product.sku = f'RKS-{product_name[:10].upper().replace(" ", "")}-{int(mrp)}'
                            product.save()
                            products_updated += 1
                            self.stdout.write(f"Row {row_num}: Updated product: {product_name} (MRP: {mrp})")

                    except Exception as e:
                        row_num = int(index) + 1 if isinstance(index, (int, float)) else "unknown"
                        self.stdout.write(self.style.ERROR(f"Error processing row {row_num}: {str(e)}"))
                        continue

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Import completed successfully!\n"
                        f"Products created: {products_created}\n"
                        f"Products updated: {products_updated}"
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {str(e)}"))
