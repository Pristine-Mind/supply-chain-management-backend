from django.urls import path

from . import views

app_name = "payment"

urlpatterns = [
    path("gateways/", views.PaymentGatewayListView.as_view(), name="payment_gateways"),
    path("initiate/", views.initiate_payment, name="initiate_payment"),
    path("callback/", views.payment_callback, name="payment_callback"),
    path("status/<str:transaction_id>/", views.payment_status, name="payment_status"),
    path("webhook/", views.PaymentWebhookView.as_view(), name="payment_webhook"),
]
