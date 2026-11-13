import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order
from config.security import PaymentThrottle
from orders.serializers import OrderOutSerializer

from . import paystack
from .services import apply_transaction

log = logging.getLogger(__name__)
NOT_SET_UP = "Online payment isn't set up yet. We'll send you payment details on WhatsApp."


class PaymentConfig(APIView):
    """GET /api/payments/config/ — lets the website know whether online payment is switched on."""

    def get(self, request):
        return Response({"online": paystack.is_configured(), "provider": "paystack", "channels": ["mobile_money", "card"]})


class StartSerializer(serializers.Serializer):
    order = serializers.CharField(max_length=20)
    email = serializers.EmailField()


class StartPayment(APIView):
    """
    POST /api/payments/start/  {order, email}
    Creates a Paystack payment for the order's total and returns the page to send the customer to.
    """

    throttle_classes = [PaymentThrottle]

    def post(self, request):
        if not paystack.is_configured():
            return Response({"detail": NOT_SET_UP}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        s = StartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order = Order.objects.filter(number=s.validated_data["order"], email__iexact=s.validated_data["email"]).first()
        if not order:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        if order.payment_status == Order.PaymentStatus.PAID:
            return Response({"detail": "This order is already paid."}, status=status.HTTP_409_CONFLICT)
        if order.status == Order.Status.CANCELLED:
            return Response({"detail": "This order was cancelled."}, status=status.HTTP_409_CONFLICT)

        reference = paystack.new_reference(order.number)
        try:
            data = paystack.initialize(
                email=order.email,
                amount=order.total,
                reference=reference,
                # Fixed return address (from settings, never from the request) so it can't be redirected elsewhere.
                callback_url=f"{settings.STORE_URL.rstrip('/')}/?paystack=1",
                metadata={"order_number": order.number, "customer": order.name},
            )
        except paystack.PaystackError as e:
            log.warning("Paystack initialize failed for %s: %s", order.number, e)
            return Response({"detail": "Payment couldn't be started. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"authorization_url": data["authorization_url"], "reference": data.get("reference", reference)})


class VerifyPayment(APIView):
    """GET /api/payments/verify/?reference=…  — called when the customer returns from Paystack."""

    throttle_classes = [PaymentThrottle]

    def get(self, request):
        if not paystack.is_configured():
            return Response({"detail": NOT_SET_UP}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        reference = (request.query_params.get("reference") or "").strip()
        if not reference or len(reference) > 64:
            return Response({"detail": "Missing payment reference."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            tx = paystack.verify(reference)
        except paystack.PaystackError as e:
            log.warning("Paystack verify failed for %s: %s", reference, e)
            return Response({"detail": "We couldn't confirm this payment yet. Please refresh in a moment."}, status=status.HTTP_502_BAD_GATEWAY)
        order = apply_transaction(tx)
        if not order:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"paystack_status": tx.get("status"), "order": OrderOutSerializer(order, context={"request": request}).data})


@method_decorator(csrf_exempt, name="dispatch")
class Webhook(View):
    """POST /api/payments/webhook/ — Paystack calls this after a payment. Signature-checked."""

    def post(self, request):
        if not paystack.valid_signature(request.body, request.headers.get("X-Paystack-Signature", "")):
            return HttpResponse(status=401)
        try:
            event = json.loads(request.body.decode())
        except ValueError:
            return HttpResponse(status=400)
        if event.get("event") == "charge.success":
            data = event.get("data") or {}
            # Re-check with Paystack rather than trusting the payload alone.
            try:
                apply_transaction(paystack.verify(data.get("reference", "")))
            except paystack.PaystackError as e:
                log.warning("Webhook verify failed: %s", e)
                return HttpResponse(status=502)  # Paystack will retry
        return HttpResponse(status=200)
