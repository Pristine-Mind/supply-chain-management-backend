from django.urls import path
from .views import DailyProductStatsView

urlpatterns = [
    path('daily-product-stats/', DailyProductStatsView.as_view(), name='daily-product-stats'),
]
