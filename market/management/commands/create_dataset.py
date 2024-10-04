import csv
from django.core.management.base import BaseCommand
from django.utils import timezone

from market.models import Bid
from producer.models import MarketplaceProduct


class Command(BaseCommand):
    help = 'Generates a CSV dataset of bids for training a machine learning model.'

    def handle(self, *args, **kwargs):
        filename = 'bid_data.csv'
        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['product_id', 'listed_price', 'current_bid', 'past_bids_count', 'time_since_listing', 'suggested_bid'])

            for product in MarketplaceProduct.objects.all():
                listed_price = product.listed_price
                time_since_listing = (timezone.now() - product.listed_date).days
                bids = Bid.objects.filter(product=product).order_by('bid_date')

                current_bid = listed_price
                past_bids_count = 0

                for bid in bids:
                    past_bids_count += 1
                    current_bid = bid.max_bid_amount
                    writer.writerow([product.id, listed_price, current_bid, past_bids_count, time_since_listing, bid.max_bid_amount])

        self.stdout.write(self.style.SUCCESS(f'Dataset created successfully at {filename}'))
