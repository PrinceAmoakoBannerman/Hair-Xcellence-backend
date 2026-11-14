import io
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import Category, Product, ProductImage, ProductLength

TMP_MEDIA = tempfile.mkdtemp()
# Store test uploads in a temporary folder, never on Cloudinary.
LOCAL_STORAGE = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}


def photo(name: str) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (100, 29, 50)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TMP_MEDIA, STORAGES=LOCAL_STORAGE)
class AdminPhotoUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        admin = get_user_model().objects.create_superuser("boss", "boss@example.com", "pw-123456")
        self.client.force_login(admin)
        self.cat = Category.objects.create(name="Test Wigs", slug="test-wigs")
        self.product = Product.objects.create(
            slug="test-wig", name="Test Wig", base_price=1000, short="Short", description="Long", detail="HD Lace",
        )

    def _post(self, photos, existing=(), **extra):
        data = {
            "name": self.product.name, "slug": self.product.slug, "kind": "wig", "categories": [self.cat.pk],
            "texture": "Straight", "detail": "HD Lace", "base_price": "1000", "sale": "0", "availability": "In stock",
            "default_colour": "", "tag": "", "short": "Short", "description": "Long", "is_active": "on",
            "sort_order": "0", "popularity": "0",
            "images-TOTAL_FORMS": str(len(existing)), "images-INITIAL_FORMS": str(len(existing)),
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000",
            "lengths-TOTAL_FORMS": "0", "lengths-INITIAL_FORMS": "0", "lengths-MIN_NUM_FORMS": "0", "lengths-MAX_NUM_FORMS": "1000",
            "photos": photos,
        }
        for i, img in enumerate(existing):
            data.update({f"images-{i}-id": img.pk, f"images-{i}-product": self.product.pk,
                         f"images-{i}-url": img.url, f"images-{i}-alt": img.alt, f"images-{i}-sort_order": img.sort_order})
        data.update(extra)
        with self.captureOnCommitCallbacks(execute=True):  # run the file clean-up that happens after saving
            return self.client.post(f"/admin/catalog/product/{self.product.pk}/change/", data, follow=True)

    def test_upload_several_photos_at_once(self):
        res = self._post([photo("a.png"), photo("b.png"), photo("c.png")])
        self.assertEqual(res.status_code, 200)
        imgs = list(self.product.images.all())
        self.assertEqual(len(imgs), 3)
        self.assertEqual([i.sort_order for i in imgs], [0, 1, 2])
        self.assertTrue(all(i.image.name.startswith("products/") for i in imgs))
        self.assertContains(res, "Added 3 photos to Test Wig.")

    def test_new_photos_go_after_existing_ones(self):
        first = ProductImage.objects.create(product=self.product, url="https://example.com/main.jpg", sort_order=4)
        self._post([photo("d.png"), photo("e.png")], existing=[first])
        self.assertEqual([i.sort_order for i in self.product.images.all()], [4, 5, 6])
        self.assertEqual(self.product.images.first().url, "https://example.com/main.jpg")  # main photo unchanged

    def test_rejects_non_images(self):
        bad = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")
        res = self._post([bad])
        self.assertEqual(self.product.images.count(), 0)
        self.assertContains(res, "Upload a valid image")

    def test_no_photos_is_fine(self):
        res = self._post([])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.product.images.count(), 0)

    def test_photos_tab_shows_cards(self):
        ProductImage.objects.create(product=self.product, image=photo("main.png"), sort_order=0)
        res = self.client.get(f"/admin/catalog/product/{self.product.pk}/change/")
        self.assertContains(res, "Main photo")
        self.assertContains(res, "Add photos")
        self.assertContains(res, 'name="images-0-DELETE"')

    def test_remove_photo_deletes_row_and_file(self):
        img = ProductImage.objects.create(product=self.product, image=photo("gone.png"), sort_order=0)
        name, storage = img.image.name, img.image.storage
        self.assertTrue(storage.exists(name))
        self._post([], existing=[img], **{"images-0-DELETE": "on"})
        self.assertFalse(ProductImage.objects.filter(pk=img.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_replace_photo_swaps_file(self):
        img = ProductImage.objects.create(product=self.product, image=photo("old.png"), sort_order=0)
        old, storage = img.image.name, img.image.storage
        self._post([], existing=[img], **{"images-0-image": photo("new.png")})
        img.refresh_from_db()
        self.assertNotEqual(img.image.name, old)
        self.assertTrue(storage.exists(img.image.name))
        self.assertFalse(storage.exists(old))

    def test_remove_some_and_add_others_in_one_save(self):
        a = ProductImage.objects.create(product=self.product, image=photo("a.png"), sort_order=0)
        b = ProductImage.objects.create(product=self.product, image=photo("b.png"), sort_order=1)
        self._post([photo("c.png")], existing=[a, b], **{"images-0-DELETE": "on"})
        self.assertEqual(self.product.images.count(), 2)
        self.assertFalse(ProductImage.objects.filter(pk=a.pk).exists())


class ProductLengthTests(TestCase):
    """Lengths are set per product in the admin; the website and checkout prices follow them."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_products", verbosity=0)

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client.force_login(get_user_model().objects.create_superuser("boss", "b@example.com", "pw-123456"))
        self.wig = Product.objects.get(slug="hd-lace-body-wave-wig")

    def _order(self, length):
        from rest_framework.test import APIClient
        options = {"length": length, "texture": "Body Wave", "laceType": "Transparent Lace", "laceSize": "4×4 Closure",
                   "density": "150%", "colour": "Natural Black", "cap": "Medium", "production": "Standard"}
        body = {"name": "Ama", "email": "ama@example.com", "phone": "0241234567", "address": "1 St", "city": "Accra",
                "region": "Greater Accra", "delivery_method": "Accra express", "payment_method": "MTN Mobile Money",
                "items": [{"product": self.wig.slug, "options": options, "quantity": 1}]}
        return APIClient().post("/api/orders/", body, format="json")

    def test_seeded_products_have_standard_lengths(self):
        self.assertEqual([l.label for l in self.wig.lengths.all()][:3], ['10"', '12"', '14"'])
        self.assertEqual(self.wig.lengths.count(), 12)

    def test_new_length_appears_on_site_and_is_priced_at_checkout(self):
        ProductLength.objects.create(product=self.wig, inches=34, extra_price=2500)
        lengths = {l["label"]: l["price"] for l in self.client.get(f"/api/products/{self.wig.slug}/").json()["lengths"]}
        self.assertEqual(lengths['34"'], 2500)
        res = self._order('34"')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["items"][0]["unit_price"], float(self.wig.base_price) + 2500)

    def test_removed_length_cannot_be_ordered(self):
        self.wig.lengths.filter(inches=32).delete()
        self.assertNotIn('32"', [l["label"] for l in self.client.get(f"/api/products/{self.wig.slug}/").json()["lengths"]])
        self.assertEqual(self._order('32"').status_code, 400)

    def test_price_change_applies(self):
        self.wig.lengths.filter(inches=18).update(extra_price=999)
        from catalog import cache as catalog_cache
        catalog_cache.bump()
        self.assertEqual(self._order('18"').json()["items"][0]["unit_price"], float(self.wig.base_price) + 999)

    def test_admin_lengths_tab_and_defaults_for_new_product(self):
        page = self.client.get(f"/admin/catalog/product/{self.wig.pk}/change/").content.decode()
        self.assertIn('name="lengths-0-inches"', page)
        self.assertIn("Customer pays from", page)
        cat = Category.objects.first()
        data = {"name": "Brand New Wig", "slug": "brand-new-wig", "kind": "wig", "categories": [cat.pk], "texture": "Straight",
                "detail": "HD Lace", "base_price": "1000", "sale": "0", "availability": "In stock", "default_colour": "",
                "tag": "", "short": "S", "description": "D", "is_active": "on", "sort_order": "0", "popularity": "0",
                "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0", "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000",
                "lengths-TOTAL_FORMS": "0", "lengths-INITIAL_FORMS": "0", "lengths-MIN_NUM_FORMS": "0", "lengths-MAX_NUM_FORMS": "1000"}
        self.assertEqual(self.client.post("/admin/catalog/product/add/", data).status_code, 302)
        self.assertEqual(Product.objects.get(slug="brand-new-wig").lengths.count(), 12)  # standard lengths added
