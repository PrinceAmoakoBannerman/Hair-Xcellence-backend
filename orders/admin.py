from urllib.parse import quote

from django.contrib import admin, messages
from django.db.models import Count, Max, Q, Sum
from django.urls import reverse
from django.utils.html import format_html

from catalog.admin import image_src

from .models import Customer, Order, OrderItem, Payment, normalise_phone


def ghs(amount) -> str:
    return f"GH₵ {amount:,.0f}" if amount == int(amount) else f"GH₵ {amount:,.2f}"


def pill(value: str, label: str):
    return format_html('<span class="hx-pill {}">{}</span>', value, label)


def contact_buttons(name: str, phone: str, number: str = ""):
    key = normalise_phone(phone)
    text = quote(f"Hi {name.split()[0] if name else ''}, this is Hair Xcellence about your order {number}.".replace("  ", " "))
    return format_html(
        '<a class="hx-btn wa" href="https://wa.me/{}?text={}" target="_blank" rel="noopener">WhatsApp</a> '
        '<a class="hx-btn" href="tel:+{}">Call</a>',
        key, text, key,
    )


# ── Orders ─────────────────────────────────────────────────────────────

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("photo", "product_name", "summary", "unit_price", "quantity", "line_total")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="")
    def photo(self, obj):
        first = obj.product.images.first() if obj.product else None
        if not first:
            return "—"
        return format_html('<img class="hx-thumb" src="{}" alt="">', image_src(first.src))


def _set_status(status: str, label: str):
    def action(modeladmin, request, queryset):
        n = 0
        for order in queryset:
            order.status = status
            order.save(update_fields=["status", "updated_at"])
            n += 1
        modeladmin.message_user(request, f"{n} order(s) marked as {label}.", messages.SUCCESS)
    action.short_description = f"Mark as {label}"
    action.__name__ = f"mark_{status}"
    return action


def _set_payment(status: str, label: str):
    def action(modeladmin, request, queryset):
        n = 0
        for order in queryset:
            order.payment_status = status
            order.save()  # save() keeps paid_at in sync
            n += 1
        modeladmin.message_user(request, f"{n} order(s) marked as {label}.", messages.SUCCESS)
    action.short_description = f"Payment: mark as {label}"
    action.__name__ = f"payment_{status}"
    return action


ORDER_ACTIONS = [
    _set_status(Order.Status.PROCESSING, "processing"),
    _set_status(Order.Status.SHIPPED, "shipped"),
    _set_status(Order.Status.DELIVERED, "delivered"),
    _set_status(Order.Status.CANCELLED, "cancelled"),
]
PAYMENT_ACTIONS = [
    _set_payment(Order.PaymentStatus.PAID, "paid"),
    _set_payment(Order.PaymentStatus.FAILED, "failed"),
    _set_payment(Order.PaymentStatus.REFUNDED, "refunded"),
]


