from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "Hair Xcellence admin"
admin.site.site_title = "Hair Xcellence admin"
admin.site.index_title = "Store management"


# Dashboard: add store stats to the admin home page (templates/admin/index.html).
_default_index = admin.site.index


def _dashboard_index(request, extra_context=None):
    from orders.dashboard import dashboard_stats
    return _default_index(request, {**(extra_context or {}), "stats": dashboard_stats()})


admin.site.index = _dashboard_index


# Admin sign-in lockout: after repeated wrong passwords, refuse further attempts for 15 minutes.
_default_login = admin.site.login


def _guarded_login(request, extra_context=None):
    if request.method != "POST":
        return _default_login(request, extra_context)
    from config.security import LOCKED_MESSAGE, admin_guard, client_ip
    username, ip = request.POST.get("username", "")[:150], client_ip(request)
    if admin_guard.is_blocked(username, ip):
        return HttpResponse(
            f"<!doctype html><meta charset=utf-8><title>Try again later</title>"
            f"<p style='font:16px system-ui;margin:15vh auto;max-width:420px;text-align:center'>{LOCKED_MESSAGE}</p>",
            status=429,
        )
    response = _default_login(request, extra_context)
    if response.status_code in (301, 302) and request.user.is_authenticated:
        admin_guard.succeeded(username, ip)
    else:
        admin_guard.failed(username, ip)
    return response


admin.site.login = _guarded_login


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    # The backend's home page sends visitors to the shop, so it never reveals where the admin is.
    path("", RedirectView.as_view(url=settings.STORE_URL, permanent=False)),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("catalog.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
