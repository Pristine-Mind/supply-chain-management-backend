from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from recommendations.engine.hybrid import get_hybrid_recommendations

# from recommendations.models import BusinessRecommendation

User = get_user_model()


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        b2b_users = User.objects.filter(user_profile__b2b_verified=True, user_profile__has_access_to_marketplace=True)
        for user in b2b_users:
            recs = get_hybrid_recommendations(user, limit=30)
            # Optionally cache or log
            self.stdout.write(f"Generated {len(recs)} recs for {user.username}")
