"""
URL configuration for main project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from rest_framework.routers import DefaultRouter
from producer.views import (
    ProducerViewSet,
    CustomerViewSet,
    ProductViewSet,
    OrderViewSet,
    SaleViewSet,
    LoginAPIView,
    DashboardAPIView,
    UserInfoView,
    TopSalesCustomersView,
    TopOrdersCustomersView,
    StockListView,
    MarketplaceProductViewSet
)
from market.views import PurchaseViewSet, BidViewSet, ChatMessageViewSet

router = DefaultRouter()
router.register(r'producers', ProducerViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'products', ProductViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'stocklist', StockListView)
router.register(r'marketplace', MarketplaceProductViewSet)
router.register(r'purchases', PurchaseViewSet, basename='purchases')
router.register(r'bids', BidViewSet, basename='bids')
router.register(r'chats', ChatMessageViewSet, basename='chats')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(router.urls)),
    path("login/", LoginAPIView.as_view()),
    path('api/v1/dashboard/', DashboardAPIView.as_view(), name='dashboard'),
    path('api/v1/user-info/', UserInfoView.as_view()),
    path('api/v1/customer/top-sales/', TopSalesCustomersView.as_view(), name='top-sales-customers'),
    path('api/v1/customer/top-orders/', TopOrdersCustomersView.as_view(), name='top-orders-customers'),
]
