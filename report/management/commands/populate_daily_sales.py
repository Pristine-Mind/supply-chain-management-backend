import logging
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError
from django.db.models import F, Case, When, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate
from django.utils import timezone

from market.models import CartItem
from report.models import DailySalesReport, DailySalesReportItem

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate a DailySalesReport and related items for a given date.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='YYYY-MM-DD date to report (defaults to today)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate report even if it exists (deletes old)',
        )

    def handle(self, *args, **options):
        try:
            report_date = (
                timezone.datetime.strptime(options['date'], '%Y-%m-%d').date()
                if options.get('date') else timezone.localdate()
            )
        except (ValueError, TypeError):
            raise CommandError('Invalid --date format; expected YYYY-MM-DD')

        if report_date > timezone.localdate():
            raise CommandError('Cannot generate report for future dates.')

        logger.info(f"Generating report for {report_date}")

        if options['force']:
            DailySalesReport.objects.filter(report_date=report_date).delete()

        try:
            with transaction.atomic():
                report, created = DailySalesReport.objects.get_or_create(
                    report_date=report_date,
                    defaults={'total_items': 0, 'total_revenue': Decimal('0.00')}
                )
                if not created and not options['force']:
                    self.stdout.write(self.style.WARNING(
                        f'Report for {report_date} already exists. Use --force to override.'))
                    return

                price_expr = Case(
                    When(product__discounted_price__isnull=False, then=F('product__discounted_price')),
                    default=F('product__listed_price'),
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                )

                qs = (
                    CartItem.objects
                    .select_related('product__product__user')
                    .annotate(date=TruncDate('cart__created_at'))
                    .filter(date=report_date)
                    .annotate(
                        sale_price=ExpressionWrapper(price_expr, output_field=DecimalField()),
                        line_total=ExpressionWrapper(F('quantity') * price_expr, output_field=DecimalField())
                    )
                    .values('product_id', 'cart__user_id', 'date', 'sale_price', 'quantity', 'product__product__user_id')
                )

                if options['force']:
                    DailySalesReportItem.objects.filter(report=report).delete()

                items = []
                total_items = 0
                total_revenue = Decimal('0.00')

                for row in qs.iterator(chunk_size=500):
                    qty = row['quantity'] or 0
                    price = row['sale_price'] or Decimal('0.00')
                    total = row['line_total'] or (price * qty)

                    items.append(DailySalesReportItem(
                        report=report,
                        date=row['date'],
                        product_id=row['product_id'],
                        customer_id=row['cart__user_id'],
                        product_owner_id=row['product__product__user_id'],
                        unit_price=price,
                        quantity=qty,
                        line_total=total
                    ))
                    total_items += qty
                    total_revenue += total

                if not items:
                    self.stdout.write(self.style.WARNING(
                        f'No sales for {report_date}; created empty report.'))
                else:
                    DailySalesReportItem.objects.bulk_create(items, batch_size=200)

                report.total_items = total_items
                report.total_revenue = total_revenue.quantize(Decimal('0.01'))
                report.generated_at = timezone.now()
                report.save()

        except IntegrityError as e:
            logger.exception("Integrity error generating report")
            raise CommandError(f"DB integrity error: {e}")
        except Exception as e:
            logger.exception("Error generating report")
            raise CommandError(f"Unexpected error: {e}")

        self.stdout.write(self.style.SUCCESS(
            f'Report {report_date} generated: {total_items} items, revenue {total_revenue}'
        ))
