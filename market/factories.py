import factory
from django.contrib.auth.models import User
from .models import Purchase, Bid, ChatMessage

from producer.models import MarketplaceProduct
from producer.factories import ProductFactory


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user_{n}")
    password = factory.PostGenerationMethodCall("set_password", "password")


class MarketplaceProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MarketplaceProduct

    product = factory.SubFactory(ProductFactory)
    listed_price = 120.00
    is_available = True
    bid_end_date = factory.Faker("date_time_this_year")


class PurchaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Purchase

    buyer = factory.SubFactory(UserFactory)
    product = factory.SubFactory(MarketplaceProductFactory)
    quantity = 1
    purchase_price = 120.00


class BidFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Bid

    bidder = factory.SubFactory(UserFactory)
    product = factory.SubFactory(MarketplaceProductFactory)
    bid_amount = 150.00


class ChatMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ChatMessage

    sender = factory.SubFactory(UserFactory)
    product = factory.SubFactory(MarketplaceProductFactory)
    message = "Is this product available?"
