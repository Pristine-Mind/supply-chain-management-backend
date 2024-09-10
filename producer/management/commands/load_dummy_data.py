from django.core.management.base import BaseCommand
from faker import Faker
import uuid

from producer.models import Producer, Customer, Product, Order, Sale


class Command(BaseCommand):
    help = "Create dummy data"

    def handle(self, *args, **kwargs):
        fake = Faker()

        # Create 100 Producers
        for _ in range(100):
            producer = Producer.objects.create(
                name=fake.company(),
                contact=fake.phone_number(),
                email=fake.email(),
                address=fake.address(),
                registration_number=fake.isbn10(),
            )
            self.stdout.write(self.style.SUCCESS(f"Created Producer: {producer.name}"))

            # Create 5 Customers for each Producer
            for _ in range(5):
                customer = Customer.objects.create(
                    name=fake.name(),
                    customer_type=fake.random_element(elements=("Retailer", "Wholesaler", "Distributor")),
                    contact=fake.phone_number(),
                    email=fake.email(),
                    billing_address=fake.address(),
                    shipping_address=fake.address(),
                    credit_limit=fake.pydecimal(left_digits=5, right_digits=2, positive=True),
                    current_balance=fake.pydecimal(left_digits=4, right_digits=2, positive=True),
                )
                self.stdout.write(self.style.SUCCESS(f"  Created Customer: {customer.name}"))

                # Create 3 Products for each Producer
                for _ in range(3):
                    product = Product.objects.create(
                        name=fake.word(),
                        description=fake.sentence(),
                        sku=fake.ean13(),
                        price=fake.pydecimal(left_digits=3, right_digits=2, positive=True),
                        cost_price=fake.pydecimal(left_digits=3, right_digits=2, positive=True),
                        stock=fake.random_int(min=1, max=500),
                        producer=producer,
                    )
                    self.stdout.write(self.style.SUCCESS(f"    Created Product: {product.name}"))

                    # Create 10 Orders for each Customer and Product
                    for _ in range(10):
                        order_number = str(uuid.uuid4())
                        order = Order.objects.create(
                            customer=customer,
                            product=product,
                            quantity=fake.random_int(min=1, max=100),
                            status=fake.random_element(
                                elements=("Pending", "Approved", "Shipped", "Delivered", "Cancelled")
                            ),
                            total_price=product.price * fake.random_int(min=1, max=100),
                            order_date=fake.date_time_this_year(),
                            payment_status=fake.random_element(elements=("Pending", "Paid")),
                            order_number=order_number,
                        )
                        self.stdout.write(self.style.SUCCESS(f"Created Order ID: {order.id}"))

                    # Create 10 Sales for each Customer and Product
                    for _ in range(10):
                        sale = Sale.objects.create(
                            customer=customer,
                            product=product,
                            quantity=fake.random_int(min=1, max=50),
                            sale_price=product.price * fake.random_int(min=1, max=50),
                        )
                        self.stdout.write(self.style.SUCCESS(f"      Created Sale ID: {sale.id}"))

        self.stdout.write(self.style.SUCCESS("Successfully created at least 100 dummy records for each model!"))
