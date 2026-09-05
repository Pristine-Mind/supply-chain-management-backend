import gc
import logging
import time

from django.core.management.base import BaseCommand
from django.db import connection, connections

from producer.models import MarketplaceProduct
from producer.utils import generate_and_save_product_tags, unload_keybert_model

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "One time backfill script to generate AI tags for Marketplace products. Runs synchronously with aggressive memory management."

    def add_arguments(self, parser):
        parser.add_argument("--category", type=str, help="Extract tags for specific category code (EG, HL, FA, etc.)")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Number of products per batch (default: None = process all products at once)",
        )
        parser.add_argument("--product-id", type=int, help="Extract tags for a single product ID")
        parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between products (default: 2.0s)")
        parser.add_argument(
            "--batch-delay", type=float, default=5.0, help="Delay in seconds between batches (default: 5.0s)"
        )
        parser.add_argument("--force", action="store_true", help="Process all products to replace old tags")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        delay = options["delay"]
        batch_delay = options["batch_delay"]
        category = options.get("category")
        product_id = options.get("product_id")

        if product_id:
            queryset = MarketplaceProduct.objects.filter(id=product_id).order_by("id")
        elif category:
            queryset = MarketplaceProduct.objects.filter(product__category__code=category).order_by("id")
        else:
            queryset = MarketplaceProduct.objects.all().order_by("id")

        total = queryset.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No products found to process."))
            return

        if batch_size is None:
            batch_size = total

        queryset.update(search_tags=None)
        self.stdout.write(self.style.SUCCESS(f"Cleared existing search_tags for {total} products"))

        self.stdout.write(f"Processing {total} products in batches of {batch_size} with {delay}s delay between products.")
        self.stdout.write(f"Batch delay: {batch_delay}s (for garbage collection and memory cleanup)")

        queued = 0
        batch_num = 0

        for batch_start in range(0, total, batch_size):
            batch_num += 1
            batch_ids = queryset[batch_start : batch_start + batch_size].values_list("id", flat=True)

            self.stdout.write(f"Processing batch {batch_num}...")

            for prod_id in batch_ids:
                try:
                    generate_and_save_product_tags(prod_id)
                    queued += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error processing product {prod_id}: {e}"))
                    logger.exception(f"Error processing product {prod_id}")

                time.sleep(delay)  # Delay between products to prevent memory spikes

            gc.collect()

            # Close all database connections to prevent connection pool exhaustion
            connections.close_all()

            # Unload KeyBERT model from memory between batches to free VRAM/RAM
            unload_keybert_model()

            self.stdout.write(f"⏳ Processed {queued}/{total} products. Waiting {batch_delay}s for cleanup...")
            time.sleep(batch_delay)  # Delay between batches for memory cleanup

        self.stdout.write(self.style.SUCCESS(f"\n Successfully processed {queued}/{total} products!"))
        self.stdout.write(self.style.SUCCESS("Search tags have been generated and saved."))

        # Final cleanup
        connections.close_all()
