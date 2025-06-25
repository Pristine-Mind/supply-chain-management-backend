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
    StatsAPIView,
    CityListView,
    withdraw_product,
    MarketplaceUserRecommendedProductViewSet,
    export_producers_to_excel,
    export_customers_to_excel,
    export_products_to_excel,
    export_sales_to_excel,
    export_orders_to_excel,
    LedgerEntryViewSet,
    AuditLogViewSet,
    procurement_view,
    sales_view,
    reconciliation_view,
    stats_dashboard,
)
from market.views import (
    BidViewSet,
    ChatMessageViewSet,
    highest_bidder,
    create_purchase,
    verify_payment,
    payment_confirmation,
    shipping_address_form,
    verify_khalti_payment,
    MarketplaceUserProductViewSet,
    ProductBidsView,
    UserBidViewSet,
    UserBidsForProductView,
    SellerProductsView,
    NotificationListView,
    MarkNotificationAsReadView,
    WithdrawBidView,
    GlobalEnumView,
    log_interaction,
    FeedbackViewSet,
    ProductFeedbackView,
    UserFeedbackView,
    DeliveryCreateView,
    CartCreateView,
    CartItemCreateView,
    CartItemUpdateView,
    CartItemDeleteView
)
from user.views import (
    RegisterView,
    LoginAPIView,
    # PretrainedChatbotAPIView,
    ContactCreateView,
)
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

router = DefaultRouter()
router.register(r"producers", ProducerViewSet)
router.register(r"customers", CustomerViewSet)
router.register(r"products", ProductViewSet)
router.register(r"orders", OrderViewSet)
router.register(r"sales", SaleViewSet)
router.register(r"stocklist", StockListView)
router.register(r"marketplace", MarketplaceProductViewSet, basename="marketplace")
router.register(r"marketplace-user-products", MarketplaceUserProductViewSet, basename="marketplace-user-products")
router.register(r"bids", BidViewSet, basename="bids")
router.register(r"chats", ChatMessageViewSet, basename="chats")
router.register(r"user-bids", UserBidViewSet, basename="user-bids")
router.register(r"user-recommendation", MarketplaceUserRecommendedProductViewSet, basename="user-recommendation")
router.register(r"ledger-entries", LedgerEntryViewSet, basename="ledger-entry")
router.register(r"audit-logs", AuditLogViewSet, basename="audit-log")
router.register(r"feedback", FeedbackViewSet, basename="feedback")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("login/", LoginAPIView.as_view()),
    path("api/v1/dashboard/", DashboardAPIView.as_view(), name="dashboard"),
    path("api/v1/user-info/", UserInfoView.as_view()),
    path("api/v1/customer/top-sales/", TopSalesCustomersView.as_view(), name="top-sales-customers"),
    path("api/v1/customer/top-orders/", TopOrdersCustomersView.as_view(), name="top-orders-customers"),
    path("api/v1/bids/highest/<int:product_id>/", highest_bidder, name="highest_bidder"),
    path("api/v1/purchases/", create_purchase, name="create_purchase"),
    path("payment/verify/", verify_payment, name="verify_payment"),
    path("payment/confirmation/<int:payment_id>/", payment_confirmation, name="payment_confirmation"),
    path("shipping/address/<int:payment_id>/", shipping_address_form, name="shipping_address_form"),
    path("khalti/verify/", verify_khalti_payment, name="verify_khalti_payment"),
    path("register/", RegisterView.as_view(), name="register"),
    path("api/v1/stats/", StatsAPIView.as_view(), name="stats-api"),
    path("api/v1/bids/product/<int:product_id>/", ProductBidsView.as_view(), name="product-bids"),
    path("api/v1/bids/user/<int:product_id>/", UserBidsForProductView.as_view(), name="user-bids-for-product"),
    path("api/v1/seller/", SellerProductsView.as_view(), name="seller-products"),
    path("api/v1/notifications/", NotificationListView.as_view(), name="notification-list"),
    path("api/v1/notifications/<int:pk>/mark-read/", MarkNotificationAsReadView.as_view(), name="mark-notification-as-read"),
    path("api/v1/cities/", CityListView.as_view(), name="city-list"),
    path("api/v1/seller/<int:product_id>/withdraw/", withdraw_product, name="withdraw_product"),
    path("api/v1/bids/<int:bid_id>/withdraw/", WithdrawBidView.as_view(), name="withdraw-bid"),
    path("api/v1/stats-dashboard/", stats_dashboard, name="stats-dashboard"),
    path("api/v1/feedback/product/<int:product_id>/", ProductFeedbackView.as_view(), name="product-feedback"),
    path("api/v1/feedback/user/", UserFeedbackView.as_view(), name="user-feedback"),
    # path("api/v1/pretrained-chatbot/", PretrainedChatbotAPIView.as_view(), name="pretrained-chatbot"),
    path("api/v1/contact/", ContactCreateView.as_view(), name="contact-create"),
    path("api/v1/global-enums/", GlobalEnumView.as_view(), name="global_enums"),
    path("api/log-interaction/", log_interaction, name="log_interaction"),
    path("api/v1/procurement/", procurement_view, name="procurement"),
    path("api/v1/sales/", sales_view, name="sales"),
    path("api/v1/reconciliation/", reconciliation_view, name="reconciliation"),
    # Docs
    path("docs/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api-docs/", SpectacularAPIView.as_view(), name="schema"),
    path("api-docs/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # export
    path("export/producers/", export_producers_to_excel, name="export_producers"),
    path("export/customers/", export_customers_to_excel, name="export_customers"),
    path("export/products/", export_products_to_excel, name="export_products"),
    path("export/orders/", export_orders_to_excel, name="export_orders"),
    path("export/sales/", export_sales_to_excel, name="export_sales"),
    path("api/v1/carts/", CartCreateView.as_view(), name="cart-create"),
    path("api/v1/carts/<int:cart_id>/items/", CartItemCreateView.as_view(), name="cart-item-create"),
    path("api/v1/carts/<int:cart_id>/items/<int:item_id>/", CartItemUpdateView.as_view(), name="cart-item-update"),
    path("api/v1/carts/<int:cart_id>/items/<int:item_id>/", CartItemDeleteView.as_view(), name="cart-item-delete"),
    path("api/v1/deliveries/", DeliveryCreateView.as_view(), name="delivery-create"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
