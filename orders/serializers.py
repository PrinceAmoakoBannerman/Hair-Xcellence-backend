from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from catalog.models import Product
from catalog.pricing import DELIVERY, PricingError, unit_price

from .models import Customer, Order, OrderItem

PAYMENT_METHODS = ["MTN Mobile Money", "Telecel Cash", "AT Money", "Debit / Credit Card"]
MAX_QTY = 20
MAX_LINES = 30


class OrderItemInSerializer(serializers.Serializer):
    product = serializers.SlugField(help_text="Product slug (the frontend's product id).")
    options = serializers.DictField(child=serializers.CharField(max_length=60))
    addons = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_QTY)


class OrderCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    address = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=80)
    region = serializers.CharField(max_length=60)
    delivery_method = serializers.ChoiceField(choices=list(DELIVERY))
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS)
    items = OrderItemInSerializer(many=True)

    def validate_city(self, value):
        """Browser autofill sometimes puts 'Accra, Greater Accra Region, Ghana' in the city box; keep the city."""
        return next((part.strip() for part in value.split(",") if part.strip()), value.strip())

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Your order has no items.")
        if len(items) > MAX_LINES:
            raise serializers.ValidationError("Too many items in one order.")
        return items

    def validate(self, data):
        """Look up every product and recalculate its price from the chosen options."""
        slugs = {i["product"] for i in data["items"]}
        products = {p.slug: p for p in Product.objects.filter(slug__in=slugs, is_active=True)}
        priced = []
        errors = []
        for n, item in enumerate(data["items"], start=1):
            product = products.get(item["product"])
            if not product:
                errors.append(f"Item {n}: product not available.")
                continue
            try:
                price = unit_price(product, item["options"], item["addons"])
            except PricingError as e:
                errors.append(f"Item {n} ({product.name}): {e}")
                continue
            priced.append((product, item, price))
        if errors:
            raise serializers.ValidationError({"items": errors})
        data["priced"] = priced
        return data

    @transaction.atomic
    def create(self, data):
        user = data.pop("user", None)
        fee = Decimal(DELIVERY[data["delivery_method"]]["fee"])
        subtotal = sum((price * item["quantity"] for _, item, price in data["priced"]), Decimal("0"))
        customer = Customer.from_order_details(
            name=data["name"], email=data["email"], phone=data["phone"], city=data["city"], region=data["region"],
        )
        order = Order.objects.create(
            customer=customer,
            user=user,
            name=data["name"], email=data["email"], phone=data["phone"],
            address=data["address"], city=data["city"], region=data["region"],
            delivery_method=data["delivery_method"], delivery_fee=fee,
            payment_method=data["payment_method"],
            subtotal=subtotal, total=subtotal + fee,
        )
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order, product=product, product_name=product.name,
                options=item["options"], addons=item["addons"],
                unit_price=price, quantity=item["quantity"],
            )
            for product, item, price in data["priced"]
        ])
        return order


class OrderItemOutSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    product = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["product", "product_name", "image", "options", "addons", "unit_price", "quantity"]

    def get_image(self, obj) -> str:
        first = obj.product.images.first() if obj.product else None
        if not first:
            return ""
        src = first.src
        request = self.context.get("request")
        if src.startswith("/") and not src.startswith("/images/") and request:
            return request.build_absolute_uri(src)
        return src


class OrderOutSerializer(serializers.ModelSerializer):
    items = OrderItemOutSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = Order
        fields = [
            "number", "status", "created_at", "name", "email", "phone", "address", "city", "region",
            "delivery_method", "delivery_fee", "payment_method", "payment_status", "subtotal", "total", "items",
        ]
