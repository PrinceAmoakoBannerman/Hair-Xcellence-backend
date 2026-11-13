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

Option prices live in `catalog/pricing.py` and must match `src/data.ts` in the website repository.

## Configuration

All settings come from environment variables (see `.env.example`). Nothing secret is stored in this repository.

| Variable | Purpose |
|---|---|
| `DJANGO_DEBUG` | `True` locally, `False` in production |
| `DJANGO_SECRET_KEY` | Required in production (Render generates one) |
| `DJANGO_ALLOWED_HOSTS` | Hostnames the backend answers on |
| `DATABASE_URL` | Postgres connection (set automatically on Render); SQLite locally |
| `CORS_ALLOWED_ORIGINS` | Website URLs allowed to call the API |
| `CSRF_TRUSTED_ORIGINS` | Backend URL (needed for the admin behind HTTPS) |
| `STORE_URL` | Website URL (used for the admin's "View store" link) |
| `CLOUDINARY_URL` | Stores photos uploaded in the admin (Render's disk is wiped on every deploy) |

## Deploy on Render

New + → Blueprint → choose this repository. `render.yaml` creates the web service and a Postgres database. After the first deploy:

1. Set `CORS_ALLOWED_ORIGINS` and `STORE_URL` to the Vercel URL, `CSRF_TRUSTED_ORIGINS` to the Render URL, and add `CLOUDINARY_URL`.
2. Open the service's **Shell** and run `python manage.py createsuperuser` and `python manage.py seed_products`.
