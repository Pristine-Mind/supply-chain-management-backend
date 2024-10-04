import pandas as pd
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create sequences of bid amounts for each product and export to CSV'

    def handle(self, *args, **kwargs):
        self.stdout.write('Loading synthetic bid data from CSV...')   
        try:
            bid_data = pd.read_csv('synthetic_bid_data.csv')
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('File "synthetic_bid_data.csv" not found. Please generate it first.'))
            return

        self.stdout.write('Converting bid_date to datetime...')
        bid_data['bid_date'] = pd.to_datetime(bid_data['bid_date'])

        self.stdout.write('Sorting bid data by product_id and bid_date...')
        bid_data = bid_data.sort_values(by=['product_id', 'bid_date'])

        self.stdout.write('Creating sequences of bid amounts...')
        sequences = []
        sequence_length = 2

        for product_id, group in bid_data.groupby('product_id'):
            group = group.reset_index(drop=True)
            for i in range(len(group) - sequence_length):
                sequences.append(group['max_bid_amount'].iloc[i:i + sequence_length + 1].tolist())

        if not sequences:
            self.stdout.write(self.style.WARNING('No sequences were generated. The data might not have enough records for the given sequence length.'))
            return

        self.stdout.write('Saving sequences to CSV...')
        pd.DataFrame(sequences).to_csv('bid_sequences.csv', index=False)
        self.stdout.write(self.style.SUCCESS('Successfully created bid sequences and exported to bid_sequences.csv'))
