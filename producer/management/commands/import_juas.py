import logging
import os
from decimal import Decimal
import io

import pandas as pd
from django.core.management.base import BaseCommand
from django.core.files import File
from django.core.files.base import ContentFile
from django.db import transaction
from openpyxl import load_workbook
from PIL import Image as PILImage

from producer.models import (
    Category,
    MarketplaceProduct,
    Producer,
    Product,
    ProductImage,
)

# Set up logging
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    help = "Import products with embedded images from Excel file"

    def add_arguments(self, parser):
        _ = parser.add_argument(
            "excel_file",
            type=str,
            help="Path to the Excel file containing product data with embedded images",
        )
        parser.add_argument(
            "--producer-id",
            type=int,
            default=131,
            help="Producer ID (default: 131)",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=118,
            help="User ID (default: 118)",
        )
        parser.add_argument(
            "--category-code",
            type=str,
            default="HB",
            help="Category code (default: HB for Health & Beauty)",
        )

    def get_product_name(self, row):
        """Extract product name from the row"""
        product_name = row.get("product_name")
        if pd.notna(product_name) and str(product_name).strip() and str(product_name).strip().lower() != "nan":
            return str(product_name).strip()
        return None

    def get_product_id(self, row):
        """Extract product ID from the row"""
        product_id = row.get("#") or row.get("id") or row.get("ID")
        if pd.notna(product_id):
            try:
                return str(int(product_id)).strip()
            except (ValueError, TypeError):
                return str(product_id).strip()
        return None

    def get_mrp(self, row):
        """Extract and validate MRP from the row"""
        try:
            mrp = row.get("mrp")
            if pd.notna(mrp):
                # Convert to string and clean
                mrp_str = str(mrp).strip()
                if mrp_str:
                    # Remove any non-numeric characters except decimal point
                    cleaned = "".join(c for c in mrp_str if c.isdigit() or c == ".")
                    if cleaned:
                        return Decimal(cleaned)
        except (ValueError, TypeError, AttributeError) as e:
            logging.warning(f"Error parsing MRP: {e}")
        return Decimal("0")

    def get_description(self, row):
        """Extract description from the row"""
        description = row.get("description")
        if pd.notna(description) and str(description).strip() and str(description).strip().lower() != "nan":
            return str(description).strip()
        return ""

    def extract_embedded_image(self, worksheet, row_num, product_name):
        """Extract embedded image from Excel worksheet for specific row"""
        try:
            # Try to extract from drawing objects/shapes
            if hasattr(worksheet, "_images") and worksheet._images:
                # Map image anchors to their row positions
                images_by_row = {}
                for img in worksheet._images:
                    try:
                        # Get the row where image is anchored (openpyxl is 0-indexed)
                        anchor_row = img.anchor._from.row + 1
                        images_by_row[anchor_row] = img
                        logging.info(f"Found embedded image at row {anchor_row}")
                    except Exception as e:
                        logging.warning(f"Error processing image anchor: {e}")
                        continue

                if images_by_row:
                    logging.info(f"Looking for image at row {row_num}. Available rows: {list(images_by_row.keys())}")

                    # Check if current row has an image
                    if row_num in images_by_row:
                        try:
                            img_obj = images_by_row[row_num]

                            # Extract image data
                            image_data = img_obj._data()
                            logging.info(f"Image data size for row {row_num}: {len(image_data)} bytes")

                            # Convert to bytes
                            image_bytes = io.BytesIO(image_data)

                            # Open with PIL to determine format
                            pil_image = PILImage.open(image_bytes)

                            # Determine file extension
                            if pil_image.format:
                                extension = pil_image.format.lower()
                            else:
                                extension = "png"

                            # Reset buffer
                            image_bytes.seek(0)

                            # Clean product name for filename
                            safe_name = "".join(c for c in product_name if c.isalnum() or c in (" ", "-", "_")).rstrip()
                            safe_name = safe_name.replace(" ", "_")[:50]

                            # Generate filename
                            filename = f"{safe_name}.{extension}"

                            logging.info(f"Successfully extracted image for row {row_num}: {filename}")
                            # Return the BytesIO object directly, not wrapped in File yet
                            return filename, image_bytes
                        except Exception as e:
                            logging.error(f"Error extracting image data for row {row_num}: {e}", exc_info=True)
                            pass

            # Try to extract from drawing shapes (images inserted as shapes)
            if hasattr(worksheet, "_drawing") and worksheet._drawing:
                logging.info(f"Found drawing in worksheet, attempting to extract images from shapes")
                try:
                    # Get all drawing elements
                    if hasattr(worksheet._drawing, "image_part"):
                        images = worksheet._drawing.image_part
                        if images:
                            for img in images.images:
                                # Try to get image by row reference
                                try:
                                    image_bytes = io.BytesIO(img.blob)
                                    pil_image = PILImage.open(image_bytes)

                                    if pil_image.format:
                                        extension = pil_image.format.lower()
                                    else:
                                        extension = "png"

                                    image_bytes.seek(0)
                                    safe_name = "".join(
                                        c for c in product_name if c.isalnum() or c in (" ", "-", "_")
                                    ).rstrip()
                                    safe_name = safe_name.replace(" ", "_")[:50]
                                    filename = f"{safe_name}.{extension}"

                                    logging.info(f"Successfully extracted image from drawing for row {row_num}: {filename}")
                                    return filename, image_bytes
                                except Exception as e:
                                    logging.warning(f"Error processing drawing image: {e}")
                                    continue
                except Exception as e:
                    logging.warning(f"Error accessing drawing images: {e}")

            logging.warning(f"No images found for row {row_num}")

        except Exception as e:
            logging.warning(f"Error extracting image for row {row_num}: {e}", exc_info=True)

        return None, None

    def handle(self, *args, **options):
        excel_file_path = options["excel_file"]
        producer_id = options["producer_id"]
        user_id = options["user_id"]
        category_code = options["category_code"]

        if not os.path.exists(excel_file_path):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file_path}"))
            return

        try:
            # Load workbook to extract embedded images
            wb = load_workbook(excel_file_path, data_only=True)
            ws = wb.active  # Use first worksheet

            # Also read with pandas for data extraction
            df = pd.read_excel(excel_file_path)

            # Clean column names
            df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_").str.replace("#", "id")

            # Check if required columns exist
            required_columns = ["product_name", "mrp", "description"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                self.stdout.write(self.style.ERROR(f"Missing required columns: {missing_columns}"))
                self.stdout.write(self.style.WARNING(f"Available columns: {list(df.columns)}"))
                return

            with transaction.atomic():
                # Get or create user
                from django.contrib.auth.models import User

                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
                    return

                # Get producer
                try:
                    producer = Producer.objects.get(id=producer_id)
                except Producer.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"Producer with ID {producer_id} not found"))
                    return

                # Get or create category
                try:
                    category = Category.objects.get(code=category_code)
                except Category.DoesNotExist:
                    # Create default category based on code
                    if category_code == "HB":
                        category_name = "Health & Beauty"
                    elif category_code == "FO":
                        category_name = "Food"
                    else:
                        category_name = f"Category {category_code}"

                    category = Category.objects.create(
                        code=category_code, name=category_name, description=f"Products imported for {producer.name}"
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created category: {category.name}"))

                # Process each row in the Excel file
                products_created = 0
                products_updated = 0
                products_skipped = 0
                images_attached = 0

                for index, row in df.iterrows():
                    try:
                        row_num = int(index) + 2  # +1 for 0-index, +1 for header row

                        # Get product data
                        product_name = self.get_product_name(row)

                        # Skip if no product name found
                        if not product_name:
                            self.stdout.write(self.style.WARNING(f"Row {row_num}: Skipping - no product name found"))
                            products_skipped += 1
                            continue

                        # Get other data
                        product_id = self.get_product_id(row)
                        mrp = self.get_mrp(row)
                        description = self.get_description(row)

                        # Skip if MRP is 0 (optional, you can remove this if needed)
                        if mrp == Decimal("0"):
                            self.stdout.write(self.style.WARNING(f'Row {row_num}: Skipping "{product_name}" - MRP is 0'))
                            products_skipped += 1
                            continue

                        # Create or update product
                        product, product_created = Product.objects.get_or_create(
                            name=product_name,
                            producer=producer,
                            defaults={
                                "description": description,
                                "user": user,
                                "category": category,
                                "old_category": Product.ProductCategory.HEALTH_BEAUTY,
                                "price": mrp,
                                "cost_price": mrp,
                                "stock": 10,
                                "reorder_level": 5,
                                "is_active": True,
                            },
                        )

                        if product_created:
                            products_created += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"Row {row_num}: Created product: {product_name} (MRP: {mrp})")
                            )
                        else:
                            # Update existing product
                            product.description = description
                            product.price = mrp
                            product.cost_price = mrp
                            product.category = category
                            product.old_category = Product.ProductCategory.HEALTH_BEAUTY
                            if not product.sku and product_id:
                                product.sku = f"{category_code}-{product_id}"
                            product.save()
                            products_updated += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"Row {row_num}: Updated product: {product_name} (MRP: {mrp})")
                            )

                        # Extract and attach embedded image
                        try:
                            filename, image_bytes = self.extract_embedded_image(ws, row_num, product_name)

                            if filename and image_bytes:
                                # Create ProductImage instance with the image
                                image_bytes.seek(0)  # Ensure we're at the start
                                product_image = ProductImage(
                                    product=product,
                                    alt_text=product_name,
                                )
                                product_image.image.save(filename, ContentFile(image_bytes.read()), save=True)
                                images_attached += 1
                                self.stdout.write(self.style.SUCCESS(f"Row {row_num}: Attached image to {product_name}"))
                            else:
                                self.stdout.write(self.style.WARNING(f"Row {row_num}: No image found for {product_name}"))
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"Row {row_num}: Failed to attach image: {str(e)}"))

                        # Create or update marketplace product
                        try:
                            mp, mp_created = MarketplaceProduct.objects.get_or_create(
                                product=product,
                                defaults={
                                    "listed_price": mrp,
                                    "is_available": True,
                                },
                            )
                            if mp_created:
                                self.stdout.write(
                                    self.style.SUCCESS(f"Row {row_num}: Created marketplace product for {product_name}")
                                )
                            else:
                                mp.listed_price = mrp
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
                        import traceback

                        self.stdout.write(self.style.ERROR(traceback.format_exc()))
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
                        f"Images attached: {images_attached}\n"
                        f"{'='*60}"
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {str(e)}"))
            import traceback

            self.stdout.write(self.style.ERROR(traceback.format_exc()))
