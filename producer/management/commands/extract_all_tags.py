from django.core.management.base import BaseCommand
from django.db import transaction

from producer.models import MarketplaceProduct
from producer.tag_extractor import TagExtractor


class Command(BaseCommand):
    help = "Extract search tags for all marketplace products"

    def add_arguments(self, parser):
        parser.add_argument("--category", type=str, help="Extract tags for specific category code (EG, HL, FA, etc.)")
        parser.add_argument("--batch-size", type=int, default=100, help="Number of products to process in each batch")
        parser.add_argument("--product-id", type=int, help="Extract tags for a single product ID")
        parser.add_argument("--force", action="store_true", help="Force re-extraction even if tags exist")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        category = options.get("category")
        product_id = options.get("product_id")
        force = options["force"]

        if product_id:
            queryset = MarketplaceProduct.objects.filter(id=product_id)
        elif category:
            queryset = MarketplaceProduct.objects.filter(product__category__code=category)
        else:
            if force:
                queryset = MarketplaceProduct.objects.all()
            else:
                queryset = MarketplaceProduct.objects.filter(search_tags=[])

        queryset = queryset.select_related("product", "product__category")
        total = queryset.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No products found to process"))
            return

        self.stdout.write(f"📊 Processing {total} products...")

        processed = 0
        for batch_start in range(0, total, batch_size):
            batch = queryset[batch_start : batch_start + batch_size]

            with transaction.atomic():
                for product in batch:
                    tags = TagExtractor.extract_and_save(product, save=True)
                    processed += 1

                    if processed % 10 == 0:
                        self.stdout.write(f" Processed {processed}/{total}")

            self.stdout.write(f"Batch {batch_start//batch_size + 1} completed")

        self.stdout.write(self.style.SUCCESS(f"\n Successfully extracted tags for {processed} products!"))

        if processed > 0:
            sample = MarketplaceProduct.objects.first()
            if sample and sample.search_tags:
                self.stdout.write(f"\n Sample tags: {', '.join(sample.search_tags[:10])}...")