class ProductionFilter(admin.SimpleListFilter):
    title = "production"
    parameter_name = "production"

    def lookups(self, request, model_admin):
        return [("rushed", "Express or priority"), ("priority", "Priority only")]

    def queryset(self, request, queryset):
        if self.value() == "priority":
            return queryset.filter(items__options__production="Priority").distinct()
        if self.value() == "rushed":
            return queryset.filter(Q(items__options__production="Priority") | Q(items__options__production="Express")).distinct()
        return queryset


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "created_at", "customer_name", "deliver_to", "total_ghs", "status", "payment_badge", "rush", "contact")
    list_display_links = ("number",)
    list_filter = ("status", "payment_status", ProductionFilter, "delivery_method", "payment_method", "region", "city", "created_at")
    list_editable = ("status",)
    search_fields = ("number", "name", "email", "phone", "payment_reference", "address", "city")
    date_hierarchy = "created_at"
    list_per_page = 30
    inlines = [OrderItemInline]
    actions = ORDER_ACTIONS + PAYMENT_ACTIONS
    readonly_fields = ("number", "delivery_box", "customer_link", "user", "contact", "created_at", "updated_at", "paid_at", "subtotal", "delivery_fee", "total")
    fieldsets = (
        ("Order", {"fields": ("number", "status", "delivery_box", "created_at", "updated_at", "note")}),
        ("Customer", {"fields": ("customer_link", "user", "contact", "name", "email", "phone", "address", "city", "region")}),
        ("Delivery & payment", {"fields": ("delivery_method", "delivery_fee", "payment_method", "payment_status", "payment_reference", "paid_at")}),
        ("Totals", {"fields": ("subtotal", "total")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("items")

    @admin.display(description="Total", ordering="total")
    def total_ghs(self, obj):
        return ghs(obj.total)

    def has_add_permission(self, request):
        return False  # orders come from the website

    @admin.display(description="Customer", ordering="name")
    def customer_name(self, obj):
        return format_html("{}<br><small class='hx-muted'>{}</small>", obj.name, obj.phone)

    @admin.display(description="Customer record")
    def customer_link(self, obj):
        if not obj.customer_id:
            return "—"
        url = reverse("admin:orders_customer_change", args=[obj.customer_id])
        return format_html('<a href="{}">{}</a>', url, obj.customer)

    @admin.display(description="Contact")
    def contact(self, obj):
        return contact_buttons(obj.name, obj.phone, obj.number)

    @admin.display(description="Deliver to", ordering="region")
    def deliver_to(self, obj):
        return format_html("<b>{}</b>, {}<br><small class='hx-muted'>{}</small>", obj.city, obj.region, obj.delivery_method)

    @admin.display(description="Delivery")
    def delivery_box(self, obj):
        if not obj.pk:
            return "—"
        query = quote(f"{obj.address}, {obj.city}, {obj.region}, Ghana")
        return format_html(
            '<div class="hx-deliver">'
            '<div class="hx-deliver-addr"><span class="hx-kpi-label">Deliver to</span>'
            '<strong>{}</strong><span>{}</span><span>{}, {}</span><span>{}</span></div>'
            '<div class="hx-deliver-meta"><span class="hx-kpi-label">Method</span><strong>{}</strong><span>Fee {}</span>'
            '<a class="hx-btn" href="https://www.google.com/maps/search/?api=1&query={}" target="_blank" rel="noopener">Open in Google Maps</a></div>'
            '</div>',
            obj.name, obj.address, obj.city, obj.region, obj.phone,
            obj.delivery_method, ghs(obj.delivery_fee), query,
        )

    @admin.display(description="Payment", ordering="payment_status")
    def payment_badge(self, obj):
        return pill(obj.payment_status, obj.get_payment_status_display())

    @admin.display(description="Production")
    def rush(self, obj):
        level = obj.rush_production
        return pill("priority" if level == "Priority" else "express", level) if level else "Standard"


# ── Payments (same orders, payment view) ───────────────────────────────

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("number", "created_at", "name", "payment_method", "total_ghs", "payment_badge", "payment_reference", "paid_at")
    list_display_links = ("number",)
    list_filter = ("payment_status", "payment_method", "paid_at", "created_at")
    list_editable = ("payment_reference",)
    search_fields = ("number", "name", "phone", "payment_reference")
    date_hierarchy = "created_at"
    actions = PAYMENT_ACTIONS
    fields = ("number", "name", "phone", "payment_method", "total", "payment_status", "payment_reference", "paid_at", "note")
    readonly_fields = ("number", "name", "phone", "payment_method", "total", "paid_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Total", ordering="total")
    def total_ghs(self, obj):
        return ghs(obj.total)

    @admin.display(description="Status", ordering="payment_status")
    def payment_badge(self, obj):
        return pill(obj.payment_status, obj.get_payment_status_display())

    def changelist_view(self, request, extra_context=None):
        qs = Order.objects.exclude(status=Order.Status.CANCELLED)
        totals = {
            "paid": qs.filter(payment_status="paid").aggregate(s=Sum("total"))["s"] or 0,
            "pending": qs.filter(payment_status="pending").aggregate(s=Sum("total"))["s"] or 0,
            "pending_count": qs.filter(payment_status="pending").count(),
            "refunded": Order.objects.filter(payment_status="refunded").aggregate(s=Sum("total"))["s"] or 0,
        }
        return super().changelist_view(request, {**(extra_context or {}), "payment_totals": totals})


# ── Customers ──────────────────────────────────────────────────────────

class CustomerOrderInline(admin.TabularInline):
    model = Order
    extra = 0
    fields = ("number_link", "created_at", "total", "status", "payment_status")
    readonly_fields = fields
    can_delete = False
    show_change_link = False
    verbose_name_plural = "Orders"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Order")
    def number_link(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("admin:orders_order_change", args=[obj.pk]), obj.number)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "region", "orders_count", "total_spent", "last_order", "contact")
    search_fields = ("name", "phone", "email")
    list_filter = ("region", "created_at")
    readonly_fields = ("contact", "created_at", "orders_count", "total_spent", "last_order")
    fields = ("name", "phone", "email", "city", "region", "contact", "notes", "orders_count", "total_spent", "last_order", "created_at")
    inlines = [CustomerOrderInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _orders=Count("orders"),
            _spent=Sum("orders__total", filter=Q(orders__payment_status="paid")),
            _last=Max("orders__created_at"),
        )

    @admin.display(description="Orders", ordering="_orders")
    def orders_count(self, obj):
        return obj._orders

    @admin.display(description="Total spent (paid)", ordering="_spent")
    def total_spent(self, obj):
        return f"GH₵ {obj._spent:,.2f}" if obj._spent else "—"

    @admin.display(description="Last order", ordering="_last")
    def last_order(self, obj):
        return obj._last.strftime("%d %b %Y") if obj._last else "—"

    @admin.display(description="Contact")
    def contact(self, obj):
        return contact_buttons(obj.name, obj.phone)
