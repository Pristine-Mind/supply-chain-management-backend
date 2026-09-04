from django.core.management.base import BaseCommand
from producer.models import MarketplaceProduct
from producer.tasks import generate_and_save_product_tags

class Command(BaseCommand):
    help = 'One time backfill script to generate AI tags for Marketplace products via Celery in batches.'

    def add_arguments(self, parser):
        parser.add_argument("--category", type=str, help="Extract tags for specific category code (EG, HL, FA, etc.)")
        parser.add_argument("--batch-size", type=int, default=1000, help="Number of products to queue in each batch")
        parser.add_argument("--product-id", type=int, help="Extract tags for a single product ID")
        parser.add_argument("--force", action="store_true", help="Process all products to replace old tags")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        category = options.get("category")
        product_id = options.get("product_id")

        if product_id:
            queryset = MarketplaceProduct.objects.filter(id=product_id)
        elif category:
            queryset = MarketplaceProduct.objects.filter(product__category__code=category)
        else:
            queryset = MarketplaceProduct.objects.all()

        total = queryset.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No products found to process."))
            return

        self.stdout.write(f"Queuing {total} products to Celery in batches of {batch_size}")

        queued = 0
        for batch_start in range(0, total, batch_size):
            batch_ids = queryset[batch_start : batch_start + batch_size].values_list('id', flat=True)

            for prod_id in batch_ids:
                generate_and_save_product_tags.delay(prod_id)
                queued += 1

            self.stdout.write(f"⏳ Queued {queued}/{total}")

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully sent {queued} tasks to Celery"))
        self.stdout.write(self.style.SUCCESS("The Celery workers will now overwrite all old tags in the background."))