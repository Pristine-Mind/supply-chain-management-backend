from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """
    UserProfile model to store additional user information.

    Fields:
    - user: One-to-one relationship with the User model.
    - phone_number: Phone number of the user.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.user.username} - {self.phone_number}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
