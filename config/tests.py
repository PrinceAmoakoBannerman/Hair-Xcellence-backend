"""Security behaviour: rate limits, sign-in lockout, token expiry, caching, safe redirects."""
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from catalog.models import Product, validate_photo_size

User = get_user_model()
WIG = "hd-lace-body-wave-wig"
OPTIONS = {
    "length": '10"', "texture": "Body Wave", "laceType": "Transparent Lace", "laceSize": "4×4 Closure",
    "density": "150%", "colour": "Natural Black", "cap": "Medium", "production": "Standard",
}
ORDER = {"name": "Ama Mensah", "email": "ama@example.com", "phone": "0241234567", "address": "1 St", "city": "Accra",
         "region": "Greater Accra", "delivery_method": "Accra express", "payment_method": "MTN Mobile Money",
         "items": [{"product": WIG, "options": OPTIONS, "quantity": 1}]}


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", verbosity=0)

    def setUp(self):
        cache.clear()
        self.api = APIClient()


class RateLimitTests(Base):
    def test_browsing_does_not_use_up_the_order_allowance(self):
        for _ in range(30):
            self.assertEqual(self.api.get("/api/products/").status_code, 200)
        self.assertEqual(self.api.post("/api/orders/", ORDER, format="json").status_code, 201)

    @override_settings(CLIENT_IP_HEADERS=[])
    def test_faked_forwarded_for_header_does_not_dodge_limits(self):
        codes = [self.api.post("/api/auth/login/", {"email": f"x{i}@example.com", "password": "nope"},
                               format="json", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}").status_code for i in range(12)]
        self.assertIn(429, codes)

    @override_settings(CLIENT_IP_HEADERS=["HTTP_TRUE_CLIENT_IP"])
    def test_visitors_are_told_apart_by_cloudflare_ip(self):
        for i in range(10):
            self.api.post("/api/auth/login/", {"email": f"a{i}@example.com", "password": "nope"}, format="json",
                          HTTP_TRUE_CLIENT_IP="1.1.1.1")
        blocked = self.api.post("/api/auth/login/", {"email": "a@example.com", "password": "nope"}, format="json",
                                HTTP_TRUE_CLIENT_IP="1.1.1.1")
        other = self.api.post("/api/auth/login/", {"email": "b@example.com", "password": "nope"}, format="json",
                              HTTP_TRUE_CLIENT_IP="2.2.2.2")
        self.assertEqual(blocked.status_code, 429)
        self.assertNotEqual(other.status_code, 429)

    def test_signed_in_customers_are_rate_limited_too(self):
        user = User.objects.create_user("ama@example.com", "ama@example.com", "a-strong-pass-123")
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
        codes = [self.api.post("/api/orders/", ORDER, format="json").status_code for _ in range(21)]
        self.assertEqual(codes[-1], 429)


class LockoutTests(Base):
    def setUp(self):
        super().setUp()
        self.customer = User.objects.create_user("ama@example.com", "ama@example.com", "a-strong-pass-123")
        self.staff = User.objects.create_superuser("boss", "boss@example.com", "boss-pass-12345")

    def _login(self, password, email="ama@example.com"):
        return self.api.post("/api/auth/login/", {"email": email, "password": password}, format="json")

    def test_customer_locked_after_five_wrong_passwords(self):
        for _ in range(5):
            self.assertEqual(self._login("wrong").status_code, 400)
        res = self._login("a-strong-pass-123")  # even the right password waits now
        self.assertEqual(res.status_code, 429)
        self.assertIn("15 minutes", res.json()["detail"])

    def test_correct_password_works_before_the_limit(self):
        for _ in range(3):
            self._login("wrong")
        self.assertEqual(self._login("a-strong-pass-123").status_code, 200)

    def test_staff_cannot_sign_in_through_the_shop(self):
        self.assertEqual(self._login("boss-pass-12345", email="boss@example.com").status_code, 400)

    def test_admin_locked_after_five_wrong_passwords(self):
        for _ in range(5):
            res = self.client.post("/admin/login/", {"username": "boss", "password": "wrong"})
            self.assertEqual(res.status_code, 200)  # form shown again with an error
        res = self.client.post("/admin/login/", {"username": "boss", "password": "boss-pass-12345"})
        self.assertEqual(res.status_code, 429)

    def test_admin_signs_in_normally(self):
        res = self.client.post("/admin/login/", {"username": "boss", "password": "boss-pass-12345"})
        self.assertEqual(res.status_code, 302)


class TokenExpiryTests(Base):
    def test_expired_token_is_rejected_and_removed(self):
        user = User.objects.create_user("ama@example.com", "ama@example.com", "a-strong-pass-123")
        token = Token.objects.create(user=user)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=31))
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.api.get("/api/auth/me/").status_code, 401)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_signing_in_replaces_an_expired_token(self):
        user = User.objects.create_user("ama@example.com", "ama@example.com", "a-strong-pass-123")
        old = Token.objects.create(user=user)
        Token.objects.filter(pk=old.pk).update(created=timezone.now() - timedelta(days=31))
        res = self.api.post("/api/auth/login/", {"email": "ama@example.com", "password": "a-strong-pass-123"}, format="json")
        self.assertNotEqual(res.json()["token"], old.key)


class CachingTests(Base):
    def test_admin_price_change_shows_immediately(self):
        first = {p["id"]: p["price"] for p in self.api.get("/api/products/").json()}
        product = Product.objects.get(slug=WIG)
        product.base_price = 9999
        product.save()
        second = {p["id"]: p["price"] for p in self.api.get("/api/products/").json()}
        self.assertNotEqual(first[WIG], second[WIG])
        self.assertEqual(float(second[WIG]), 9999)

    def test_unchanged_products_return_304(self):
        res = self.api.get("/api/products/")
        self.assertIn("no-cache", res["Cache-Control"])
        again = self.api.get("/api/products/", HTTP_IF_NONE_MATCH=res["ETag"])
        self.assertEqual(again.status_code, 304)


class MiscTests(TestCase):
    @override_settings(STORE_URL="https://shop.example")
    def test_backend_home_does_not_reveal_admin(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertNotIn("admin", res["Location"])

    def test_oversized_photo_rejected(self):
        with self.assertRaises(ValidationError):
            validate_photo_size(SimpleNamespace(size=11 * 1024 * 1024))
        validate_photo_size(SimpleNamespace(size=3 * 1024 * 1024))  # fine


class ProductionStaticFilesTests(TestCase):
    """Admin pages must render with the production static storage (hashed, compressed files)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import tempfile
        cls.static_root = tempfile.mkdtemp()
        cls.override = override_settings(
            STATIC_ROOT=cls.static_root,
            STORAGES={**settings.STORAGES,
                      "staticfiles": {"BACKEND": "config.storage.StaticStorage"}},
        )
        cls.override.enable()
        call_command("collectstatic", interactive=False, verbosity=0)

    @classmethod
    def tearDownClass(cls):
        import shutil
        cls.override.disable()
        shutil.rmtree(cls.static_root, ignore_errors=True)
        super().tearDownClass()

    def test_admin_pages_render(self):
        call_command("seed_products", verbosity=0)
        self.client.force_login(User.objects.create_superuser("boss", "boss@example.com", "boss-pass-12345"))
        product = Product.objects.first()
        for path in ["/admin/", "/admin/orders/order/", "/admin/orders/payment/", "/admin/orders/customer/",
                     "/admin/catalog/product/", f"/admin/catalog/product/{product.pk}/change/", "/admin/auth/user/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
