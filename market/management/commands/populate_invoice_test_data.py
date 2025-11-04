"""
Django Management Command to populate test data for Invoice Generation System

Usage: python manage.py populate_invoice_test_data
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from market.models import Cart, CartItem, Delivery, Invoice, MarketplaceSale
from payment.models import PaymentTransaction, PaymentTransactionStatus
from producer.models import City, MarketplaceProduct, Product


class Command(BaseCommand):
    help = "Populate test data for invoice generation system testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Clean existing test data before creating new data",
        )

    def handle(self, *args, **options):
        if options["clean"]:
            self.stdout.write("🧹 Cleaning existing test data...")
            self.clean_test_data()

        self.stdout.write("🚀 Starting test data population for Invoice Generation System...")

        try:
            with transaction.atomic():
                # Create all test data
                buyer1, buyer2, seller1, seller2 = self.create_test_users()
                city1, city2 = self.create_test_cities()
                mp1, mp2, mp3, mp4 = self.create_test_products(seller1, seller2, city1, city2)
                cart1, cart2 = self.create_test_carts_and_items(buyer1, buyer2, mp1, mp2, mp3, mp4)
                delivery1, delivery2 = self.create_test_delivery_info(cart1, cart2, buyer1, buyer2)
                payment1, payment2 = self.create_test_payment_transactions(cart1, cart2, buyer1, buyer2)
                sale1, sale2 = self.create_test_marketplace_sales(buyer1, buyer2, seller1, seller2, mp1, mp3)

                self.stdout.write(self.style.SUCCESS("\n✅ All test data created successfully!"))

                # Check what invoices were generated
                self.check_generated_invoices()

                # Print test instructions
                self.print_test_instructions()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error creating test data: {str(e)}"))
            raise

    def clean_test_data(self):
        """Clean existing test data"""
        # Delete test users and related data
        test_usernames = ["buyer1", "buyer2", "seller1", "seller2"]
        for username in test_usernames:
            try:
                user = User.objects.get(username=username)
                user.delete()
            except User.DoesNotExist:
                pass

        # Clean up products with test SKUs
        test_skus = ["RICE-001", "HONEY-001", "SCARF-001", "TEA-001"]
        Product.objects.filter(sku__in=test_skus).delete()

        self.stdout.write("✅ Test data cleaned")

    def create_test_users(self):
        """Create test buyers and sellers"""
        self.stdout.write("\n📝 Creating test users...")

        # Create buyers
        buyer1, created = User.objects.get_or_create(
            username="buyer1",
            defaults={"email": "buyer1@example.com", "first_name": "John", "last_name": "Doe", "is_active": True},
        )
        if created:
            buyer1.set_password("password123")
            buyer1.save()

        buyer2, created = User.objects.get_or_create(
            username="buyer2",
            defaults={"email": "buyer2@example.com", "first_name": "Jane", "last_name": "Smith", "is_active": True},
        )
        if created:
            buyer2.set_password("password123")
            buyer2.save()

        # Create sellers
        seller1, created = User.objects.get_or_create(
            username="seller1",
            defaults={"email": "seller1@example.com", "first_name": "Ram", "last_name": "Farmer", "is_active": True},
        )
        if created:
            seller1.set_password("password123")
            seller1.save()

        seller2, created = User.objects.get_or_create(
            username="seller2",
            defaults={"email": "seller2@example.com", "first_name": "Sita", "last_name": "Producer", "is_active": True},
        )
        if created:
            seller2.set_password("password123")
            seller2.save()

        self.stdout.write(f"✅ Created users: {buyer1.username}, {buyer2.username}, {seller1.username}, {seller2.username}")
        return buyer1, buyer2, seller1, seller2

    def create_test_cities(self):
        """Create test cities"""
        self.stdout.write("\n🏙️ Creating test cities...")

        city1, created = City.objects.get_or_create(name="Kathmandu")
        city2, created = City.objects.get_or_create(name="Chitwan")

        self.stdout.write(f"✅ Created cities: {city1.name}, {city2.name}")
        return city1, city2

    def create_test_products(self, seller1, seller2, city1, city2):
        """Create test products and marketplace products"""
        self.stdout.write("\n🛍️ Creating test products...")

        # Product 1 - Organic Rice
        product1, created = Product.objects.get_or_create(
            name="Organic Basmati Rice",
            user=seller1,
            sku="RICE-001",
            defaults={
                "description": "Premium quality organic basmati rice grown in the hills of Nepal",
                "price": 150.00,
                "cost_price": 100.00,
                "stock": 100,
                "category": "GE",  # Groceries & Essentials
                "location": city1,
            },
        )

        marketplace_product1, created = MarketplaceProduct.objects.get_or_create(
            product=product1,
            listed_price=product1.price,
            defaults={
                "is_available": True,
            },
        )

        # Product 2 - Pure Honey
        product2, created = Product.objects.get_or_create(
            name="Pure Mountain Honey",
            user=seller1,
            sku="HONEY-001",
            defaults={
                "description": "Natural honey harvested from mountain bees in the Himalayas",
                "price": 800.00,
                "cost_price": 600.00,
                "stock": 25,
                "category": "HB",  # Health & Beauty
                "location": city1,
            },
        )

        marketplace_product2, created = MarketplaceProduct.objects.get_or_create(
            product=product2,
            listed_price=product2.price,
            defaults={
                "is_available": True,
            },
        )

        # Product 3 - Handmade Scarf
        product3, created = Product.objects.get_or_create(
            name="Traditional Pashmina Scarf",
            user=seller2,
            sku="SCARF-001",
            defaults={
                "description": "Handwoven pashmina scarf made by local artisans",
                "price": 2500.00,
                "cost_price": 2000.00,
                "stock": 15,
                "category": "FA",  # Fashion & Apparel
                "location": city2,
            },
        )

        marketplace_product3, created = MarketplaceProduct.objects.get_or_create(
            product=product3,
            listed_price=product3.price,
            defaults={
                "is_available": True,
            },
        )

        # Product 4 - Organic Tea
        product4, created = Product.objects.get_or_create(
            name="Himalayan Green Tea",
            user=seller2,
            sku="TEA-001",
            defaults={
                "description": "Premium green tea leaves from high altitude gardens",
                "price": 450.00,
                "cost_price": 300.00,
                "stock": 50,
                "category": "GE",  # Groceries & Essentials
                "location": city2,
            },
        )

        marketplace_product4, created = MarketplaceProduct.objects.get_or_create(
            product=product4,
            listed_price=product4.price,
            defaults={
                "is_available": True,
            },
        )

        self.stdout.write(f"✅ Created products: {product1.name}, {product2.name}, {product3.name}, {product4.name}")
        return marketplace_product1, marketplace_product2, marketplace_product3, marketplace_product4

    def create_test_carts_and_items(self, buyer1, buyer2, mp1, mp2, mp3, mp4):
        """Create test carts with items"""
        self.stdout.write("\n🛒 Creating test carts and cart items...")

        # Cart 1 - Buyer 1 with multiple items
        cart1, created = Cart.objects.get_or_create(user=buyer1, defaults={"created_at": timezone.now()})

        # Clear existing items if any
        CartItem.objects.filter(cart=cart1).delete()

        # Add items to cart 1
        CartItem.objects.create(cart=cart1, product=mp1, quantity=2)  # 2x Rice
        CartItem.objects.create(cart=cart1, product=mp2, quantity=1)  # 1x Honey
        CartItem.objects.create(cart=cart1, product=mp4, quantity=3)  # 3x Tea

        # Cart 2 - Buyer 2 with single expensive item
        cart2, created = Cart.objects.get_or_create(user=buyer2, defaults={"created_at": timezone.now()})

        # Clear existing items if any
        CartItem.objects.filter(cart=cart2).delete()

        # Add items to cart 2
        CartItem.objects.create(cart=cart2, product=mp3, quantity=1)  # 1x Scarf
        CartItem.objects.create(cart=cart2, product=mp1, quantity=5)  # 5x Rice

        self.stdout.write(f"✅ Created carts with items for {buyer1.username} and {buyer2.username}")
        return cart1, cart2

    def create_test_delivery_info(self, cart1, cart2, buyer1, buyer2):
        """Create test delivery information"""
        self.stdout.write("\n🚚 Creating test delivery information...")

        # Delivery for cart 1
        delivery1, created = Delivery.objects.get_or_create(
            cart=cart1,
            defaults={
                "customer_name": f"{buyer1.first_name} {buyer1.last_name}",
                "phone_number": "+977-9841234567",
                "email": buyer1.email,
                "address": "123 Thamel Street, Ward 26",
                "city": "Kathmandu",
                "state": "Bagmati",
                "zip_code": "44600",
                "latitude": 27.7172,
                "longitude": 85.3240,
                "created_at": timezone.now(),
            },
        )

        # Delivery for cart 2
        delivery2, created = Delivery.objects.get_or_create(
            cart=cart2,
            defaults={
                "customer_name": f"{buyer2.first_name} {buyer2.last_name}",
                "phone_number": "+977-9851234567",
                "email": buyer2.email,
                "address": "456 Lakeside Road, Ward 6",
                "city": "Pokhara",
                "state": "Gandaki",
                "zip_code": "33700",
                "latitude": 28.2096,
                "longitude": 83.9856,
                "created_at": timezone.now(),
            },
        )

        self.stdout.write("✅ Created delivery info for both carts")
        return delivery1, delivery2

    def create_test_payment_transactions(self, cart1, cart2, buyer1, buyer2):
        """Create test payment transactions"""
        self.stdout.write("\n💳 Creating test payment transactions...")

        # Calculate totals for cart 1
        cart1_subtotal = Decimal("0")
        for item in CartItem.objects.filter(cart=cart1):
            cart1_subtotal += Decimal(str(item.product.product.price)) * item.quantity

        cart1_tax = cart1_subtotal * Decimal("0.13")  # 13% VAT
        cart1_shipping = Decimal("100.00")
        cart1_total = cart1_subtotal + cart1_tax + cart1_shipping

        # Payment Transaction 1 - Completed
        payment1, created = PaymentTransaction.objects.get_or_create(
            user=buyer1,
            cart=cart1,
            defaults={
                "gateway": "KHALTI",
                "gateway_transaction_id": "TXN_" + timezone.now().strftime("%Y%m%d_%H%M%S") + "_001",
                "subtotal": cart1_subtotal,
                "tax_amount": cart1_tax,
                "shipping_cost": cart1_shipping,
                "total_amount": cart1_total,
                "status": PaymentTransactionStatus.COMPLETED,
                "completed_at": timezone.now(),
                "return_url": "https://example.com/success",
                "customer_name": f"{buyer1.first_name} {buyer1.last_name}",
                "customer_email": buyer1.email,
                "customer_phone": "+977-9841234567",
                "notes": "Test payment for invoice generation",
                "created_at": timezone.now() - timedelta(hours=1),
            },
        )

        # Calculate totals for cart 2
        cart2_subtotal = Decimal("0")
        for item in CartItem.objects.filter(cart=cart2):
            cart2_subtotal += Decimal(str(item.product.product.price)) * item.quantity

        cart2_tax = cart2_subtotal * Decimal("0.13")  # 13% VAT
        cart2_shipping = Decimal("150.00")
        cart2_total = cart2_subtotal + cart2_tax + cart2_shipping

        # Payment Transaction 2 - Pending (for testing manual completion)
        payment2, created = PaymentTransaction.objects.get_or_create(
            user=buyer2,
            cart=cart2,
            defaults={
                "gateway": "CONNECT_IPS",
                "gateway_transaction_id": "TXN_" + timezone.now().strftime("%Y%m%d_%H%M%S") + "_002",
                "subtotal": cart2_subtotal,
                "tax_amount": cart2_tax,
                "shipping_cost": cart2_shipping,
                "total_amount": cart2_total,
                "status": PaymentTransactionStatus.PENDING,
                "return_url": "https://example.com/success",
                "customer_name": f"{buyer2.first_name} {buyer2.last_name}",
                "customer_email": buyer2.email,
                "customer_phone": "+977-9851234567",
                "notes": "Test payment - can be completed manually",
                "created_at": timezone.now() - timedelta(minutes=30),
            },
        )

        self.stdout.write(f"✅ Created payment transactions:")
        self.stdout.write(f"   - Payment 1: {payment1.order_number} (COMPLETED) - NPR {payment1.total_amount}")
        self.stdout.write(f"   - Payment 2: {payment2.order_number} (PENDING) - NPR {payment2.total_amount}")

        return payment1, payment2

    def create_test_marketplace_sales(self, buyer1, buyer2, seller1, seller2, mp1, mp3):
        """Create test marketplace sales (legacy single-item system)"""
        self.stdout.write("\n💰 Creating test marketplace sales...")

        # Sale 1 - Completed (should auto-generate invoice)
        sale1, created = MarketplaceSale.objects.get_or_create(
            buyer=buyer1,
            seller=seller1,
            product=mp1,
            defaults={
                "quantity": 1,
                "unit_price": Decimal(str(mp1.product.price)).quantize(Decimal("0.01")),
                "unit_price_at_purchase": Decimal(str(mp1.product.price)).quantize(Decimal("0.01")),
                "subtotal": Decimal(str(mp1.product.price)).quantize(Decimal("0.01")),
                "tax_amount": (Decimal(str(mp1.product.price)) * Decimal("0.13")).quantize(Decimal("0.01")),
                "shipping_cost": Decimal("50.00"),
                "total_amount": (
                    Decimal(str(mp1.product.price)) + (Decimal(str(mp1.product.price)) * Decimal("0.13")) + Decimal("50.00")
                ).quantize(Decimal("0.01")),
                "currency": "NPR",
                "status": "delivered",  # Use valid SaleStatus choice
                "payment_status": "paid",  # Use valid PaymentStatus choice
                "buyer_name": f"{buyer1.first_name} {buyer1.last_name}",
                "buyer_email": buyer1.email,
                "buyer_phone": "+977-9841234567",
                "sale_date": timezone.now() - timedelta(hours=2),
            },
        )

        # Sale 2 - Pending payment (for testing manual completion)
        sale2, created = MarketplaceSale.objects.get_or_create(
            buyer=buyer2,
            seller=seller2,
            product=mp3,
            defaults={
                "quantity": 1,
                "unit_price": Decimal(str(mp3.product.price)).quantize(Decimal("0.01")),
                "unit_price_at_purchase": Decimal(str(mp3.product.price)).quantize(Decimal("0.01")),
                "subtotal": Decimal(str(mp3.product.price)).quantize(Decimal("0.01")),
                "tax_amount": (Decimal(str(mp3.product.price)) * Decimal("0.13")).quantize(Decimal("0.01")),
                "shipping_cost": Decimal("100.00"),
                "total_amount": (
                    Decimal(str(mp3.product.price)) + (Decimal(str(mp3.product.price)) * Decimal("0.13")) + Decimal("100.00")
                ).quantize(Decimal("0.01")),
                "currency": "NPR",
                "status": "processing",  # Use valid SaleStatus choice
                "payment_status": "pending",  # Use valid PaymentStatus choice
                "buyer_name": f"{buyer2.first_name} {buyer2.last_name}",
                "buyer_email": buyer2.email,
                "buyer_phone": "+977-9851234567",
                "sale_date": timezone.now() - timedelta(minutes=45),
            },
        )

        self.stdout.write(f"✅ Created marketplace sales:")
        self.stdout.write(f"   - Sale 1: {sale1.order_number} (COMPLETED) - NPR {sale1.total_amount}")
        self.stdout.write(f"   - Sale 2: {sale2.order_number} (PENDING) - NPR {sale2.total_amount}")

        return sale1, sale2

    def check_generated_invoices(self):
        """Check what invoices were auto-generated"""
        self.stdout.write("\n📋 Checking auto-generated invoices...")

        invoices = Invoice.objects.all()
        self.stdout.write(f"📊 Total invoices in system: {invoices.count()}")

        for invoice in invoices:
            self.stdout.write(f"   📄 {invoice.invoice_number}")
            self.stdout.write(f"      Customer: {invoice.customer_name} ({invoice.customer_email})")
            self.stdout.write(f"      Amount: {invoice.currency} {invoice.total_amount}")
            self.stdout.write(f"      Status: {invoice.status}")
            self.stdout.write(f"      Source: {invoice.source_order_number}")
            self.stdout.write(f'      PDF: {"✅" if invoice.pdf_file else "❌"}')
            self.stdout.write(f"      Line Items: {invoice.invoicelineitem_set.count()}")
            self.stdout.write("")

    def print_test_instructions(self):
        """Print instructions for testing the system"""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("🎯 TEST INSTRUCTIONS FOR INVOICE GENERATION SYSTEM")
        self.stdout.write("=" * 70)

        self.stdout.write("\n1. 🔍 CHECK AUTO-GENERATED INVOICES:")
        self.stdout.write("   - Go to Django Admin: /admin/")
        self.stdout.write("   - Navigate to Market → Invoices")
        self.stdout.write("   - You should see auto-generated invoices from completed payments/sales")

        self.stdout.write("\n2. 🧪 TEST MANUAL INVOICE GENERATION:")
        self.stdout.write("   - Go to Market → Payment Transactions")
        self.stdout.write("   - Find pending payment transactions")
        self.stdout.write('   - Change status to "completed"')
        self.stdout.write("   - Save and check if invoice is auto-generated")

        self.stdout.write("\n3. 📋 TEST ADMIN ACTIONS:")
        self.stdout.write("   - In Market → Invoices:")
        self.stdout.write('     • Select invoices and use "Generate PDF" action')
        self.stdout.write('     • Use "Send invoice email" action')
        self.stdout.write('     • Try "Download PDF" action')
        self.stdout.write("     • Test bulk operations")

        self.stdout.write("\n4. 🛒 TEST WITH MARKETPLACE SALES:")
        self.stdout.write("   - Go to Market → Marketplace Sales")
        self.stdout.write('   - Find sales with "pending" payment status')
        self.stdout.write('   - Change payment_status to "completed"')
        self.stdout.write("   - Save and verify invoice generation")

        self.stdout.write("\n💡 SAMPLE TEST DATA CREATED:")
        self.stdout.write("   - 4 Users: buyer1, buyer2, seller1, seller2")
        self.stdout.write("   - 4 Products: Rice, Honey, Scarf, Tea")
        self.stdout.write("   - 2 Carts with multiple items")
        self.stdout.write("   - 2 Payment transactions (1 completed, 1 pending)")
        self.stdout.write("   - 2 Marketplace sales (1 completed, 1 pending)")
        self.stdout.write("   - Delivery information with addresses")

        self.stdout.write("\n🔑 LOGIN CREDENTIALS:")
        self.stdout.write("   Username/Password: buyer1/password123, seller1/password123, etc.")

        self.stdout.write("\n" + "=" * 70)
