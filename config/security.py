"""
Shared security helpers: the visitor's real IP, API rate limits and sign-in lockout.

On Render, every request passes through Cloudflare, which sets True-Client-IP to the visitor's
address. X-Forwarded-For is NOT used: Render appends to it without clearing what the visitor sent,
so it can be faked to dodge rate limits.
"""
import hashlib

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle


def client_ip(request) -> str:
    meta = getattr(request, "META", {})
    for header in settings.CLIENT_IP_HEADERS:
        value = meta.get(header, "").split(",")[0].strip()
        if value:
            return value[:64]
    return meta.get("REMOTE_ADDR", "")[:64] or "unknown"


# ── API rate limits ────────────────────────────────────────────────────
# Each limit has its own scope, so browsing products never uses up the order or sign-in allowance.
# They apply to everyone (guests and signed-in customers), keyed on the visitor's IP.

class IPThrottle(SimpleRateThrottle):
    scope = "ip"  # general limit for every API endpoint (rate in REST_FRAMEWORK settings)

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": client_ip(request)}


class AuthThrottle(IPThrottle):
    scope = "auth"
    rate = "10/min"


class OrderThrottle(IPThrottle):
    scope = "orders"
    rate = "20/hour"


class PaymentThrottle(IPThrottle):
    scope = "payments"
    rate = "60/hour"


class EnquiryThrottle(IPThrottle):
    scope = "enquiries"
    rate = "10/hour"


# ── Sign-in lockout ────────────────────────────────────────────────────

LOCKOUT_SECONDS = 15 * 60


class LoginGuard:
    """
    Counts failed sign-ins and blocks further attempts for 15 minutes once a limit is reached:
    - per account + IP (stops guessing one password from one place),
    - per IP (stops trying many accounts from one place),
    - per account overall, set high so an attacker can't easily lock the real owner out.
    """

    def __init__(self, area: str, per_account_ip=5, per_ip=20, per_account=50):
        self.area = area
        self.limits = {"account_ip": per_account_ip, "ip": per_ip, "account": per_account}

    def _keys(self, account: str, ip: str) -> dict[str, str]:
        acct = hashlib.sha256(account.strip().lower().encode()).hexdigest()[:24]
        return {
            "account_ip": f"lock:{self.area}:ai:{acct}:{ip}",
            "ip": f"lock:{self.area}:ip:{ip}",
            "account": f"lock:{self.area}:a:{acct}",
        }

    def is_blocked(self, account: str, ip: str) -> bool:
        counts = cache.get_many(list(self._keys(account, ip).values()))
        return any(counts.get(key, 0) >= self.limits[kind] for kind, key in self._keys(account, ip).items())

    def failed(self, account: str, ip: str) -> None:
        for key in self._keys(account, ip).values():
            if cache.add(key, 1, LOCKOUT_SECONDS):
                continue
            try:
                cache.incr(key)
            except ValueError:  # expired between add() and incr()
                cache.set(key, 1, LOCKOUT_SECONDS)

    def succeeded(self, account: str, ip: str) -> None:
        cache.delete(self._keys(account, ip)["account_ip"])


admin_guard = LoginGuard("admin")
customer_guard = LoginGuard("customer")
LOCKED_MESSAGE = "Too many sign-in attempts. Please wait 15 minutes and try again."
