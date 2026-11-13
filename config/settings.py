"""
Django settings for the Hair Xcellence backend.

All secrets and environment-specific values come from environment variables
(or a local `.env` file in development). See `.env.example`.
"""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Render sets RENDER_EXTERNAL_HOSTNAME automatically for web services.
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

INSTALLED_APPS = [
    "jazzmin",  # admin theme, must come before django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # third party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "cloudinary_storage",
    "cloudinary",
    # local
    "catalog",
    "orders",
    "accounts",
    "payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: DATABASE_URL (Render Postgres) or a local SQLite file.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

# Static files (Django admin CSS/JS) served by WhiteNoise.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Uploaded product photos. Locally they go in backend/media/. In production set
# CLOUDINARY_URL so uploads are stored on Cloudinary (Render's disk is wiped on deploy).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
# …or the three values separately (read directly by the Cloudinary library).
CLOUDINARY_ENABLED = bool(CLOUDINARY_URL) or all(
    os.environ.get(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
)

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage" if CLOUDINARY_ENABLED
        else "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tests render admin pages without running collectstatic first.
import sys  # noqa: E402
if "test" in sys.argv:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

# Own cookie names so this admin doesn't clash with other Django projects on 127.0.0.1
# (browsers share cookies across ports on the same host).
SESSION_COOKIE_NAME = "hx_sessionid"
CSRF_COOKIE_NAME = "hx_csrftoken"

# CORS / CSRF: the Vercel frontend and local dev server may call the API.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "120/min"},
}

# Production hardening (only when DEBUG is off).
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True


# ── Admin theme (Jazzmin) ─────────────────────────────────────────────
STORE_URL = os.environ.get("STORE_URL", "https://hair-xcellence.vercel.app")

# Paystack (online MoMo / card payments). Secret key only — it never leaves the server.
# Empty = online payment switched off; orders are still placed and paid manually.
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")

JAZZMIN_SETTINGS = {
    "site_title": "Hair Xcellence admin",
    "site_header": "Hair Xcellence",
    "site_brand": "Hair Xcellence",
    "site_logo": "hx/logo.svg",
    "login_logo": "hx/logo-full.svg",
    "site_logo_classes": "",
    "site_icon": "hx/logo.svg",
    "welcome_sign": "Sign in to manage the store",
    "copyright": "Hair Xcellence",
    "search_model": ["orders.Order", "orders.Customer", "catalog.Product"],
    "user_avatar": None,
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "View store", "url": STORE_URL, "new_window": True},
        {"name": "API", "url": "/api/products/", "new_window": True},
    ],
    "usermenu_links": [
        {"name": "View store", "url": STORE_URL, "new_window": True, "icon": "fas fa-store"},
    ],
    "hide_apps": ["authtoken"],  # sign-in tokens are internal
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": ["orders", "orders.Order", "orders.Payment", "orders.Customer", "catalog", "catalog.Product", "catalog.Category", "auth"],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "orders": "fas fa-receipt",
        "orders.Order": "fas fa-shopping-bag",
        "orders.Payment": "fas fa-money-bill-wave",
        "orders.Customer": "fas fa-user-friends",
        "authtoken": "fas fa-key",
        "authtoken.TokenProxy": "fas fa-key",
        "catalog": "fas fa-store",
        "catalog.Product": "fas fa-gem",
        "catalog.Category": "fas fa-tags",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "custom_css": "hx/admin.css",
    "show_ui_builder": False,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {"auth.user": "collapsible", "auth.group": "vertical_tabs"},
}

JAZZMIN_UI_TWEAKS = {
    "theme": "default",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": True,
    "navbar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_fixed": True,
    "sidebar_nav_small_text": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_flat_style": True,
    "brand_colour": "navbar-dark",
    "accent": "accent-primary",
    "button_classes": {
        "primary": "btn-primary", "secondary": "btn-outline-secondary", "info": "btn-outline-info",
        "warning": "btn-warning", "danger": "btn-danger", "success": "btn-success",
    },
}
