from django.contrib import admin
from django.utils.html import format_html

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "summary", "unit_price", "quantity", "line_total")
    readonly_fields = ("product_name", "summary", "unit_price", "quantity", "line_total")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "created_at", "name", "phone", "total", "status", "payment_badge", "rush")
    list_filter = ("status", "payment_status", "delivery_method", "payment_method", "region", "created_at")
    list_editable = ("status",)
    search_fields = ("number", "name", "email", "phone")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    readonly_fields = ("number", "created_at", "updated_at", "subtotal", "delivery_fee", "total")
    fieldsets = (
        ("Order", {"fields": ("number", "status", "created_at", "updated_at", "note")}),
        ("Customer", {"fields": ("name", "email", "phone", "address", "city", "region")}),
        ("Delivery & payment", {"fields": ("delivery_method", "delivery_fee", "payment_method", "payment_status", "payment_reference")}),
        ("Totals", {"fields": ("subtotal", "total")}),
    )

    @admin.display(description="Production")
    def rush(self, obj):
        return obj.rush_production or "Standard"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return format_html('<span class="hx-pill {}">{}</span>', obj.status, obj.get_status_display())

    @admin.display(description="Payment", ordering="payment_status")
    def payment_badge(self, obj):
        return format_html('<span class="hx-pill {}">{}</span>', obj.payment_status, obj.get_payment_status_display())
