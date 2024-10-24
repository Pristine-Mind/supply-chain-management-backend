from user.models import UserProfile
from main.manager import set_current_shop


class ShopIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.headers.get('Authorization')
        print(f"Authorization Header: {auth_header}")
        print(f"Request User: {request.user}")
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
