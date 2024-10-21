from user.models import UserProfile
from main.manager import set_current_shop


class ShopIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user and request.user.is_authenticated:
            try:
                user_profile = UserProfile.objects.get(user=request.user)
                set_current_shop(user_profile.shop_id)
            except UserProfile.DoesNotExist:
                set_current_shop(None)
        else:
            set_current_shop(None)

        response = self.get_response(request)
        return response
