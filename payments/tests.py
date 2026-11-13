import hashlib
import hmac
import json
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orders.models import Order

SECRET = "sk_test_unit_tests_only"
WIG = "hd-lace-body-wave-wig"
OPTIONS = {
    "length": '10"', "texture": "Body Wave", "laceType": "Transparent Lace", "laceSize": "4×4 Closure",
    "density": "150%", "colour": "Natural Black", "cap": "Medium", "production": "Standard",
}


def fake_paystack(order: Order, *, status="success", amount=None, channel="mobile_money"):
    """Stand-in for payments.paystack._request: no network calls in tests."""
    def _request(method, path, body=None):
        if path == "/transaction/initialize":
            return {"authorization_url": "https://checkout.paystack.com/test123", "access_code": "x", "reference": body["reference"]}
        if path.startswith("/transaction/verify/"):
            ref = path.rsplit("/", 1)[1]
            return {"status": status, "reference": ref, "amount": amount if amount is not None else int(order.total * 100),
                    "currency": "GHS", "channel": channel, "metadata": {"order_number": order.number}}
        raise AssertionError(path)
    return _request


@override_settings(PAYSTACK_SECRET_KEY=SECRET, STORE_URL="https://shop.example")
class PaystackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", verbosity=0)

    def setUp(self):
        cache.clear()
        self.api = APIClient()
        body = {"name": "Ama Mensah", "email": "ama@example.com", "phone": "0241234567", "address": "1 St", "city": "Accra",
                "region": "Greater Accra", "delivery_method": "Accra express", "payment_method": "MTN Mobile Money",
                "items": [{"product": WIG, "options": OPTIONS, "quantity": 1}]}
        res = self.api.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.order = Order.objects.get(number=res.json()["number"])

    def test_config_flag(self):
        self.assertTrue(self.api.get("/api/payments/config/").json()["online"])
        with override_settings(PAYSTACK_SECRET_KEY=""):
            self.assertFalse(self.api.get("/api/payments/config/").json()["online"])

    def test_not_configured(self):
        with override_settings(PAYSTACK_SECRET_KEY=""):
            res = self.api.post("/api/payments/start/", {"order": self.order.number, "email": "ama@example.com"}, format="json")
        self.assertEqual(res.status_code, 503)

    def test_start_requires_matching_email(self):
        with mock.patch("payments.paystack._request", fake_paystack(self.order)):
            res = self.api.post("/api/payments/start/", {"order": self.order.number, "email": "someone@else.com"}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_start_sends_correct_amount_and_fixed_callback(self):
        calls = []
        real = fake_paystack(self.order)
        def spy(method, path, body=None):
            calls.append(body)
            return real(method, path, body)
        with mock.patch("payments.paystack._request", spy):
            res = self.api.post("/api/payments/start/", {"order": self.order.number, "email": "AMA@example.com"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["authorization_url"].startswith("https://checkout.paystack.com/"))
        sent = calls[0]
        self.assertEqual(sent["amount"], int(self.order.total * 100))  # pesewas
        self.assertEqual(sent["currency"], "GHS")
        self.assertEqual(sent["callback_url"], "https://shop.example/?paystack=1")

    def test_verify_success_marks_paid(self):
        with mock.patch("payments.paystack._request", fake_paystack(self.order)):
            res = self.api.get("/api/payments/verify/", {"reference": f"{self.order.number}-abcd1234"})
        self.assertEqual(res.status_code, 200, res.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(self.order.payment_channel, "mobile_money")
        self.assertEqual(res.json()["order"]["payment_status"], "paid")

    def test_wrong_amount_is_not_marked_paid(self):
        with mock.patch("payments.paystack._request", fake_paystack(self.order, amount=100)):
            self.api.get("/api/payments/verify/", {"reference": f"{self.order.number}-abcd1234"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")
        self.assertIn("Check before shipping", self.order.note)

    def test_failed_payment(self):
        with mock.patch("payments.paystack._request", fake_paystack(self.order, status="failed")):
            self.api.get("/api/payments/verify/", {"reference": f"{self.order.number}-abcd1234"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed")

    def _webhook(self, payload: dict, signature: str | None = None):
        raw = json.dumps(payload).encode()
        sig = signature if signature is not None else hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()
        return self.client.post("/api/payments/webhook/", data=raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sig)

    def test_webhook_rejects_bad_signature(self):
        res = self._webhook({"event": "charge.success", "data": {"reference": "x"}}, signature="forged")
        self.assertEqual(res.status_code, 401)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")

    def test_webhook_marks_paid_and_is_idempotent(self):
        payload = {"event": "charge.success", "data": {"reference": f"{self.order.number}-abcd1234"}}
        with mock.patch("payments.paystack._request", fake_paystack(self.order, channel="card")):
            self.assertEqual(self._webhook(payload).status_code, 200)
            first_paid_at = Order.objects.get(pk=self.order.pk).paid_at
            self.assertEqual(self._webhook(payload).status_code, 200)  # Paystack may resend
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(self.order.payment_channel, "card")
        self.assertEqual(self.order.paid_at, first_paid_at)

    def test_abandoned_payment_stays_pending(self):
        with mock.patch("payments.paystack._request", fake_paystack(self.order, status="abandoned")):
            res = self.api.get("/api/payments/verify/", {"reference": f"{self.order.number}-abcd1234"})
        self.assertEqual(res.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")
