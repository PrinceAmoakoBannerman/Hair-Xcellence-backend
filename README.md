# Hair Xcellence — Backend

Django + Django REST Framework backend for the Hair Xcellence store: admin panel (Jazzmin), product catalogue and orders API. The website is a separate React app deployed on Vercel.

## Run locally

First time:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_products
python manage.py createsuperuser
```

Every time after that:

```bat
.venv\Scripts\activate
python manage.py runserver 8001
```

- Admin: http://127.0.0.1:8001/admin/
- API: http://127.0.0.1:8001/api/products/

Run the tests with `python manage.py test`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health/` | Health check |
| GET | `/api/products/` | Active products. Filters: `?category=Glueless%20Wigs`, `?kind=wig` |
| GET | `/api/products/<slug>/` | One product |
| POST | `/api/orders/` | Place an order. Prices are recalculated on the server from the chosen options |
| GET | `/api/payments/config/` | Whether online payment is switched on |
| POST | `/api/payments/start/` | Start a Paystack payment for an order (`{order, email}`) |
| GET | `/api/payments/verify/?reference=` | Confirm a payment with Paystack when the customer returns |
| POST | `/api/payments/webhook/` | Paystack notifications (signature-checked) — set this URL in the Paystack dashboard |
| POST | `/api/auth/register/`, `/api/auth/login/` | Customer accounts |
| GET | `/api/auth/me/`, `/api/auth/orders/` | Signed-in customer's details and orders |

Option prices live in `catalog/pricing.py` and must match `src/data.ts` in the website repository.

## Configuration

All settings come from environment variables (see `.env.example`). Nothing secret is stored in this repository.

| Variable | Purpose |
|---|---|
| `DJANGO_DEBUG` | `True` locally, `False` in production |
| `DJANGO_SECRET_KEY` | Required in production: 50+ random characters (`python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DJANGO_ALLOWED_HOSTS` | Hostnames the backend answers on |
| `DATABASE_URL` | Postgres connection (Neon in production, local Postgres or SQLite in development) |
| `CORS_ALLOWED_ORIGINS` | Website URLs allowed to call the API |
| `CSRF_TRUSTED_ORIGINS` | Backend URL (needed for the admin behind HTTPS) |
| `STORE_URL` | Website URL (used for the admin's "View store" link) |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Store photos uploaded in the admin (Render's disk is wiped on every deploy). `CLOUDINARY_URL` also works |
| `DJANGO_ADMIN_URL` | Admin address. `admin/` locally; something hard to guess in production, e.g. `hx-studio-7f3k/` |
| `PAYSTACK_SECRET_KEY` | Online MoMo / card payments. `sk_test_…` for testing, `sk_live_…` in production. Empty = online payment off |

## Security

- **Rate limits** (per visitor IP): 120 API requests a minute overall; sign-in and sign-up 10 a minute; orders 20 an hour; payments 60 an hour. Each has its own allowance, so browsing never uses up the order limit. On Render the IP comes from Cloudflare's `True-Client-IP` header (`X-Forwarded-For` can be faked there).
- **Sign-in lockout:** 5 wrong passwords for an account from one IP (or 20 from one IP in total) blocks further attempts for 15 minutes. Applies to the admin and to customer accounts. Staff accounts can only sign in to the admin, never through the shop.
- **Sessions:** admin sign-in lasts 12 hours; customer sign-in 30 days, then they sign in again. Cookies are `Secure`, `HttpOnly` (session) and `SameSite=Lax`.
- **HTTPS:** redirect to HTTPS, HSTS for a year, `X-Frame-Options: DENY`, no MIME sniffing, strict referrer policy.
- **Admin address:** set `DJANGO_ADMIN_URL`; the backend's home page redirects to the shop and doesn't reveal it.
- **Uploads:** photos up to 10 MB each, checked to be real images.
- **Payments:** amounts are recalculated on the server; Paystack webhooks are signature-checked and re-verified.
- `build.sh` runs `manage.py check --deploy` and stops the deploy if a security setting is missing.

## Caching

- The product API is cached for 10 minutes and cleared the moment a product, photo or category changes in the admin.
- Responses carry an ETag; browsers re-check each time and get a quick `304 Not Modified` when nothing changed.
- The cache lives in the database (`createcachetable`, run by `build.sh`), so all server processes share it.

## Deploy on Render (+ Neon database)

The database is a free Neon Postgres (it doesn't expire); the backend runs on Render. Both in Frankfurt.

1. **Neon** (neon.tech): create a project in region *AWS Europe Central 1 (Frankfurt)*. Copy the connection string (direct, not pooled; it ends with `?sslmode=require`).
2. **Render**: New + → Blueprint → choose this repository. `render.yaml` creates the web service. When asked, paste `DATABASE_URL` (the Neon link), the Paystack and Cloudinary keys, and a secret `DJANGO_ADMIN_URL`.
3. Set `CORS_ALLOWED_ORIGINS` and `STORE_URL` to the Vercel URL and `CSRF_TRUSTED_ORIGINS` to the Render URL.
4. The free plan has no shell: create the admin account and load products by running `manage.py createsuperuser` / `seed_products` locally with `DATABASE_URL` set to the Neon link.
