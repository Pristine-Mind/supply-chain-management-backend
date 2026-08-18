from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AllUserViewSet, BusinessListView

app_name = "user"

router = DefaultRouter()
router.register(r"all-users", AllUserViewSet, basename="all-users")

urlpatterns = router.urls + [
    path("businesses/", BusinessListView.as_view(), name="business-list"),
]
