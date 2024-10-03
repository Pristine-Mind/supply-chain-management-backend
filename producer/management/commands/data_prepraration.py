import pandas as pd
from django.core.management.base import BaseCommand

from producer.models import Bid


class Command(BaseCommand):
    help = 'Extract bid data and export to CSV'

    def handle(self, *args, **kwargs):
        self.stdout.write('Extracting bid data...')
        bids = Bid.objects.all()
        data = []
        for bid in bids:
            data.append({
                'bid_id': bid.id,
                'product_id': bid.product.id,
                'user_id': bid.bidder.id,
                'bid_amount': bid.bid_amount,
                'max_bid_amount': bid.max_bid_amount,
                'bid_date': bid.bid_date,
            })
        df = pd.DataFrame(data)
        df.to_csv('bid_data.csv', index=False)
        self.stdout.write(self.style.SUCCESS('Successfully exported bid data to bid_data.csv'))
