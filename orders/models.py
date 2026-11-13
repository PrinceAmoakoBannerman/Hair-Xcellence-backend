import secrets

from django.db import models


def new_order_number() -> str:
    return f"HX-{secrets.randbelow(900000) + 100000}"


class Order(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    number = models.CharField(max_length=20, unique=True, default=new_order_number, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED)

    # Customer
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    region = models.CharField(max_length=60)

    # Delivery & payment
    delivery_method = models.CharField(max_length=40)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=40)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_reference = models.CharField(max_length=100, blank=True, help_text="Paystack reference, once payments are connected.")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True, help_text="Internal note (not shown to the customer).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    @property
    def rush_production(self) -> str:
        """'Priority' / 'Express' if any wig in the order was rushed, else ''."""
        levels = [i.options.get("production", "") for i in self.items.all()]
        return "Priority" if "Priority" in levels else "Express" if "Express" in levels else ""


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=150, help_text="Saved at order time in case the product changes later.")
    options = models.JSONField(default=dict, blank=True)
    addons = models.JSONField(default=list, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def summary(self) -> str:
        parts = list(self.options.values()) + list(self.addons)
        return " · ".join(str(p) for p in parts)
