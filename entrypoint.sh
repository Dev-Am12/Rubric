#!/bin/sh
set -eu
cd /app/src
python manage.py migrate --noinput
python manage.py seed_fixtures
exec gunicorn rubric.wsgi:application --bind 0.0.0.0:8080 --workers 3
