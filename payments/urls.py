from django.urls import path

from . import views

urlpatterns = [
    path("payments/config/", views.PaymentConfig.as_view(), name="payment-config"),
    path("payments/start/", views.StartPayment.as_view(), name="payment-start"),
    path("payments/verify/", views.VerifyPayment.as_view(), name="payment-verify"),
    path("payments/webhook/", views.Webhook.as_view(), name="payment-webhook"),
]
