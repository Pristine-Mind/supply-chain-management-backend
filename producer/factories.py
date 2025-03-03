import factory
from factory.django import DjangoModelFactory
from faker import Faker

from .models import Producer, Customer, Product, Order, Sale, LedgerEntry, AuditLog
from user.models import User

fake = Faker()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class ProducerFactory(DjangoModelFactory):
    class Meta:
        model = Producer

    name = factory.Faker("company")
    contact = factory.Faker("phone_number")
    email = factory.Faker("email")
    address = factory.Faker("address")
    registration_number = factory.Faker("isbn10")


class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer

    name = factory.Faker("name")
    customer_type = "Retailer"
    contact = factory.Faker("phone_number")
    email = factory.Faker("email")
    billing_address = factory.Faker("address")
    shipping_address = factory.Faker("address")
    credit_limit = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True)
    current_balance = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    producer = factory.SubFactory(ProducerFactory)


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Faker("word")
    description = factory.Faker("sentence")
    sku = factory.Faker("ean13")
    price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    cost_price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    stock = factory.Faker("random_int", min=1, max=500)
    producer = factory.SubFactory(ProducerFactory)


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = Order

    customer = factory.SubFactory(CustomerFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = factory.Faker("random_int", min=1, max=100)
    status = "Pending"
    total_price = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    order_date = factory.Faker("date_time")
    payment_status = "Pending"


class SaleFactory(DjangoModelFactory):
    class Meta:
        model = Sale

    customer = factory.SubFactory(CustomerFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = factory.Faker("random_int", min=1, max=50)
    sale_price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)


class LedgerEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LedgerEntry

    account_type = LedgerEntry.AccountType.INVENTORY
    amount = 50000.00
    debit = True
    reference_id = factory.Sequence(lambda n: f"REF{n:04d}")
    date = factory.Faker("date")
    related_entity = 1
    user = factory.SubFactory(UserFactory)


class AuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditLog

    transaction_type = AuditLog.TransactionType.PROCUREMENT
    reference_id = factory.Sequence(lambda n: f"REF{n:04d}")
    date = factory.Faker("date")
    entity_id = 1
    amount = 50000.00
    user = factory.SubFactory(UserFactory)
