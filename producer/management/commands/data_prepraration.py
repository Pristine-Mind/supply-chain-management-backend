import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate synthetic bid data and export to CSV'

    def handle(self, *args, **kwargs):
        self.stdout.write('Generating synthetic bid data...')

        num_records = 10000
        num_products = 100
        num_users = 1000

        np.random.seed(42)

        data = []
        start_date = datetime(2023, 1, 1)

        for i in range(num_records):
            bid_id = i + 1
            product_id = np.random.randint(1, num_products + 1)
            user_id = np.random.randint(1, num_users + 1)
            bid_amount = np.random.uniform(100, 10000)
            max_bid_amount = bid_amount + np.random.uniform(10, 1000)
            bid_date = start_date + timedelta(days=np.random.randint(0, 365))

            data.append({
                'bid_id': bid_id,
                'product_id': product_id,
                'user_id': user_id,
                'bid_amount': round(bid_amount, 2),
                'max_bid_amount': round(max_bid_amount, 2),
                'bid_date': bid_date.strftime('%Y-%m-%d %H:%M:%S')
            })

        df = pd.DataFrame(data)

        csv_filename = 'synthetic_bid_data.csv'
        df.to_csv(csv_filename, index=False)

        self.stdout.write(self.style.SUCCESS(f'Successfully created synthetic bid data and saved to {csv_filename}'))
