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
from django.conf import settings
from django.conf.urls.static import static

from rest_framework.routers import DefaultRouter
from producer.views import (
    ProducerViewSet,
    CustomerViewSet,
    ProductViewSet,
    OrderViewSet,
    SaleViewSet,
    DashboardAPIView,
    UserInfoView,
    TopSalesCustomersView,
    TopOrdersCustomersView,
    StockListView,
    MarketplaceProductViewSet,
)
from market.views import (
    BidViewSet,
    ChatMessageViewSet,
    highest_bidder,
    create_purchase,
    verify_payment,
    payment_confirmation,
    shipping_address_form,
    verify_khalti_payment
)
from user.views import RegisterView, LoginAPIView

router = DefaultRouter()
router.register(r'producers', ProducerViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'products', ProductViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'stocklist', StockListView)
router.register(r'marketplace', MarketplaceProductViewSet)
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
    path('api/v1/bids/highest/<int:product_id>/', highest_bidder, name='highest_bidder'),
    path('api/v1/purchases/', create_purchase, name='create_purchase'),
    path('payment/verify/', verify_payment, name='verify_payment'),
    path('payment/confirmation/<int:payment_id>/', payment_confirmation, name='payment_confirmation'),
    path('shipping/address/<int:payment_id>/', shipping_address_form, name='shipping_address_form'),
    path('khalti/verify/', verify_khalti_payment, name='verify_khalti_payment'),
    path('register/', RegisterView.as_view(), name='register'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
