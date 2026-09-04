from django.core.management.base import BaseCommand
from producer.models import MarketplaceProduct
from producer.tasks import generate_and_save_product_tags

class Command(BaseCommand):
    help = 'One time backfill script to generate AI tags for all existing Marketplace products via Celery.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Fetching all Marketplace Products"))
        all_products = MarketplaceProduct.objects.all()
        total = all_products.count()
        
        if total == 0:
            self.stdout.write(self.style.ERROR("No products found to process."))
            return
            
        self.stdout.write(self.style.SUCCESS(f"Found {total} products. Queuing tasks to Celery"))
        
        count = 0
        for mp in all_products:
            generate_and_save_product_tags.delay(mp.id) 
            count += 1
            if count % 1000 == 0:
                self.stdout.write(f"Queued {count}/{total} products")
                
        self.stdout.write(self.style.SUCCESS("All tasks successfully sent to Celery! The workers will now replace the old tags in the background."))