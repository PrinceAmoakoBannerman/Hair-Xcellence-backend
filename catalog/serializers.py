from rest_framework import serializers

from .models import Product
from .pricing import length_prices


class ProductSerializer(serializers.ModelSerializer):
    """Shaped like the frontend's Product type in frontend/src/data.ts."""

    id = serializers.CharField(source="slug")
    categories = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    price = serializers.DecimalField(source="base_price", max_digits=10, decimal_places=2, coerce_to_string=False)
    sale = serializers.DecimalField(max_digits=4, decimal_places=2, coerce_to_string=False)
    image = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    isNew = serializers.BooleanField(source="is_new")
    isBest = serializers.BooleanField(source="is_bestseller")
    colour = serializers.CharField(source="default_colour")
    lengths = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "kind", "categories", "texture", "price", "sale", "availability",
            "isNew", "isBest", "tag", "image", "gallery", "short", "description", "detail", "colour", "popularity",
            "lengths",
        ]

    def get_lengths(self, obj):
        """Lengths offered (set in the admin), each with what it adds to the base price."""
        return [{"label": label, "price": float(price)} for label, price in length_prices(obj).items()]

    def _abs(self, src: str) -> str:
        """Full URL so the website (on another domain) can load the photo."""
        if not src or src.startswith(("http://", "https://")):
            return src
        if src.startswith("/images/"):  # legacy path from the website's own public folder
            return src
        request = self.context.get("request")
        return request.build_absolute_uri(src) if request else src

    def get_gallery(self, obj) -> list[str]:
        return [self._abs(img.src) for img in obj.images.all()]

    def get_image(self, obj) -> str:
        first = obj.images.first()
        return self._abs(first.src) if first else ""
