from django.conf import settings
from django import forms
from django.contrib import admin, messages
from django.db.models import Max
from django.utils.html import format_html

from .models import Category, Product, ProductImage, ProductLength, validate_photo_size
from . import cache as catalog_cache
from .pricing import standard_lengths


def image_src(src: str) -> str:
    """Old /images/... paths live on the website; everything else is served by this backend or is a full URL."""
    if src.startswith("/images/"):
        return f"{settings.STORE_URL.rstrip('/')}{src}"
    return src


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order")
    list_editable = ("sort_order",)
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    """Photos shown as cards (templates/admin/catalog/product/photos_inline.html)."""

    model = ProductImage
    template = "admin/catalog/product/photos_inline.html"
    verbose_name_plural = "Photos"
    extra = 0  # new photos come in through "Add photos" (several at once)
    fields = ("image", "url", "alt", "sort_order")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "image":
            # Plain file picker: "Replace" swaps the photo, "Remove" deletes the whole card.
            kwargs["widget"] = forms.FileInput(attrs={"accept": "image/*"})
        if db_field.name == "url":
            kwargs["widget"] = forms.TextInput(attrs={"placeholder": "https://…"})
        if db_field.name == "alt":
            kwargs["widget"] = forms.TextInput(attrs={"placeholder": "e.g. Front view"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class ProductLengthInline(admin.TabularInline):
    """Lengths the product is offered in. Add a row for a new length, delete a row to stop offering it."""

    model = ProductLength
    verbose_name = "length"
    verbose_name_plural = "Lengths"
    extra = 1
    fields = ("inches", "extra_price", "customer_pays")
    readonly_fields = ("customer_pays",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "inches":
            kwargs["widget"] = forms.NumberInput(attrs={"min": 4, "max": 60, "step": 1, "placeholder": "e.g. 34", "class": "hx-num"})
        if db_field.name == "extra_price":
            kwargs["widget"] = forms.NumberInput(attrs={"min": 0, "step": 10, "placeholder": "0", "class": "hx-num"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Customer pays from")
    def customer_pays(self, obj):
        if not obj or not obj.pk:
            return "—"
        total = obj.product.base_price + obj.extra_price
        return f"GH₵ {total:,.0f}"


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """Pick several photos at once; each one is checked as an image."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = [super(MultipleImageField, self).clean(f, initial) for f in files]
        for f in cleaned:
            validate_photo_size(f)
        return cleaned


class ProductForm(forms.ModelForm):
    photos = MultipleImageField(
        required=False, label="Add photos",
        help_text="Select several photos at once (hold Ctrl, or Cmd on a Mac). They are added in the order chosen, "
                  "after any photos the product already has. Reorder or delete them under Product images below.",
    )

    class Meta:
        model = Product
        fields = "__all__"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductForm
    # Tabs: the photos (with "Add photos") sit right after price, in one place.
    jazzmin_section_order = ("General", "Price & stock", "Lengths", "Photos", "Display")
    list_display = ("thumb", "name", "kind", "base_price", "sale", "availability", "is_bestseller", "is_new", "is_active")
    list_display_links = ("thumb", "name")
    list_filter = ("kind", "availability", "is_active", "is_bestseller", "is_new", "categories")
    list_editable = ("base_price", "availability", "is_active")
    search_fields = ("name", "slug", "detail")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductLengthInline, ProductImageInline]
    fieldsets = (
        ("General", {"fields": ("name", "slug", "kind", "categories", "texture", "detail")}),
        ("Price & stock", {"fields": ("base_price", "sale", "availability", "default_colour")}),
        ("Display", {"fields": ("tag", "short", "description", "is_new", "is_bestseller", "is_active", "sort_order", "popularity")}),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        if not product.lengths.exists():
            # Nothing entered: offer the standard lengths so the product can be bought straight away.
            ProductLength.objects.bulk_create([
                ProductLength(product=product, inches=inches, extra_price=price)
                for inches, price in standard_lengths(product.kind)
            ])
            catalog_cache.bump()
        files = form.cleaned_data.get("photos") or []
        if not files:
            return
        product = form.instance
        start = (product.images.aggregate(m=Max("sort_order"))["m"] or 0) + (1 if product.images.exists() else 0)
        for i, f in enumerate(files):
            ProductImage.objects.create(product=product, image=f, alt=product.name, sort_order=start + i)
        messages.success(request, f"Added {len(files)} photo{'s' if len(files) != 1 else ''} to {product.name}.")

    @admin.display(description="")
    def thumb(self, obj):
        first = obj.images.first()
        if not first:
            return "—"
        return format_html('<img class="hx-thumb" src="{}" alt="">', image_src(first.src))

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("images")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "categories":
            kwargs["widget"] = forms.CheckboxSelectMultiple
        return super().formfield_for_manytomany(db_field, request, **kwargs)
