from django.core.management.base import BaseCommand

from market.models import Invoice, MarketplaceSale


class Command(BaseCommand):
    help = "Test automatic invoice generation by changing sale status to paid"

    def handle(self, *args, **options):
        self.stdout.write("🔄 Testing automatic invoice generation...")

        # Find a sale with pending status
        pending_sales = MarketplaceSale.objects.filter(payment_status="pending")
        self.stdout.write(f"Found {pending_sales.count()} pending sales")

        if not pending_sales.exists():
            self.stdout.write("❌ No pending sales found. Creating test data may be needed.")
            return

        sale = pending_sales.first()
        self.stdout.write(f"Testing with sale: {sale.order_number}")
        self.stdout.write(f"Current payment_status: {sale.payment_status}")

        # Check current invoice count
        initial_count = Invoice.objects.count()
        self.stdout.write(f"Initial invoice count: {initial_count}")

        # Change status to paid - this should trigger the signal
        self.stdout.write("🚀 Changing payment_status to 'paid' to trigger signal...")
        sale.payment_status = "paid"
        sale.save()  # This should trigger the signal automatically

        # Check if invoice was created
        final_count = Invoice.objects.count()
        self.stdout.write(f"Final invoice count: {final_count}")

        if final_count > initial_count:
            # Find the new invoice
            try:
                new_invoice = sale.invoice
                self.stdout.write(f"✅ SUCCESS! Auto-generated invoice: {new_invoice.invoice_number}")
                self.stdout.write(f"   Customer: {new_invoice.customer_name}")
                self.stdout.write(f"   Total: NPR {new_invoice.total_amount}")
                self.stdout.write(f"   Status: {new_invoice.status}")
            except:
                self.stdout.write("✅ Invoice count increased but couldn't link to sale")
        else:
            self.stdout.write("❌ No new invoice was created - signal may not be working")

        self.stdout.write("✅ Test completed!")
