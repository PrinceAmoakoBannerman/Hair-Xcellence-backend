from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
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


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("catalog.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
