import io
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import Category, Product, ProductImage

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
