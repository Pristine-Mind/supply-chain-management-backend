import uuid

from django.core.management.base import BaseCommand
from faker import Faker

from producer.models import Customer, Order, Producer, Product, Sale


class Command(BaseCommand):
    help = "Create dummy data"

    def handle(self, *args, **kwargs):
        fake = Faker()

        # Create 100 Producers
        for _ in range(2):
            producer = Producer.objects.create(
                name=fake.company(),
                contact=fake.phone_number(),
                email=fake.email(),
                address=fake.address(),
                registration_number=fake.isbn10(),
                user_id=1,
            )
            self.stdout.write(self.style.SUCCESS(f"Created Producer: {producer.name}"))

            # Create 5 Customers for each Producer
            for _ in range(2):
                customer = Customer.objects.create(
                    name=fake.name(),
                    customer_type=fake.random_element(elements=("Retailer", "Wholesaler", "Distributor")),
                    contact=fake.phone_number(),
                    email=fake.email(),
                    billing_address=fake.address(),
                    shipping_address=fake.address(),
                    credit_limit=fake.pydecimal(left_digits=5, right_digits=2, positive=True),
                    current_balance=fake.pydecimal(left_digits=4, right_digits=2, positive=True),
                    user_id=1,
                )
                self.stdout.write(self.style.SUCCESS(f"  Created Customer: {customer.name}"))

                # Create 3 Products for each Producer
                for _ in range(2):
                    product = Product.objects.create(
                        name=fake.word(),
                        description=fake.sentence(),
                        sku=fake.ean13(),
                        price=fake.pydecimal(left_digits=3, right_digits=2, positive=True),
                        cost_price=fake.pydecimal(left_digits=3, right_digits=2, positive=True),
                        stock=6000,
                        producer=producer,
                        user_id=1,
                    )
                    self.stdout.write(self.style.SUCCESS(f"    Created Product: {product.name}"))

                    # Create 10 Orders for each Customer and Product
                    for _ in range(2):
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
                            # payment_status=fake.random_element(elements=("Pending", "Paid")),
                            order_number=order_number,
                            user_id=1,
                        )
                        self.stdout.write(self.style.SUCCESS(f"Created Order ID: {order.id}"))

                        # Create 10 Sales for each Customer and Product
                        for _ in range(2):
                            sale = Sale.objects.create(
                                # customer=customer,
                                # product=product,
                                order=order,
                                quantity=fake.random_int(min=1, max=50),
                                sale_price=product.price * fake.random_int(min=1, max=50),
                                user_id=1,
                            )
                        self.stdout.write(self.style.SUCCESS(f"Created Sale ID: {sale.id}"))

        self.stdout.write(self.style.SUCCESS("Successfully created at least 100 dummy records for each model!"))
