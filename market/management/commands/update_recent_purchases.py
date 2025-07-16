from django.core.management.base import BaseCommand
from django.utils import timezone

from market.models import MarketplaceSale, SaleStatus
from producer.models import MarketplaceProduct


class Command(BaseCommand):
    help = "Update recent_purchases_count for all marketplace products based on sales in the last 24 hours"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Starting to update recent purchases count..."))

        products = MarketplaceProduct.objects.all()
        updated_count = 0
        total_products = products.count()
        self.stdout.write(self.style.SUCCESS(f"Found {total_products} products to process..."))

        for product in products:
            twenty_four_hours_ago = timezone.now() - timezone.timedelta(hours=24)

            purchase_count = MarketplaceSale.objects.filter(
                product=product,
                sale_date__gte=twenty_four_hours_ago,
                status__in=[
                    SaleStatus.PROCESSING,
                    SaleStatus.SHIPPED,
                    SaleStatus.DELIVERED,
                ],
            ).count()

            if product.recent_purchases_count != purchase_count:
                product.recent_purchases_count = purchase_count
                product.save(update_fields=["recent_purchases_count"])
                updated_count += 1

        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"✅ Successfully updated {updated_count} products with recent purchases count")
            )
        else:
            self.stdout.write(self.style.WARNING("ℹ️  No products required updates for recent purchases count"))
