from urllib.parse import quote

from django.contrib import admin, messages
from django.db.models import Count, Max, Q, Sum
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from catalog.admin import image_src

from .models import Customer, Enquiry, Order, OrderItem, Payment, normalise_phone


def ghs(amount) -> str:
    return f"GH₵ {amount:,.0f}" if amount == int(amount) else f"GH₵ {amount:,.2f}"


def short_city(city: str) -> str:
    """'Accra, Greater Accra Region, Ghana' (browser autofill) -> 'Accra'."""
    return next((part.strip() for part in city.split(",") if part.strip()), city)


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

OPTION_LABELS = {
    "length": "Length", "texture": "Texture", "laceType": "Lace", "laceSize": "Lace size", "density": "Density",
    "colour": "Colour", "cap": "Cap size", "production": "Production",
}


def option_label(key: str) -> str:
    return OPTION_LABELS.get(key) or key[:1].upper() + key[1:]


def items_html(order) -> str:
    """Order items as clear cards: photo, name, every chosen option on its own line, quantity and price."""
    cards = []
    for it in order.items.all():
        first = it.product.images.first() if it.product else None
        photo = format_html('<img src="{}" alt="">', image_src(first.src)) if first else format_html('<span class="hx-noimg">No photo</span>')
        name = (format_html('<a href="{}">{}</a>', reverse("admin:catalog_product_change", args=[it.product_id]), it.product_name)
                if it.product_id else it.product_name)
        specs = format_html_join(
            "", '<div class="{}"><dt>{}</dt><dd>{}</dd></div>',
            (("hx-rush" if k == "production" and v != "Standard" else "", option_label(k), v) for k, v in it.options.items()),
        )
        addons = format_html('<div><dt>Add-ons</dt><dd>{}</dd></div>', ", ".join(it.addons)) if it.addons else ""
        cards.append(format_html(
            '<div class="hx-item"><div class="hx-item-photo">{}</div>'
            '<div class="hx-item-body"><strong class="hx-item-name">{}</strong><dl class="hx-specs">{}{}</dl></div>'
            '<div class="hx-item-price"><span class="hx-qty">Qty {}</span><span class="hx-muted">{} each</span><strong>{}</strong></div></div>',
            photo, name, specs, addons, it.quantity, ghs(it.unit_price), ghs(it.line_total),
        ))
    totals = format_html(
        '<dl class="hx-item-totals"><div><dt>Subtotal</dt><dd>{}</dd></div><div><dt>Delivery · {}</dt><dd>{}</dd></div>'
        '<div class="hx-grand"><dt>Total</dt><dd>{}</dd></div></dl>',
        ghs(order.subtotal), order.delivery_method, ghs(order.delivery_fee), ghs(order.total),
    )
    return format_html('<div class="hx-items">{}{}{}</div>', note_html(order), format_html_join("", "{}", ((c,) for c in cards)), totals)


def note_html(order, label: bool = True) -> str:
    """The customer's own note, highlighted so it isn't missed when making the wig."""
    if not order.customer_note:
        return ""
    heading = format_html('<span class="hx-kpi-label">Customer’s note</span>') if label else ""
    return format_html('<div class="hx-cnote">{}<p>{}</p></div>', heading, order.customer_note)


