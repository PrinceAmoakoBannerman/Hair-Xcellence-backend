import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Category, Product, ProductImage

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "products.json"
CATEGORY_ORDER = [
    "HD Lace Wigs", "Closure Wigs", "Frontal Wigs", "Glueless Wigs", "Straight Hair",
    "Body Wave", "Deep Wave", "Curly Hair", "Hair Bundles", "Closures and Frontals",
]


def backend_path(url: str) -> str:
    """/images/x.webp (website public folder) -> /static/catalog/products/x.webp (served by this backend)."""
    return url.replace("/images/", "/static/catalog/products/", 1) if url.startswith("/images/") else url


class Command(BaseCommand):
    help = "Load (or update) the starter product catalogue from catalog/fixtures/products.json."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(FIXTURE), help="Path to a products JSON file.")

    @transaction.atomic
    def handle(self, *args, **opts):
        items = json.loads(Path(opts["file"]).read_text(encoding="utf-8"))
        created = updated = 0
        for row in items:
            product, is_new = Product.objects.update_or_create(
                slug=row["slug"],
                defaults={
                    "name": row["name"],
                    "kind": row["kind"],
                    "texture": row["texture"],
                    "base_price": Decimal(str(row["base_price"])),
                    "sale": Decimal(str(row.get("sale") or 0)),
                    "availability": row["availability"],
                    "default_colour": row.get("default_colour", ""),
                    "tag": row.get("tag", ""),
                    "short": row["short"],
                    "description": row["description"],
                    "detail": row["detail"],
                    "is_new": row.get("is_new", False),
                    "is_bestseller": row.get("is_bestseller", False),
                    "sort_order": row.get("sort_order", 0),
                    "popularity": row.get("popularity", 0),
                },
            )
            cats = []
            for name in row.get("categories", []):
                order = CATEGORY_ORDER.index(name) if name in CATEGORY_ORDER else 99
                cat, _ = Category.objects.get_or_create(name=name, defaults={"slug": slugify(name), "sort_order": order})
                cats.append(cat)
            product.categories.set(cats)
            product.images.all().delete()
            ProductImage.objects.bulk_create([
                ProductImage(product=product, url=backend_path(url), alt=product.name, sort_order=i)
                for i, url in enumerate(row.get("images", []))
            ])
            created += is_new
            updated += not is_new
        self.stdout.write(self.style.SUCCESS(f"Products: {created} created, {updated} updated."))
