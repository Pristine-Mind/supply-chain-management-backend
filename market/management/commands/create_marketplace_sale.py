# management/commands/create_marketplace_sales.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction, models
from django.contrib.auth import get_user_model
from datetime import timedelta
from decimal import Decimal
import random
import string
from faker import Faker
from market.models import (
    MarketplaceSale, MarketplaceProduct, SaleStatus, 
    PaymentStatus
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Create sample marketplace sales for testing'

    def __init__(self):
        super().__init__()
        self.fake = Faker()

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', 
            type=int, 
            default=500,
            help='Number of marketplace sales to create (default: 500)'
        )
        parser.add_argument(
            '--anonymous-ratio',
            type=float,
            default=0.3,
            help='Ratio of anonymous buyers (0.0-1.0, default: 0.3)'
        )
        parser.add_argument(
            '--status-distribution',
            type=str,
            default='20,60,15,5',
            help='Status distribution as percentages: pending,completed,cancelled,refunded (default: 20,60,15,5)'
        )
        parser.add_argument(
            '--payment-status-distribution',
            type=str,
            default='10,70,15,5',
            help='Payment status distribution: pending,paid,failed,refunded (default: 10,70,15,5)'
        )
        parser.add_argument(
            '--date-range-days',
            type=int,
            default=90,
            help='Create sales within last N days (default: 90)'
        )
        parser.add_argument(
            '--currency-distribution',
            type=str,
            default='USD:60,EUR:25,NPR:15',
            help='Currency distribution as currency:percentage (default: USD:60,EUR:25,NPR:15)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for bulk creation (default: 100)'
        )

    def handle(self, *args, **options):
        count = options['count']
        anonymous_ratio = options['anonymous_ratio']
        date_range_days = options['date_range_days']
        batch_size = options['batch_size']

        # Validate anonymous ratio
        if not 0 <= anonymous_ratio <= 1:
            raise CommandError("Anonymous ratio must be between 0.0 and 1.0")

        # Parse status distributions
        try:
            pending_pct, completed_pct, cancelled_pct, refunded_pct = map(
                int, options['status_distribution'].split(',')
            )
            if pending_pct + completed_pct + cancelled_pct + refunded_pct != 100:
                raise ValueError("Status percentages must sum to 100")
        except ValueError as e:
            raise CommandError(f"Invalid status distribution: {e}")

        try:
            pay_pending_pct, pay_paid_pct, pay_failed_pct, pay_refunded_pct = map(
                int, options['payment_status_distribution'].split(',')
            )
            if pay_pending_pct + pay_paid_pct + pay_failed_pct + pay_refunded_pct != 100:
                raise ValueError("Payment status percentages must sum to 100")
        except ValueError as e:
            raise CommandError(f"Invalid payment status distribution: {e}")

        # Parse currency distribution
        try:
            currency_data = {}
            total_currency_pct = 0
            for item in options['currency_distribution'].split(','):
                currency, pct = item.split(':')
                currency_data[currency.strip()] = int(pct)
                total_currency_pct += int(pct)
            
            if total_currency_pct != 100:
                raise ValueError("Currency percentages must sum to 100")
        except ValueError as e:
            raise CommandError(f"Invalid currency distribution: {e}")

        # Check if we have enough data
        users = User.objects.filter(is_active=True)
        products = MarketplaceProduct.objects.filter(is_available=True)
        
        if users.count() < 2:
            raise CommandError("Need at least 2 active users (buyers and sellers)")
        
        if products.count() == 0:
            raise CommandError("Need at least 1 active marketplace product")

        self.stdout.write(f"Found {users.count()} users and {products.count()} products")
        self.stdout.write(f"Creating {count} marketplace sales...")

        # Prepare distribution lists for random selection
        status_choices = self._create_weighted_choices([
            (SaleStatus.PENDING, pending_pct),
            (SaleStatus.DELIVERED, completed_pct),
            (SaleStatus.CANCELLED, cancelled_pct),
            (SaleStatus.REFUNDED, refunded_pct),
        ])

        payment_status_choices = self._create_weighted_choices([
            (PaymentStatus.PENDING, pay_pending_pct),
            (PaymentStatus.PAID, pay_paid_pct),
            (PaymentStatus.FAILED, pay_failed_pct),
            (PaymentStatus.REFUNDED, pay_refunded_pct),
        ])

        currency_choices = self._create_weighted_choices([
            (currency, pct) for currency, pct in currency_data.items()
        ])

        # Create sales in batches
        sales_created = 0
        errors = 0

        for batch_start in range(0, count, batch_size):
            batch_end = min(batch_start + batch_size, count)
            batch_sales = []

            try:
                with transaction.atomic():
                    for i in range(batch_start, batch_end):
                        try:
                            sale_data = self._generate_sale_data(
                                users, products, anonymous_ratio, date_range_days,
                                status_choices, payment_status_choices, currency_choices
                            )
                            batch_sales.append(MarketplaceSale(**sale_data))
                        except Exception as e:
                            errors += 1
                            self.stdout.write(
                                self.style.ERROR(f"Error generating sale {i+1}: {str(e)}")
                            )

                    # Bulk create the batch
                    if batch_sales:
                        MarketplaceSale.objects.bulk_create(batch_sales)
                        sales_created += len(batch_sales)
                        self.stdout.write(f"Created batch: {sales_created}/{count} sales")

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error creating batch {batch_start}-{batch_end}: {str(e)}")
                )
                errors += len(batch_sales)

        # Final report
        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {sales_created} marketplace sales")
        )
        
        if errors > 0:
            self.stdout.write(
                self.style.WARNING(f"Encountered {errors} errors during creation")
            )

        # Show some statistics
        self._show_creation_stats()

    def _generate_sale_data(self, users, products, anonymous_ratio, date_range_days,
                           status_choices, payment_status_choices, currency_choices):
        """Generate data for a single marketplace sale"""
        
        # Select random product and users
        product = random.choice(products)
        seller = random.choice(users)
        
        # Ensure buyer is different from seller
        potential_buyers = users.exclude(id=seller.id)
        if potential_buyers.exists():
            buyer_user = random.choice(potential_buyers)
        else:
            buyer_user = seller  # Fallback if only one user exists

        # Determine if anonymous buyer
        is_anonymous = random.random() < anonymous_ratio

        # Generate sale date within date range
        days_ago = random.randint(0, date_range_days)
        sale_date = timezone.now() - timedelta(days=days_ago)

        # Generate order number
        order_number = self._generate_order_number()

        # Generate quantities and pricing
        quantity = random.randint(1, 10)
        
        # Use product price with some variation (±20%)
        base_price = product.listed_price
        variation = random.uniform(-0.2, 0.2)
        unit_price = base_price * (1 + variation)
        unit_price = round(unit_price, 2)

        subtotal = Decimal(str(unit_price)) * quantity
        
        # Generate tax (0-15%)
        tax_rate = random.uniform(0, 0.15)
        tax_amount = subtotal * Decimal(str(tax_rate))
        tax_amount = tax_amount.quantize(Decimal('0.01'))

        # Generate shipping cost (0-50)
        shipping_cost = Decimal(str(random.uniform(0, 50))).quantize(Decimal('0.01'))

        total_amount = subtotal + tax_amount + shipping_cost

        # Select status and payment status
        status = random.choice(status_choices)
        payment_status = random.choice(payment_status_choices)
        
        # Adjust payment status based on sale status
        if status == SaleStatus.DELIVERED:
            payment_status = PaymentStatus.PAID
        elif status == SaleStatus.CANCELLED and payment_status == PaymentStatus.PAID:
            payment_status = PaymentStatus.REFUNDED

        # Select currency
        currency = random.choice(currency_choices)

        # Build sale data
        sale_data = {
            'order_number': order_number,
            'sale_date': sale_date,
            'currency': currency,
            'seller': seller,
            'product': product,
            'quantity': quantity,
            'unit_price': unit_price,
            'unit_price_at_purchase': unit_price,  # Same as current price for simplicity
            'subtotal': subtotal,
            'tax_amount': tax_amount,
            'shipping_cost': shipping_cost,
            'total_amount': total_amount,
            'status': status,
            'payment_status': payment_status,
        }

        # Add buyer information
        if is_anonymous:
            sale_data.update({
                'buyer': None,
                'buyer_name': self.fake.name(),
                'buyer_email': self.fake.email(),
                'buyer_phone': f"+977-98{random.randint(10000000, 99999999)}",
            })
        else:
            sale_data.update({
                'buyer': buyer_user,
                'buyer_name': buyer_user.get_full_name() or buyer_user.username,
                'buyer_email': buyer_user.email or self.fake.email(),
                'buyer_phone': f"+977-98{random.randint(10000000, 99999999)}",
            })

        return sale_data

    def _generate_order_number(self):
        """Generate unique order number"""
        timestamp = timezone.now().strftime('%Y%m%d')
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"ORD-{timestamp}-{random_part}"

    def _create_weighted_choices(self, choices_with_weights):
        """Create a list of choices based on weights for random selection"""
        weighted_choices = []
        for choice, weight in choices_with_weights:
            weighted_choices.extend([choice] * weight)
        return weighted_choices

    def _show_creation_stats(self):
        """Show statistics about created sales"""
        total_sales = MarketplaceSale.objects.count()
        total_revenue = MarketplaceSale.objects.aggregate(
            total=models.Sum('total_amount')
        )['total'] or 0

        status_stats = MarketplaceSale.objects.values('status').annotate(
            count=models.Count('id')
        )

        payment_stats = MarketplaceSale.objects.values('payment_status').annotate(
            count=models.Count('id')
        )

        self.stdout.write(f"\n=== Creation Statistics ===")
        self.stdout.write(f"Total Sales: {total_sales}")
        self.stdout.write(f"Total Revenue: ${total_revenue}")
        
        self.stdout.write(f"\nStatus Breakdown:")
        for stat in status_stats:
            self.stdout.write(f"  {stat['status']}: {stat['count']}")

        self.stdout.write(f"\nPayment Status Breakdown:")
        for stat in payment_stats:
            self.stdout.write(f"  {stat['payment_status']}: {stat['count']}")