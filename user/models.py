import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from producer.models import City


class UserProfile(models.Model):
    """
    UserProfile model to store additional user information.

    Fields:
    - user: One-to-one relationship with the User model.
    - phone_number: Phone number of the user.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    shop_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    has_access_to_marketplace = models.BooleanField(verbose_name=_("Has Access to Marketplace"), default=False)
    location = models.ForeignKey(
        City, on_delete=models.CASCADE, verbose_name="Location", help_text="Location of the product", null=True, blank=True
    )

    def __str__(self):
        return f"Shop profile for {self.user.username} with Shop ID {self.shop_id}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


class Contact(models.Model):
    name = models.CharField(max_length=255, verbose_name="Full Name")
    email = models.EmailField(verbose_name="Email Address")
    subject = models.CharField(max_length=255, verbose_name="Subject")
    message = models.TextField(verbose_name="Message")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    def __str__(self):
        return self.name
