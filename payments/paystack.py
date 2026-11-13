"""
Minimal Paystack client (https://paystack.com/docs/api/).

Only the SECRET key is used, and only on the server. It comes from the
PAYSTACK_SECRET_KEY environment variable and is never sent to the browser.
"""
import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

API = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.PAYSTACK_SECRET_KEY)


def to_pesewas(amount: Decimal) -> int:
    """Paystack amounts are in the smallest unit (GH₵ 1 = 100 pesewas)."""
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def new_reference(order_number: str) -> str:
    return f"{order_number}-{secrets.token_hex(4)}"


def _request(method: str, path: str, body: dict | None = None) -> dict:
    """Call the Paystack API. Separate function so tests can replace it."""
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "hair-xcellence-backend",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read().decode()).get("message", "")
        except Exception:
            message = ""
        raise PaystackError(message or f"Paystack returned HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise PaystackError("Could not reach Paystack. Please try again.") from e
    if not data.get("status"):
        raise PaystackError(data.get("message") or "Paystack request failed")
    return data["data"]


def initialize(*, email: str, amount: Decimal, reference: str, callback_url: str, metadata: dict) -> dict:
    """Start a payment. Returns {'authorization_url', 'access_code', 'reference'}."""
    return _request("POST", "/transaction/initialize", {
        "email": email,
        "amount": to_pesewas(amount),
        "currency": "GHS",
        "reference": reference,
        "callback_url": callback_url,
        "channels": ["mobile_money", "card"],
        "metadata": metadata,
    })


def verify(reference: str) -> dict:
    """Ask Paystack for the real status of a payment (never trust the browser)."""
    return _request("GET", f"/transaction/verify/{urllib.request.quote(reference, safe='')}")


def valid_signature(raw_body: bytes, signature: str) -> bool:
    """Webhooks are signed with HMAC-SHA512 of the raw body using the secret key."""
    if not settings.PAYSTACK_SECRET_KEY or not signature:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
