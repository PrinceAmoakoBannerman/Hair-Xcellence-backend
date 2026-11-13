from django.conf import settings
from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product, ProductImage


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
    model = ProductImage
    extra = 1
    fields = ("preview", "image", "url", "alt", "sort_order")
    readonly_fields = ("preview",)

    @admin.display(description="Preview")
    def preview(self, obj):
        if not obj.src:
            return "—"
        return format_html('<img src="{}" style="height:72px;width:58px;object-fit:cover;border-radius:4px" alt="">', image_src(obj.src))


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("thumb", "name", "kind", "base_price", "sale", "availability", "is_bestseller", "is_new", "is_active")
    list_display_links = ("thumb", "name")
    list_filter = ("kind", "availability", "is_active", "is_bestseller", "is_new", "categories")
    list_editable = ("base_price", "availability", "is_active")
    search_fields = ("name", "slug", "detail")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "kind", "categories", "texture", "detail")}),
        ("Price & stock", {"fields": ("base_price", "sale", "availability", "default_colour")}),
        ("Display", {"fields": ("tag", "short", "description", "is_new", "is_bestseller", "is_active", "sort_order", "popularity")}),
    )

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
