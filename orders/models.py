import secrets

from django.db import models


def new_order_number() -> str:
    return f"HX-{secrets.randbelow(900000) + 100000}"


def normalise_phone(phone: str) -> str:
    """Digits only, with Ghana numbers stored as 233XXXXXXXXX so 024… and +233 24… match."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "233" + digits[1:]
    return digits


class Customer(models.Model):
    """Created automatically from orders (matched by phone number)."""

    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    phone_key = models.CharField(max_length=20, unique=True, editable=False)
    city = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True, help_text="Private notes, e.g. preferences or cap size.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"

    @classmethod
    def from_order_details(cls, *, name, email, phone, city, region):
        key = normalise_phone(phone)
        customer, created = cls.objects.get_or_create(
            phone_key=key, defaults={"name": name, "email": email, "phone": phone, "city": city, "region": region},
        )
        if not created:  # keep their latest details
            customer.name, customer.email, customer.phone, customer.city, customer.region = name, email or customer.email, phone, city, region
            customer.save(update_fields=["name", "email", "phone", "city", "region"])
        return customer


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
    customer = models.ForeignKey(Customer, null=True, blank=True, related_name="orders", on_delete=models.SET_NULL)
    user = models.ForeignKey(
        "auth.User", null=True, blank=True, related_name="orders", on_delete=models.SET_NULL,
        help_text="Website account that placed the order (if the customer was signed in).",
    )
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
    payment_reference = models.CharField(max_length=100, blank=True, help_text="Mobile Money / Paystack transaction reference.")
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_channel = models.CharField(max_length=30, blank=True, help_text="How the customer paid on Paystack, e.g. mobile_money or card.")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    customer_note = models.TextField(
        "customer's note", blank=True, max_length=500,
        help_text="Written by the customer at checkout, e.g. a date they need the wig by.",
    )
    note = models.TextField("internal note", blank=True, help_text="Internal note (not shown to the customer).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        from django.utils import timezone
        if self.payment_status == self.PaymentStatus.PAID and not self.paid_at:
            self.paid_at = timezone.now()
        elif self.payment_status != self.PaymentStatus.PAID:
            self.paid_at = None
        super().save(*args, **kwargs)

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


class Payment(Order):
    """The same orders, viewed from the payments side in the admin."""

    class Meta:
        proxy = True
        verbose_name = "payment"
        verbose_name_plural = "payments"
