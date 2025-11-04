from django.core.management.base import BaseCommand

from market.models import Invoice, MarketplaceSale
from market.signals import generate_invoice_from_marketplace_sale


class Command(BaseCommand):
    help = "Test invoice generation signals manually"

    def handle(self, *args, **options):
        self.stdout.write("🔧 Testing invoice generation signals...")

        # Get sales with completed payment status
        completed_sales = MarketplaceSale.objects.filter(payment_status="paid")
        self.stdout.write(f"Found {completed_sales.count()} sales with payment_status='paid'")

        for sale in completed_sales:
            self.stdout.write(f"\n📋 Testing sale: {sale.order_number}")
            self.stdout.write(f"   Payment Status: {sale.payment_status}")
            self.stdout.write(f"   Total Amount: NPR {sale.total_amount}")

            # Check existing invoices
            try:
                existing_invoice = sale.invoice
                self.stdout.write(f"   ✅ Existing invoice: {existing_invoice.invoice_number}")
                continue
            except:
                self.stdout.write("   ℹ️ No existing invoice")

            # Manually trigger the signal
            self.stdout.write("   🚀 Manually triggering signal...")
            try:
                generate_invoice_from_marketplace_sale(sender=MarketplaceSale, instance=sale, created=False)

                # Check if invoice was created
                try:
                    new_invoice = sale.invoice
                    self.stdout.write(f"   ✅ Invoice created: {new_invoice.invoice_number}")
                except:
                    self.stdout.write("   ❌ No invoice created")

            except Exception as e:
                self.stdout.write(f"   ❌ Error: {str(e)}")

        # Test Django signal mechanism by triggering a save
        self.stdout.write("\n🔄 Testing Django signal mechanism...")
        if completed_sales.exists():
            sale = completed_sales.first()
            self.stdout.write(f"Triggering save() on sale: {sale.order_number}")

            try:
                # Delete existing invoice first to test fresh creation
                try:
                    existing_invoice = sale.invoice
                    if existing_invoice:
                        existing_invoice.delete()
                        self.stdout.write("   🗑️ Deleted existing invoice for fresh test")
                except:
                    pass

                # Trigger save to test signal
                sale.save()

                # Check result
                try:
                    new_invoice = sale.invoice
                    self.stdout.write(f"   ✅ Signal worked! Invoice: {new_invoice.invoice_number}")
                except:
                    self.stdout.write("   ❌ Signal didn't fire - no invoice created")

            except Exception as e:
                self.stdout.write(f"   ❌ Error during save(): {str(e)}")

        # Summary
        total_invoices = Invoice.objects.count()
        self.stdout.write(f"\n📊 Total invoices in system: {total_invoices}")
        self.stdout.write("✅ Signal testing completed!")
