from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from market.views import (
    BidViewSet,
    CartCreateView,
    CartItemCreateView,
    CartItemDeleteView,
    CartItemUpdateView,
    ChatMessageViewSet,
    DeliveryCreateView,
    FeedbackViewSet,
    GlobalEnumView,
    MarketplaceSaleViewSet,
    MarketplaceUserProductViewSet,
    MarkNotificationAsReadView,
    NotificationListView,
    OrderTrackingEventViewSet,
    ProductFeedbackView,
    SellerProductsView,
    UserBidViewSet,
    UserCartView,
    UserFeedbackView,
    create_purchase,
    log_interaction,
    log_product_view,
    payment_confirmation,
    shipping_address_form,
    verify_khalti_payment,
    verify_payment,
)
from producer.views import (
    AuditLogViewSet,
    CityListView,
    CustomerViewSet,
    DailyProductStatsView,
    DashboardAPIView,
    DirectSaleViewSet,
    KhaltiInitAPIView,
    KhaltiVerifyAPIView,
    LedgerEntryViewSet,
    MarketplaceProductViewSet,
    MarketplaceUserRecommendedProductViewSet,
    OrderViewSet,
    ProducerViewSet,
    ProductViewSet,
    PurchaseOrderViewSet,
    SaleViewSet,
    ShopQRAPIView,
    StatsAPIView,
    StockHistoryViewSet,
    StockListView,
    TopOrdersCustomersView,
    TopSalesCustomersView,
    UserInfoView,
    export_customers_to_excel,
    export_orders_to_excel,
    export_producers_to_excel,
    export_products_to_excel,
    export_sales_to_excel,
    procurement_view,
    reconciliation_view,
    sales_view,
    stats_dashboard,
)

