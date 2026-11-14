"""
Server-side pricing for customised products.

Mirrors the option tables in frontend/src/data.ts so the backend never trusts a
price sent by the browser: an order lists the chosen options, and the price is
recalculated here. Keep these tables in sync with the frontend.
"""
from decimal import Decimal

LENGTHS = ['10"', '12"', '14"', '16"', '18"', '20"', '22"', '24"', '26"', '28"', '30"', '32"']

ADDONS = {
    "Bleached knots": 120,
    "Pre-plucked hairline": 150,
    "Baby hair": 100,
    "Custom styling": 300,
}

PRODUCTION = {
    "Standard": 0,
    "Express": 400,
    "Priority": 800,
}

DELIVERY = {
    "Accra express": {"fee": 60, "time": "1–2 working days"},
    "Standard delivery": {"fee": 80, "time": "2–5 working days"},
}


def standard_lengths(kind: str) -> list[tuple[int, int]]:
    """Default lengths (inches, extra GH₵) for a new product: 10"–32" in 2" steps."""
    step = {"bundle": 60, "closure": 70}.get(kind, 180)
    return [(10 + 2 * i, i * step) for i in range(len(LENGTHS))]


def length_prices(product) -> dict[str, Decimal]:
    """{'10"': extra price, …} for a product: the lengths set in the admin, or the standard ones."""
    rows = list(product.lengths.all()) if product.pk else []
    if rows:
        return {row.label: Decimal(row.extra_price) for row in rows}
    return {f'{inches}"': Decimal(price) for inches, price in standard_lengths(product.kind)}


def option_groups(kind: str) -> dict[str, dict[str, int]]:
    """Option group key -> {option label: price delta in GH₵} for a product kind (lengths come per product)."""
    step = {"bundle": 60, "closure": 70}.get(kind, 180)
    wig = kind == "wig"
    length = {label: i * step for i, label in enumerate(LENGTHS)}  # replaced by the product's own lengths
    texture = {
        "Straight": 0,
        "Body Wave": 0,
        "Deep Wave": 150 if wig else 40,
        "Loose Wave": 100 if wig else 30,
        "Curly": 200 if wig else 50,
    }
    lace_type = {"Transparent Lace": 0, "HD Lace": 350, "Swiss Lace": 200}
    lace_size = {"4×4 Closure": 0, "5×5 Closure": 250, "13×4 Frontal": 550, "13×6 Frontal": 850}
    density = {"150%": 0, "180%": 300, "200%": 550, "250%": 900}
    colour = {"Natural Black": 0, "Jet Black": 80, "Chocolate Brown": 250, "Burgundy 99J": 400, "Ginger": 450, "Honey Blonde": 450}
    cap = {"Small": 0, "Medium": 0, "Large": 0}

    if kind == "bundle":
        return {"length": length, "texture": texture, "colour": colour}
    if kind == "closure":
        return {"length": length, "texture": texture, "laceType": lace_type, "laceSize": lace_size, "colour": colour}
    return {
        "length": length, "texture": texture, "laceType": lace_type, "laceSize": lace_size,
        "density": density, "colour": colour, "cap": cap, "production": PRODUCTION,
    }


class PricingError(ValueError):
    pass


def unit_price(product, choices: dict[str, str], addons: list[str]) -> Decimal:
    """Price of one unit with the given options. Raises PricingError on unknown options."""
    groups = option_groups(product.kind)
    groups["length"] = length_prices(product)
    total = Decimal(product.base_price)
    for key, options in groups.items():
        value = choices.get(key)
        if value is None:
            raise PricingError(f"Missing option '{key}'.")
        if value not in options:
            raise PricingError(f"'{value}' is not a valid {key}.")
        total += options[value]
    unknown = [k for k in choices if k not in groups]
    if unknown:
        raise PricingError(f"Unknown option(s): {', '.join(unknown)}.")
    if addons and product.kind == "bundle":
        raise PricingError("Bundles have no finishing touches.")
    for addon in addons:
        if addon not in ADDONS:
            raise PricingError(f"'{addon}' is not a valid finishing touch.")
        total += ADDONS[addon]
    return total