class HasNoteFilter(admin.SimpleListFilter):
    title = "customer's note"
    parameter_name = "note"

    def lookups(self, request, model_admin):
        return [("yes", "Has a note"), ("no", "No note")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(customer_note="")
        if self.value() == "no":
            return queryset.filter(customer_note="")
        return queryset


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
    list_display = ("number", "created_at", "customer_name", "deliver_to", "total_ghs", "status", "payment_badge", "rush", "note_flag", "contact")
    list_display_links = ("number",)
    list_filter = ("status", "payment_status", ProductionFilter, HasNoteFilter, "delivery_method", "payment_method", "region", "city", "created_at")
    list_editable = ("status",)
    search_fields = ("number", "name", "email", "phone", "payment_reference", "address", "city", "customer_note")
    date_hierarchy = "created_at"
    list_per_page = 30
    actions = ORDER_ACTIONS + PAYMENT_ACTIONS
    readonly_fields = ("number", "customer_note_box", "items_box", "delivery_box", "customer_link", "user", "contact", "created_at", "updated_at", "paid_at", "payment_channel", "subtotal", "delivery_fee", "total")
    fieldsets = (
        ("Order", {"fields": ("number", "status", "customer_note_box", "delivery_box", "created_at", "updated_at", "note")}),
        ("Order items", {"fields": ("items_box",)}),
        ("Customer", {"fields": ("customer_link", "user", "contact", "name", "email", "phone", "address", "city", "region")}),
        ("Delivery & payment", {"fields": ("delivery_method", "delivery_fee", "payment_method", "payment_status", "payment_channel", "payment_reference", "paid_at")}),
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
        city = short_city(obj.city)
        place = city if not obj.region or obj.region.lower() in city.lower() else f"{city} · {obj.region}"
        full = f"{obj.address}, {obj.city}, {obj.region}"
        return format_html(
            '<span class="hx-addr" title="{}">{}</span><small class="hx-muted hx-place">{} · {}</small>',
            full, obj.address, place, obj.delivery_method,
        )

    @admin.display(description="Customer's note")
    def customer_note_box(self, obj):
        return note_html(obj, label=False) or "—"

    @admin.display(description="Note")
    def note_flag(self, obj):
        if not obj.customer_note:
            return ""
        short = obj.customer_note if len(obj.customer_note) <= 140 else obj.customer_note[:137] + "…"
        return format_html('<span class="hx-pill hx-note-pill" title="{}">Note</span>', short)

    @admin.display(description="Items")
    def items_box(self, obj):
        return items_html(obj) if obj.pk else "—"

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
    list_display = ("number", "created_at", "name", "payment_method", "total_ghs", "payment_badge", "channel", "payment_reference", "paid_at")
    list_display_links = ("number",)
    list_filter = ("payment_status", "payment_method", "paid_at", "created_at")
    list_editable = ("payment_reference",)
    search_fields = ("number", "name", "phone", "payment_reference")
    date_hierarchy = "created_at"
    actions = PAYMENT_ACTIONS
    fields = ("number", "name", "phone", "payment_method", "total", "payment_status", "payment_channel", "payment_reference", "paid_at", "note")
    readonly_fields = ("number", "name", "phone", "payment_method", "total", "paid_at", "payment_channel")

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

    @admin.display(description="Paid via")
    def channel(self, obj):
        return {"mobile_money": "MoMo (Paystack)", "card": "Card (Paystack)"}.get(obj.payment_channel, obj.payment_channel or "—")

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


# ── Enquiries (contact / request form on the website) ─────────────────

@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "topic_badge", "name", "preview", "product", "needed_by", "reply")
    list_display_links = ("created_at", "name")
    list_editable = ("status",)
    list_filter = ("status", "topic", "created_at")
    search_fields = ("name", "phone", "email", "message", "product")
    date_hierarchy = "created_at"
    readonly_fields = ("topic", "name", "phone", "email", "message_box", "product", "needed_by", "reply", "created_at", "updated_at")
    fieldsets = (
        ("Enquiry", {"fields": ("status", "topic", "message_box", "product", "needed_by", "created_at")}),
        ("Customer", {"fields": ("name", "phone", "email", "reply")}),
        ("Notes", {"fields": ("note", "updated_at")}),
    )
    actions = ["mark_replied", "mark_closed"]

    def has_add_permission(self, request):
        return False  # enquiries come from the website

    @admin.display(description="Topic", ordering="topic")
    def topic_badge(self, obj):
        return pill("priority" if obj.topic == Enquiry.Topic.REQUEST else "pending", obj.get_topic_display())

    @admin.display(description="Message")
    def preview(self, obj):
        text = obj.message if len(obj.message) <= 90 else obj.message[:87] + "…"
        return format_html('<span title="{}">{}</span>', obj.message, text)

    @admin.display(description="Message")
    def message_box(self, obj):
        return format_html('<div class="hx-cnote"><p>{}</p></div>', obj.message)

    @admin.display(description="Reply")
    def reply(self, obj):
        key = normalise_phone(obj.phone)
        first = obj.name.split()[0] if obj.name else ""
        about = f" about {obj.product}" if obj.product else ""
        text = quote(f"Hi {first}, thank you for your message to Hair Xcellence{about}. ".replace("  ", " "))
        mail = format_html(' <a class="hx-btn" href="mailto:{}">Email</a>', obj.email) if obj.email else ""
        return format_html(
            '<a class="hx-btn wa" href="https://wa.me/{}?text={}" target="_blank" rel="noopener">Reply on WhatsApp</a> '
            '<a class="hx-btn" href="tel:+{}">Call</a>{}',
            key, text, key, mail,
        )

    @admin.action(description="Mark as replied")
    def mark_replied(self, request, queryset):
        n = queryset.update(status=Enquiry.Status.REPLIED)
        self.message_user(request, f"{n} enquir{'y' if n == 1 else 'ies'} marked as replied.", messages.SUCCESS)

    @admin.action(description="Mark as closed")
    def mark_closed(self, request, queryset):
        n = queryset.update(status=Enquiry.Status.CLOSED)
        self.message_user(request, f"{n} enquir{'y' if n == 1 else 'ies'} closed.", messages.SUCCESS)
