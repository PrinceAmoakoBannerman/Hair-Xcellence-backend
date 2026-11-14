"""Numbers for the admin dashboard."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from catalog.models import Product

from .models import Customer, Enquiry, Order, OrderItem

LIVE = ~Q(status=Order.Status.CANCELLED)
RUSHED = Q(items__options__production="Priority") | Q(items__options__production="Express")


def _money(qs) -> Decimal:
    return qs.aggregate(s=Sum("total"))["s"] or Decimal("0")


def dashboard_stats() -> dict:
    now = timezone.now()
    today = timezone.localdate()
    start_today = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)

    paid = Order.objects.filter(payment_status=Order.PaymentStatus.PAID)
    live = Order.objects.filter(LIVE)
    pending = live.filter(payment_status=Order.PaymentStatus.PENDING)

    paid_30 = paid.filter(paid_at__gte=d30)
    paid_30_count = paid_30.count()

    # 14-day chart: paid revenue per day (by payment date)
    start = today - timedelta(days=13)
    by_day = {
        row["day"]: row["total"]
        for row in paid.filter(paid_at__date__gte=start)
        .annotate(day=TruncDate("paid_at", tzinfo=timezone.get_current_timezone()))
        .values("day").annotate(total=Sum("total"))
    }
    orders_by_day = {
        row["day"]: row["n"]
        for row in live.filter(created_at__date__gte=start)
        .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
        .values("day").annotate(n=Count("id"))
    }
    days = [start + timedelta(days=i) for i in range(14)]
    peak = max([by_day.get(d, 0) for d in days] + [1])
    chart = [{
        "label": d.strftime("%d %b"),
        "short": d.strftime("%a")[0],
        "total": by_day.get(d, 0),
        "orders": orders_by_day.get(d, 0),
        "pct": round(float(by_day.get(d, 0)) / float(peak) * 100) if by_day.get(d) else 0,
    } for d in days]

    pipeline = [
        {"key": s.value, "label": s.label, "count": Order.objects.filter(status=s.value).count()}
        for s in [Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]
    ]

    top_products = (
        OrderItem.objects.filter(order__created_at__gte=d30).exclude(order__status=Order.Status.CANCELLED)
        .values("product_name").annotate(units=Sum("quantity"), orders=Count("order", distinct=True))
        .order_by("-units")[:5]
    )

    rushed = (
        live.filter(status__in=[Order.Status.CONFIRMED, Order.Status.PROCESSING]).filter(RUSHED)
        .distinct().order_by("created_at")[:6]
    )

    regions = list(
        live.filter(created_at__gte=d30).values("region").annotate(n=Count("id"), total=Sum("total")).order_by("-n")[:6]
    )
    top_region = max([r["n"] for r in regions] + [1])
    for r in regions:
        r["pct"] = round(r["n"] / top_region * 100)

    customers = Customer.objects.all()
    repeat = customers.annotate(n=Count("orders")).filter(n__gt=1).count()

    return {
        "revenue_today": _money(paid.filter(paid_at__gte=start_today)),
        "revenue_7": _money(paid.filter(paid_at__gte=d7)),
        "revenue_30": _money(paid_30),
        "orders_today": live.filter(created_at__gte=start_today).count(),
        "orders_7": live.filter(created_at__gte=d7).count(),
        "orders_30": live.filter(created_at__gte=d30).count(),
        "avg_order": (_money(paid_30) / paid_30_count) if paid_30_count else Decimal("0"),
        "pending_count": pending.count(),
        "pending_total": _money(pending),
        "to_ship": live.filter(status__in=[Order.Status.CONFIRMED, Order.Status.PROCESSING]).count(),
        "chart": chart,
        "chart_total": sum((c["total"] for c in chart), Decimal("0")),
        "pipeline": pipeline,
        "cancelled": Order.objects.filter(status=Order.Status.CANCELLED).count(),
        "top_products": list(top_products),
        "rushed": list(rushed),
        "recent": list(Order.objects.order_by("-created_at")[:8]),
        "regions": regions,
        "customers_total": customers.count(),
        "customers_new_30": customers.filter(created_at__gte=d30).count(),
        "customers_repeat": repeat,
        "low_stock": list(Product.objects.filter(is_active=True, availability=Product.Availability.LOW_STOCK).values("id", "name")[:6]),
        "products_live": Product.objects.filter(is_active=True).count(),
        "enquiries_new": Enquiry.objects.filter(status=Enquiry.Status.NEW).count(),
        "requests_new": Enquiry.objects.filter(status=Enquiry.Status.NEW, topic=Enquiry.Topic.REQUEST).count(),
        "sold_out": Product.objects.filter(is_active=True, availability=Product.Availability.SOLD_OUT).count(),
        "products_hidden": Product.objects.filter(is_active=False).count(),
        "products_on_sale": Product.objects.filter(is_active=True, sale__gt=0).count(),
    }
