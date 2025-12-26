from django.conf import settings
from django.db import models


class BusinessInteraction(models.Model):
    INTERACTION_TYPES = [
        ("view", "Profile Viewed"),
        ("contact", "Contact Initiated"),
        ("order", "Order Placed"),
        ("connect", "Connection Request"),
    ]

    business = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="initiated_interactions")
    target_business = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_interactions"
    )
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    weight = models.FloatField(default=1.0)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("business", "target_business", "interaction_type")
        indexes = [
            models.Index(fields=["business", "target_business"]),
            models.Index(fields=["target_business", "interaction_type"]),
        ]
