from django.utils.deprecation import MiddlewareMixin

from main.manager import set_current_shop
from user.models import UserProfile


class ShopIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user and request.user.is_authenticated:
            try:
                user_profile = UserProfile.objects.filter(user=request.user).first()
                if user_profile:
                    set_current_shop(user_profile.shop_id)
                    print(f"Shop ID set to: {user_profile.shop_id}")
                else:
                    set_current_shop(None)
                    print("User profile not found, setting shop to None.")
            except Exception as e:
                set_current_shop(None)
                print(f"Exception in middleware: {e}")
        else:
            set_current_shop(None)
            print("User not authenticated, setting shop to None.")

        response = self.get_response(request)
        return response


class EnsureSessionKeyMiddleware(MiddlewareMixin):
    """
    Guarantees request.session.session_key exists by saving the session
    if needed. Add this *above* your view middleware in settings.
    """

    def process_request(self, request):
        # touch session so session_key is created
        if not request.session.session_key:
            request.session.save()
