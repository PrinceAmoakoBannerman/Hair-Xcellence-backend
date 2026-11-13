from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

WIG = "hd-lace-body-wave-wig"
OPTIONS = {
    "length": '10"', "texture": "Body Wave", "laceType": "Transparent Lace", "laceSize": "4×4 Closure",
    "density": "150%", "colour": "Natural Black", "cap": "Medium", "production": "Standard",
}


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", verbosity=0)

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset rate limits between tests
        self.api = APIClient()

    def register(self, email="ama@example.com", password="Lace-and-Waves-2026", name="Ama Mensah"):
        return self.api.post("/api/auth/register/", {"name": name, "email": email, "password": password}, format="json")

    def signed_in(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        return c

    def order(self, client, email):
        body = {"name": "Ama Mensah", "email": email, "phone": "0241234567", "address": "1 St", "city": "Accra",
                "region": "Greater Accra", "delivery_method": "Accra express", "payment_method": "MTN Mobile Money",
                "items": [{"product": WIG, "options": OPTIONS, "quantity": 1}]}
        res = client.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["number"]

    def test_register_returns_token_and_name(self):
        res = self.register()
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(res.json()["token"])
        self.assertEqual(res.json()["account"]["name"], "Ama Mensah")

    def test_duplicate_email_and_weak_password_rejected(self):
        self.register()
        self.assertEqual(self.register(email="AMA@example.com").status_code, 400)
        weak = self.register(email="new@example.com", password="password")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("password", weak.json())

    def test_login(self):
        self.register()
        ok = self.api.post("/api/auth/login/", {"email": "Ama@Example.com", "password": "Lace-and-Waves-2026"}, format="json")
        self.assertEqual(ok.status_code, 200)
        bad = self.api.post("/api/auth/login/", {"email": "ama@example.com", "password": "wrong-password"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_me_and_update_profile(self):
        me = self.signed_in(self.register().json()["token"])
        self.assertEqual(me.get("/api/auth/me/").json()["email"], "ama@example.com")
        res = me.patch("/api/auth/me/", {"phone": "0241234567", "city": "Kumasi", "name": "Ama K. Mensah"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["city"], "Kumasi")
        self.assertEqual(res.json()["name"], "Ama K. Mensah")
        self.assertEqual(APIClient().get("/api/auth/me/").status_code, 401)

    def test_my_orders_only_shows_own_orders(self):
        ama = self.signed_in(self.register().json()["token"])
        efua = self.signed_in(self.register(email="efua@example.com", name="Efua Owusu").json()["token"])
        mine = self.order(ama, "ama@example.com")
        self.order(efua, "efua@example.com")
        self.order(APIClient(), "ama@example.com")  # guest order with the same email is NOT attached
        numbers = [o["number"] for o in ama.get("/api/auth/orders/").json()]
        self.assertEqual(numbers, [mine])
        # The first signed-in order fills in the account's delivery details.
        self.assertEqual(ama.get("/api/auth/me/").json()["city"], "Accra")

    def test_logout_ends_session(self):
        token = self.register().json()["token"]
        me = self.signed_in(token)
        self.assertEqual(me.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(me.get("/api/auth/me/").status_code, 401)