# Import transport views for direct URL patterns
from transport import views as transport_views
from user.views import (
    BusinessRegisterView,
    ChangePasswordView,
    ContactCreateView,
    DeleteAccountView,
    LoginAPIView,
    PhoneLoginView,
    ProfileView,
    RegisterView,
    RequestOTPView,
    TransporterRegistrationAPIView,
    UpdateNotificationPreferencesView,
    UploadProfilePictureView,
    VerifyOTPView,
)

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
router.register(r"purchase-orders", PurchaseOrderViewSet, basename="purchase-orders")
router.register(r"stock-history", StockHistoryViewSet, basename="stockhistory")
router.register(r"direct-sales", DirectSaleViewSet, basename="direct-sale")
router.register(r"marketplace-sales", MarketplaceSaleViewSet, basename="marketplace-sale")
router.register(r"transporters/documents", transport_views.TransporterDocumentViewSet, basename="transporter-document")
router.register(r"order-tracking-events", OrderTrackingEventViewSet, basename="order-tracking-event")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("api/login/", LoginAPIView.as_view()),
    path("api/v1/daily-product-stats/", DailyProductStatsView.as_view(), name="daily-product-stats"),
    path("api/v1/dashboard/", DashboardAPIView.as_view(), name="dashboard"),
    path("api/v1/user-info/", UserInfoView.as_view()),
    path("api/v1/customer/top-sales/", TopSalesCustomersView.as_view(), name="top-sales-customers"),
    path("api/v1/customer/top-orders/", TopOrdersCustomersView.as_view(), name="top-orders-customers"),
    path("api/v1/purchases/", create_purchase, name="create_purchase"),
    path("payment/verify/", verify_payment, name="verify_payment"),
    path("payment/confirmation/<int:payment_id>/", payment_confirmation, name="payment_confirmation"),
    path("shipping/address/<int:payment_id>/", shipping_address_form, name="shipping_address_form"),
    path("khalti/verify/", verify_khalti_payment, name="verify_khalti_payment"),
    path("register/", RegisterView.as_view(), name="register"),
    path("register/business/", BusinessRegisterView.as_view(), name="business-register"),
    path("api/register/user/", RegisterView.as_view(), name="api-user-register"),
    path("api/v1/stats/", StatsAPIView.as_view(), name="stats-api"),
    path("api/v1/notifications/", NotificationListView.as_view(), name="notification-list"),
    path("api/v1/notifications/<int:pk>/mark-read/", MarkNotificationAsReadView.as_view(), name="mark-notification-as-read"),
    path("api/v1/cities/", CityListView.as_view(), name="city-list"),
    path("api/v1/stats-dashboard/", stats_dashboard, name="stats-dashboard"),
    path("api/v1/feedback/product/<int:product_id>/", ProductFeedbackView.as_view(), name="product-feedback"),
    path("api/v1/feedback/user/", UserFeedbackView.as_view(), name="user-feedback"),
    path("api/v1/contact/", ContactCreateView.as_view(), name="contact-create"),
    path("api/v1/global-enums/", GlobalEnumView.as_view(), name="global_enums"),
    # User Profile APIs
    path("api/v1/user-profile/", ProfileView.as_view(), name="user-profile"),
    path("api/v1/user/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("api/v1/user/upload-profile-picture/", UploadProfilePictureView.as_view(), name="upload-profile-picture"),
    path("api/v1/user/notification-preferences/", UpdateNotificationPreferencesView.as_view(), name="notification-preferences"),
    path("api/v1/user/delete-account/", DeleteAccountView.as_view(), name="delete-account"),
    path("api/log-interaction/", log_interaction, name="log_interaction"),
    path("api/v1/procurement/", procurement_view, name="procurement"),
    path("api/v1/sales/", sales_view, name="sales"),
    path("api/v1/reconciliation/", reconciliation_view, name="reconciliation"),
    path("docs/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api-docs/", SpectacularAPIView.as_view(), name="schema"),
    path("api-docs/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/export/producers/", export_producers_to_excel, name="export_producers"),
    path("api/export/customers/", export_customers_to_excel, name="export_customers"),
    path("api/export/products/", export_products_to_excel, name="export_products"),
    path("api/export/orders/", export_orders_to_excel, name="export_orders"),
    path("api/export/sales/", export_sales_to_excel, name="export_sales"),
    path("api/v1/carts/", CartCreateView.as_view(), name="cart-create"),
    path("api/v1/my-cart/", UserCartView.as_view(), name="user-cart"),
    path("api/v1/carts/<int:cart_id>/items/", CartItemCreateView.as_view(), name="cart-item-create"),
    path("api/v1/carts/<int:cart_id>/items/<int:item_id>/", CartItemUpdateView.as_view(), name="cart-item-update"),
    path(
        "api/v1/carts/<int:cart_id>/items/<int:item_id>/delete/",
        CartItemDeleteView.as_view(),
        name="cart-item-delete",
    ),
    path("api/v1/deliveries/", DeliveryCreateView.as_view(), name="delivery-create"),
    path("api/shops/<uuid:shop_id>/qr/", ShopQRAPIView.as_view(), name="shop-qr"),
    path("api/products/<int:pk>/log-view/", log_product_view, name="log-product-view"),
    path("api/payments/khalti/init/", KhaltiInitAPIView.as_view(), name="khalti-init"),
    path("api/payments/khalti/verify/", KhaltiVerifyAPIView.as_view(), name="khalti-verify"),
    path("api/otp/request/", RequestOTPView.as_view(), name="request-otp"),
    path("api/otp/verify/", VerifyOTPView.as_view(), name="verify-otp"),
    path("api/phone-login/", PhoneLoginView.as_view(), name="phone-login"),
    path("api/profile/", transport_views.TransporterProfileView.as_view(), name="transporter-profile"),
    path("api/transporters/", transport_views.TransporterListView.as_view(), name="transporter-list"),
    path(
        "api/transporters/toggle-availability/", transport_views.ToggleAvailabilityView.as_view(), name="toggle-availability"
    ),
    path("api/transporters/update-location/", transport_views.UpdateLocationView.as_view(), name="update-location"),
    path("api/transporters/stats/", transport_views.TransporterStatsView.as_view(), name="transporter-stats"),
    path("api/deliveries/available/", transport_views.AvailableDeliveriesView.as_view(), name="available-deliveries"),
    path("api/deliveries/my/", transport_views.MyDeliveriesView.as_view(), name="my-deliveries"),
    path("api/deliveries/nearby/", transport_views.NearbyDeliveriesView.as_view(), name="nearby-deliveries"),
    path("api/deliveries/history/", transport_views.delivery_history, name="delivery-history"),
    path("api/deliveries/<uuid:delivery_id>/", transport_views.DeliveryDetailView.as_view(), name="delivery-detail"),
    path("api/deliveries/<uuid:delivery_id>/accept/", transport_views.AcceptDeliveryView.as_view(), name="accept-delivery"),
    path(
        "api/deliveries/<uuid:delivery_id>/update-status/",
        transport_views.UpdateDeliveryStatusView.as_view(),
        name="update-delivery-status",
    ),
    path(
        "api/deliveries/<uuid:delivery_id>/tracking/",
        transport_views.DeliveryTrackingView.as_view(),
        name="delivery-tracking",
    ),
    path(
        "api/deliveries/<uuid:delivery_id>/ratings/",
        transport_views.DeliveryRatingListCreateView.as_view(),
        name="delivery-ratings",
    ),
    path("api/admin/deliveries/", transport_views.DeliveryListCreateView.as_view(), name="admin-delivery-list"),
    path(
        "api/admin/deliveries/<uuid:delivery_id>/",
        transport_views.DeliveryUpdateView.as_view(),
        name="admin-delivery-detail",
    ),
    path("api/admin/dashboard/", transport_views.DashboardStatsView.as_view(), name="admin-dashboard"),
    path("api/register/transporter/", TransporterRegistrationAPIView.as_view(), name="api_register_transporter"),
    path("api/auto-assign/", transport_views.AutoAssignmentAPIView.as_view(), name="auto_assign_delivery"),
    path("api/reports/", transport_views.DeliveryReportingAPIView.as_view(), name="delivery_reports"),
    path("api/distance/", transport_views.DistanceCalculationAPIView.as_view(), name="calculate_distance"),
    path(
        "api/deliveries/<uuid:delivery_id>/update-distance/",
        transport_views.DeliveryDistanceUpdateAPIView.as_view(),
        name="update_delivery_distance",
    ),
    path(
        "api/deliveries/<uuid:delivery_id>/optimal-transporters/",
        transport_views.OptimalTransporterAPIView.as_view(),
        name="optimal_transporters",
    ),
    path("api/analytics/delivery-trends/", transport_views.DeliveryAnalyticsAPIView.as_view(), name="delivery_trends"),
    path(
        "api/analytics/transporter-rankings/",
        transport_views.DeliveryAnalyticsAPIView.as_view(),
        name="transporter_rankings",
    ),
    path("api/analytics/efficiency-metrics/", transport_views.DeliveryAnalyticsAPIView.as_view(), name="efficiency_metrics"),
    path("api/deliveries/bulk-operations/", transport_views.BulkDeliveryOperationsAPIView.as_view(), name="bulk_operations"),
    path(
        "api/transporters/<transporter_id>/status/",
        transport_views.UpdateTransporterStatusView.as_view(),
        name="transporter-status-update",
    ),
    path("api/deliveries/suggestions/", transport_views.DeliverySuggestionView.as_view(), name="delivery-suggestions"),
    # path("transporters/documents/", transport_views.TransporterDocumentViewSet.as_view()),
    # Payment URLs
    path("api/v1/payments/", include("payment.urls")),
    # Notification URLs
    path("api/v1/notifications/", include("notification.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
