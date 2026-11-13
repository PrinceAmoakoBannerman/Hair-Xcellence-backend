"""
Product API cache. Responses are kept for 10 minutes and thrown away the moment anything in the
catalogue changes in the admin (product, photo or category), so the website never shows stale prices.
"""
import hashlib

from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save

VERSION_KEY = "catalog:version"
TTL = 10 * 60


def version() -> int:
    return cache.get_or_set(VERSION_KEY, 1, None)


def key(request, *parts) -> str:
    # Image links are absolute, so the host is part of the key. Hashed: keys stay short and safe.
    raw = "|".join([request.get_host(), *[str(p) for p in parts]])
    return f"catalog:{version()}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def bump(*_args, **_kwargs) -> None:
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 2, None)


def connect() -> None:
    from .models import Category, Product, ProductImage
    for model in (Product, ProductImage, Category):
        post_save.connect(bump, sender=model, dispatch_uid=f"catalog-cache-save-{model.__name__}")
        post_delete.connect(bump, sender=model, dispatch_uid=f"catalog-cache-delete-{model.__name__}")
    m2m_changed.connect(bump, sender=Product.categories.through, dispatch_uid="catalog-cache-m2m")
