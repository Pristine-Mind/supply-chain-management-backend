import logging
import os
import requests
from decimal import Decimal
from io import BytesIO

import pandas as pd
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from bs4 import BeautifulSoup

from producer.models import Category, Producer, Product, ProductImage, MarketplaceProduct
from user.models import Role, UserProfile

# Set up logging
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    help = "Import Health and Beauty Store data from Excel file"

    def add_arguments(self, parser):
        _ = parser.add_argument("excel_file", type=str, help="Path to the Excel file containing the data")

    def clean_html_to_text(self, html_content):
        """Convert HTML content to clean text"""
        if pd.isna(html_content) or not html_content:
            return ""

        try:
            # Parse HTML and extract text
            soup = BeautifulSoup(str(html_content), "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            return text.strip()
        except Exception as e:
            # If parsing fails, return the content as-is
            return str(html_content).strip()

    def get_product_name(self, row):
        """Extract product name from English column first, then Nepali column"""
        # Try English name first
        english_name = row.get("Product Name(English)")
        if pd.notna(english_name) and str(english_name).strip() and str(english_name).strip().lower() != "nan":
            return str(english_name).strip()

        # Try Nepali name
        nepali_name = row.get("Product Name(Nepali) look function")
        if pd.notna(nepali_name) and str(nepali_name).strip() and str(nepali_name).strip().lower() != "nan":
            return str(nepali_name).strip()

        return None

    def get_description(self, row):
        """Combine Main Description and Highlights into a single description"""
        main_desc = row.get("Main Description")
        highlights = row.get("Highlights")

        # Clean HTML from both fields
        main_desc_text = self.clean_html_to_text(main_desc)
        highlights_text = self.clean_html_to_text(highlights)

        # Combine descriptions
        parts = []
        if main_desc_text:
            parts.append(main_desc_text)
        if highlights_text:
            parts.append(f"Highlights: {highlights_text}")

        return " | ".join(parts) if parts else "Health and Beauty Product"

    def download_and_save_image(self, url, product, alt_text=""):
        """Download image from URL and save as ProductImage"""
        try:
            # Clean URL
            url = str(url).strip()
            if not url or url.lower() == "nan":
                return False

            # Set headers to mimic a browser request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            # Download image with timeout
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()

            # Get file extension from URL or content type
            content_type = response.headers.get("content-type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                ext = "jpg"
            elif "png" in content_type:
                ext = "png"
            elif "webp" in content_type:
                ext = "webp"
            else:
                # Try to extract from URL
                ext = url.split(".")[-1].split("?")[0].lower()
                if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
                    ext = "jpg"  # Default to jpg

            # Create filename
            filename = f"{product.sku}_{len(product.images.all()) + 1}.{ext}"

            # Save image content
            image_content = ContentFile(response.content)

            # Create ProductImage instance
            product_image = ProductImage(
                product=product, alt_text=alt_text or f"{product.name} - Image {len(product.images.all()) + 1}"
            )
            product_image.image.save(filename, image_content, save=True)

            return True

        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.WARNING(f"Failed to download image from {url}: {str(e)}"))
            return False
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Error saving image from {url}: {str(e)}"))
            return False

    def handle(self, *args, **options):
        excel_file_path = options["excel_file"]

        if not os.path.exists(excel_file_path):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file_path}"))
            return

        try:
            # Read the Excel file
            df = pd.read_excel(excel_file_path)

            # Check if required columns exist
            required_columns = ["Price"]
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

                # Create user with username "health_beauty_store"
                username = "physio_nepal_surgical_house"
                user, user_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": "test@gmail.com",
                        "first_name": "Physio",
                        "last_name": "Nepal Surgical House",
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
                        "phone_number": "9800000002",
                        "business_type": "distributor",
                        "registered_business_name": "Physio Nepal Surgical House",
                        "has_access_to_marketplace": True,
                    },
                )

                if profile_created:
                    self.stdout.write(self.style.SUCCESS(f"Created user profile for: {username}"))
                else:
                    # Update existing profile
                    user_profile.role = business_owner_role
                    user_profile.phone_number = "9800000002"
                    user_profile.business_type = "distributor"
                    user_profile.registered_business_name = "Physio Nepal Surgical House"
                    user_profile.has_access_to_marketplace = True
                    user_profile.save()
                    self.stdout.write(self.style.WARNING(f"Updated user profile for: {username}"))

                # Create producer
                producer, producer_created = Producer.objects.get_or_create(
                    registration_number="HB2025",
                    defaults={
                        "name": "Health & Beauty Store",
                        "contact": "9800000002",
                        "email": "healthbeauty@gmail.com",
                        "address": "Kathmandu, Nepal",
                        "user": user,
                    },
                )

                if producer_created:
                    self.stdout.write(self.style.SUCCESS(f"Created producer: {producer.name}"))
                else:
                    self.stdout.write(self.style.WARNING(f"Producer already exists: {producer.name}"))

                # Get or create "Health & Beauty" category
                try:
                    health_beauty_category = Category.objects.get(code="HB")
                except Category.DoesNotExist:
                    health_beauty_category = Category.objects.create(
                        code="HB", name="Health & Beauty", description="Health and beauty products"
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created category: {health_beauty_category.name}"))

                # Process each row in the Excel file
                products_created = 0
                products_updated = 0
                products_skipped = 0
                images_downloaded = 0
                images_failed = 0

                for index, row in df.iterrows():
                    try:
                        row_num = int(index) + 2

                        # Get product name (English first, then Nepali)
                        product_name = self.get_product_name(row)

                        # Skip if no product name found
                        if not product_name:
                            self.stdout.write(
                                self.style.WARNING(f"Row {row_num}: Skipping - no product name in English or Nepali columns")
                            )
                            products_skipped += 1
                            continue

                        # Handle Price conversion
                        try:
                            price = float(row["Price"]) if pd.notna(row["Price"]) else None
                        except (ValueError, TypeError):
                            price = None

                        # Skip if price is not present or invalid
                        if price is None or price <= 0:
                            self.stdout.write(
                                self.style.WARNING(f'Row {row_num}: Skipping "{product_name}" - no valid price')
                            )
                            products_skipped += 1
                            continue

                        # Get description from Main Description and Highlights
                        description = self.get_description(row)

                        # Create or update product
                        product, product_created = Product.objects.get_or_create(
                            name=product_name,
                            producer=producer,
                            defaults={
                                "description": description,
                                "user": user,
                                "category": health_beauty_category,
                                "old_category": Product.ProductCategory.HEALTH_BEAUTY,
                                "additional_information": "",
                                "price": price,
                                "cost_price": price,
                                "stock": 20,
                                "reorder_level": 10,
                                "is_active": True,
                                "sku": f'HB-{product_name[:10].upper().replace(" ", "")}-{int(price)}',
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
                            product.category = health_beauty_category
                            product.old_category = Product.ProductCategory.HEALTH_BEAUTY
                            if not product.sku:
                                product.sku = f'HB-{product_name[:10].upper().replace(" ", "")}-{int(price)}'
                            product.save()
                            products_updated += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"Row {row_num}: Updated product: {product_name} (Price: {price})")
                            )

                        # Download and save product images
                        image_urls = []
                        for col in ["Product Images1", "Product Images2", "Product Images3"]:
                            if col in row and pd.notna(row[col]):
                                url = str(row[col]).strip()
                                if url and url.lower() != "nan":
                                    image_urls.append(url)

                        # Clear existing images if updating product
                        if not product_created:
                            product.images.all().delete()

                        # Download each image
                        for idx, url in enumerate(image_urls, 1):
                            self.stdout.write(f"  Downloading image {idx} from: {url[:80]}...")
                            success = self.download_and_save_image(url, product, alt_text=f"{product_name} - Image {idx}")
                            if success:
                                images_downloaded += 1
                                self.stdout.write(self.style.SUCCESS(f"    ✓ Image {idx} downloaded"))
                            else:
                                images_failed += 1
                                self.stdout.write(self.style.WARNING(f"    ✗ Image {idx} failed"))

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
                        f"Images downloaded: {images_downloaded}\n"
                        f"Images failed: {images_failed}\n"
                        f"{'='*60}"
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {str(e)}"))
            import traceback

            self.stdout.write(self.style.ERROR(traceback.format_exc()))
