import factory
from factory.django import DjangoModelFactory
from faker import Faker

from user.models import User
from .models import AuditLog, Customer, LedgerEntry, Order, Producer, Product, Sale

fake = Faker()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")

    @factory.post_generation
    def create_profile(obj, create, extracted, **kwargs):
        if not create:
            return
        try:
            from user.models import UserProfile
            UserProfile.objects.get_or_create(user=obj, defaults={"phone_number": "9800000000"})
        except Exception:
            pass



class ProducerFactory(DjangoModelFactory):
    class Meta:
        model = Producer

    user = factory.SubFactory(UserFactory)
    name = factory.Faker("company")
    contact = factory.Faker("phone_number")
    email = factory.Faker("email")
    address = factory.Faker("address")
    registration_number = factory.Sequence(lambda n: f"REG-{n:06d}")


class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer

    user = factory.SubFactory(UserFactory)
    name = factory.Faker("name")
    customer_type = "Retailer"
    contact = factory.Faker("phone_number")
    email = factory.Faker("email")
    billing_address = factory.Faker("address")
    shipping_address = factory.Faker("address")
    credit_limit = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True)
    current_balance = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Faker("word")
    description = factory.Faker("sentence")
    sku = factory.Faker("ean13")
    price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    cost_price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    stock = factory.Faker("random_int", min=1, max=500)
    user = factory.SubFactory(UserFactory)


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    customer = factory.SubFactory(CustomerFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = factory.Faker("random_int", min=1, max=100)
    status = "Pending"
    total_price = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    order_date = factory.Faker("date_time")


class SaleFactory(DjangoModelFactory):
    class Meta:
        model = Sale

    user = factory.SubFactory(UserFactory)
    order = factory.SubFactory(OrderFactory)
    quantity = factory.Faker("random_int", min=1, max=50)
    sale_price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)


class LedgerEntryFactory(DjangoModelFactory):
    class Meta:
        model = LedgerEntry

    account_type = LedgerEntry.AccountType.INVENTORY
    amount = 50000.00
    debit = True
    reference_id = factory.Sequence(lambda n: f"REF{n:04d}")
    date = factory.Faker("date")
    related_entity = 1
    user = factory.SubFactory(UserFactory)


class AuditLogFactory(DjangoModelFactory):
    class Meta:
        model = AuditLog

    transaction_type = AuditLog.TransactionType.PROCUREMENT
    reference_id = factory.Sequence(lambda n: f"REF{n:04d}")
    date = factory.Faker("date")
    entity_id = 1
    amount = 50000.00
    user = factory.SubFactory(UserFactory)
