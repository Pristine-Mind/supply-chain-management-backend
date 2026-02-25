from django.urls import path
from .views import BusinessListView

app_name = 'user'

urlpatterns = [
    path('businesses/', BusinessListView.as_view(), name='business-list'),
]