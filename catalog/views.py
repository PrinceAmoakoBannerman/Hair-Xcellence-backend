from rest_framework import generics

from .models import Product
from .serializers import ProductSerializer


class ProductList(generics.ListAPIView):
    """GET /api/products/?category=Glueless%20Wigs&kind=wig"""

    serializer_class = ProductSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).prefetch_related("categories", "images")
        category = self.request.query_params.get("category")
        kind = self.request.query_params.get("kind")
        if category:
            qs = qs.filter(categories__name=category)
        if kind:
            qs = qs.filter(kind=kind)
        return qs.distinct()


class ProductDetail(generics.RetrieveAPIView):
    """GET /api/products/<slug>/"""

    serializer_class = ProductSerializer
    lookup_field = "slug"
    queryset = Product.objects.filter(is_active=True).prefetch_related("categories", "images")
