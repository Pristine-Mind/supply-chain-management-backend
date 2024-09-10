from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from producer.models import MarketplaceProduct


class Purchase(models.Model):
    """
    Represents a purchase made by a customer from the marketplace.

    Fields:
    - buyer: The customer who bought the product.
    - product: The product that was purchased.
    - quantity: The number of items purchased.
    - purchase_price: The price at which the product was purchased.
    - purchase_date: The date of the purchase.
    """
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Buyer"))
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, verbose_name=_("Product"))
    quantity = models.PositiveIntegerField(verbose_name=_("Quantity"))
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Purchase Price"))
    purchase_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Purchase Date"))

    def __str__(self):
        return f"{self.buyer.username} bought {self.quantity} of {self.product.product.name}"

    class Meta:
        verbose_name = _("Purchase")
        verbose_name_plural = _("Purchases")


class Bid(models.Model):
    """
    Represents a bid placed on a marketplace product by a customer.

    Fields:
    - bidder: The customer placing the bid.
    - product: The product being bid on.
    - bid_amount: The amount offered for the product.
    - bid_date: The date the bid was placed.
    """
    bidder = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Bidder"))
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, verbose_name=_("Product"))
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Bid Amount"))
    bid_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Bid Date"))

    def __str__(self):
        return f"{self.bidder.username} bid {self.bid_amount} on {self.product.product.name}"

    class Meta:
        verbose_name = _("Bid")
        verbose_name_plural = _("Bids")


class ChatMessage(models.Model):
    """
    Represents a chat message related to a marketplace product.
    Fields:
    - sender: The user who sent the message.
    - product: The product being discussed.
    - message: The content of the message.
    - timestamp: The time the message was sent.
    """
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Sender"))
    product = models.ForeignKey(MarketplaceProduct, on_delete=models.CASCADE, verbose_name=_("Product"))
    message = models.TextField(verbose_name=_("Message"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Timestamp"))

    def __str__(self):
        return f"Message from {self.sender.username} about {self.product.product.name}"

    class Meta:
        verbose_name = _("Chat Message")
        verbose_name_plural = _("Chat Messages")
