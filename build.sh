#!/usr/bin/env bash
# Render build step for the Django backend.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createcachetable   # shared cache for rate limits and the product API
python manage.py check --deploy --fail-level WARNING
