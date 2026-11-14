from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    class Kind(models.TextChoices):
        WIG = "wig", "Wig"
        BUNDLE = "bundle", "Bundle"
        CLOSURE = "closure", "Closure / frontal"

    class Texture(models.TextChoices):
        STRAIGHT = "Straight"
        BODY_WAVE = "Body Wave"
        DEEP_WAVE = "Deep Wave"
        LOOSE_WAVE = "Loose Wave"
        CURLY = "Curly"

    class Availability(models.TextChoices):
        IN_STOCK = "In stock"
        LOW_STOCK = "Low stock"
        MADE_TO_ORDER = "Made to order"
        SOLD_OUT = "Sold out"

    slug = models.SlugField(max_length=120, unique=True, help_text="Used in the product's web address.")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.WIG)
    categories = models.ManyToManyField(Category, related_name="products", blank=True)
    texture = models.CharField(max_length=20, choices=Texture.choices, default=Texture.STRAIGHT)
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Starting price in GH₵, shown on the website as \"from GH₵ …\" (10\" length, cheapest options). Options chosen by the customer add to this.",
    )
    sale = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0"),
        help_text="Discount as a fraction, e.g. 0.30 = 30% off. 0 = not on sale.",
    )
    availability = models.CharField(max_length=20, choices=Availability.choices, default=Availability.IN_STOCK)
    default_colour = models.CharField(max_length=40, blank=True, help_text="Colour pre-selected on the product page.")
    tag = models.CharField(max_length=30, blank=True, help_text="Small label on the product card, e.g. Bestseller, New, Sale.")
    short = models.CharField("short description", max_length=200)
    description = models.TextField()
    detail = models.CharField("spec line", max_length=120, help_text="e.g. HD Lace · Frontal · Body Wave")
    is_new = models.BooleanField(default=False)
    is_bestseller = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, help_text="Untick to hide the product from the shop.")
    sort_order = models.PositiveIntegerField(default=0)
    popularity = models.PositiveIntegerField(default=0, help_text="Used for the 'Best selling' sort.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


def validate_photo_size(file):
    """Keep uploads reasonable (phone photos are 2–6 MB)."""
    limit = settings.MAX_PHOTO_MB * 1024 * 1024
    if file and getattr(file, "size", 0) > limit:
        raise ValidationError(f"This photo is larger than {settings.MAX_PHOTO_MB} MB. Please use a smaller one.")


class ProductLength(models.Model):
    """A hair length the product is offered in, and what it adds to the base price."""

    product = models.ForeignKey(Product, related_name="lengths", on_delete=models.CASCADE)
    inches = models.PositiveSmallIntegerField(validators=[MinValueValidator(4), MaxValueValidator(60)])
    extra_price = models.DecimalField(
        "extra price (GH₵)", max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Added to the base price. Usually 0 for the shortest length.",
    )

    class Meta:
        ordering = ["inches"]
        constraints = [models.UniqueConstraint(fields=["product", "inches"], name="unique_length_per_product")]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        return f'{self.inches}"'


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/", blank=True, validators=[validate_photo_size], help_text="Upload a photo (recommended, up to 10 MB).")
    url = models.CharField(
        max_length=500, blank=True,
        help_text="…or paste an image link instead of uploading.",
    )
    alt = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower numbers show first. The first photo is the main one.")

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.src or "Image"

    @property
    def src(self) -> str:
        """Uploaded file URL if there is one, otherwise the pasted link."""
        if self.image:
            return self.image.url
        return self.url

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.image and not self.url:
            raise ValidationError("Upload a photo or paste an image link.")
