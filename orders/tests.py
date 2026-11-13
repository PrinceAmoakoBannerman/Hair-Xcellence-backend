from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from orders.models import Order

WIG = "hd-lace-body-wave-wig"
DEFAULT_WIG_OPTIONS = {
    "length": '10"', "texture": "Body Wave", "laceType": "Transparent Lace", "laceSize": "4×4 Closure",
    "density": "150%", "colour": "Natural Black", "cap": "Medium", "production": "Standard",
}
CUSTOMER = {
    "name": "Ama Mensah", "email": "ama@example.com", "phone": "024 123 4567",
    "address": "12 Lagos Avenue", "city": "Accra", "region": "Greater Accra",
    "delivery_method": "Accra express", "payment_method": "MTN Mobile Money",
}


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", verbosity=0)

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset rate limits between tests
        self.api = APIClient()

    def test_health(self):
        self.assertEqual(self.api.get("/api/health/").json(), {"status": "ok"})

    def test_product_list_and_filters(self):
        all_products = self.api.get("/api/products/").json()
        self.assertEqual(len(all_products), 12)
        wigs = self.api.get("/api/products/", {"kind": "wig"}).json()
        self.assertTrue(wigs and all(p["kind"] == "wig" for p in wigs))
        glueless = self.api.get("/api/products/", {"category": "Glueless Wigs"}).json()
        self.assertTrue(glueless and all("Glueless Wigs" in p["categories"] for p in glueless))

    def test_product_detail_shape(self):
        p = self.api.get(f"/api/products/{WIG}/").json()
        self.assertEqual(p["id"], WIG)
        self.assertEqual(p["price"], 2450)
        self.assertTrue(p["image"] and p["gallery"])
        # Photos are full URLs served by the backend, so the website can load them from another domain.
        self.assertTrue(p["image"].startswith("http://testserver/static/catalog/products/"), p["image"])
        self.assertEqual(self.api.get("/api/products/does-not-exist/").status_code, 404)

    def test_order_is_priced_on_the_server(self):
        options = {**DEFAULT_WIG_OPTIONS, "length": '18"', "laceType": "HD Lace", "production": "Express"}
        body = {**CUSTOMER, "items": [
            {"product": WIG, "options": options, "addons": ["Baby hair"], "quantity": 2, "unit_price": 1},  # unit_price ignored
        ]}
        res = self.api.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        # 2450 base + 18" (4 × 180) + HD lace 350 + express 400 + baby hair 100 = 4020 each
        self.assertEqual(data["items"][0]["unit_price"], 4020)
        self.assertEqual(data["subtotal"], 8040)
        self.assertEqual(data["delivery_fee"], 60)
        self.assertEqual(data["total"], 8100)
        order = Order.objects.get(number=data["number"])
        self.assertEqual(order.total, Decimal("8100"))
        self.assertEqual(order.rush_production, "Express")

    def test_invalid_option_is_rejected(self):
        body = {**CUSTOMER, "items": [{"product": WIG, "options": {**DEFAULT_WIG_OPTIONS, "colour": "Neon Green"}, "quantity": 1}]}
        res = self.api.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("items", res.json())
        self.assertEqual(Order.objects.count(), 0)

    def test_missing_customer_details_rejected(self):
        res = self.api.post("/api/orders/", {"items": []}, format="json")
        self.assertEqual(res.status_code, 400)
        for field in ("name", "email", "phone", "address", "city", "items"):
            self.assertIn(field, res.json())

    def test_bundle_cannot_have_addons(self):
        body = {**CUSTOMER, "items": [{
            "product": "body-wave-hair-bundles",
            "options": {"length": '10"', "texture": "Body Wave", "colour": "Natural Black"},
            "addons": ["Baby hair"], "quantity": 1,
        }]}
        self.assertEqual(self.api.post("/api/orders/", body, format="json").status_code, 400)


class AdminFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", verbosity=0)
        from django.contrib.auth import get_user_model
        cls.admin_user = get_user_model().objects.create_superuser("boss", "boss@example.com", "x-test-pass-123")

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset rate limits between tests
        self.api = APIClient()

    def _order(self, phone="024 123 4567", qty=1, production="Standard"):
        body = {**CUSTOMER, "phone": phone, "items": [
            {"product": WIG, "options": {**DEFAULT_WIG_OPTIONS, "production": production}, "quantity": qty},
        ]}
        res = self.api.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        return Order.objects.get(number=res.json()["number"])

    def test_customer_created_and_matched_across_phone_formats(self):
        from orders.models import Customer
        first = self._order(phone="024 123 4567")
        second = self._order(phone="+233 24 123 4567")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(first.customer_id, second.customer_id)
        self.assertEqual(first.customer.orders.count(), 2)

    def test_paid_at_follows_payment_status(self):
        order = self._order()
        self.assertIsNone(order.paid_at)
        order.payment_status = Order.PaymentStatus.PAID
        order.save()
        self.assertIsNotNone(order.paid_at)
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save()
        self.assertIsNone(order.paid_at)

    def test_admin_pages_render(self):
        rushed = self._order(production="Priority")
        rushed.payment_status = Order.PaymentStatus.PAID
        rushed.save()
        self._order()
        self.client.force_login(self.admin_user)
        for url in ["/admin/", "/admin/orders/order/", "/admin/orders/order/?production=rushed",
                    "/admin/orders/payment/", "/admin/orders/customer/", f"/admin/orders/order/{rushed.pk}/change/"]:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, url)
        dash = self.client.get("/admin/").content.decode()
        self.assertIn("Store overview", dash)
        self.assertIn(rushed.number, dash)  # appears in recent + rush lists
        self.assertIn("Awaiting payment", self.client.get("/admin/orders/payment/").content.decode())
