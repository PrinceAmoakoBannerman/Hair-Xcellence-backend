from django.core.cache import cache as store
from django.utils.cache import patch_cache_control
from rest_framework import generics
from rest_framework.response import Response

from . import cache
from .models import Product
from .serializers import ProductSerializer


def _cached(request, cache_key, build):
    data = store.get(cache_key)
    if data is None:
        data = build()
        data = list(data) if isinstance(data, list) else dict(data)  # plain data, without the serializer
        store.set(cache_key, data, cache.TTL)
    response = Response(data)
    # Browsers re-check every time (cheap: unchanged data returns 304 thanks to the ETag),
    # so price changes made in the admin show up straight away.
    patch_cache_control(response, public=True, no_cache=True)
    return response


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

    def list(self, request, *args, **kwargs):
        # Only the two real filters go into the key, so junk query strings can't flood the cache.
        category = request.query_params.get("category", "")[:80]
        kind = request.query_params.get("kind", "")[:20]
        key = cache.key(request, "list", category, kind)
        return _cached(request, key, lambda: super(ProductList, self).list(request, *args, **kwargs).data)


class ProductDetail(generics.RetrieveAPIView):
    """GET /api/products/<slug>/"""

    serializer_class = ProductSerializer
    lookup_field = "slug"
    queryset = Product.objects.filter(is_active=True).prefetch_related("categories", "images")

    def retrieve(self, request, *args, **kwargs):
        key = cache.key(request, "detail", kwargs.get("slug", "")[:120])
        return _cached(request, key, lambda: super(ProductDetail, self).retrieve(request, *args, **kwargs).data)
