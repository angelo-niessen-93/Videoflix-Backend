#!/bin/sh
# Academy startup sequence, extended for the existing independent RQ workers.
set -e

# Explicit commands (workers, checks, tests) must not run web initialization.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "Warte auf PostgreSQL auf $DB_HOST:$DB_PORT..."
while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -q; do
    sleep 1
done

python manage.py collectstatic --noinput
# Migrations are versioned; never generate new migration files at startup.
python manage.py migrate --noinput

python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured

User = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
email = os.environ['DJANGO_SUPERUSER_EMAIL']
password = os.environ['DJANGO_SUPERUSER_PASSWORD']
user = User.objects.filter(username=username).first()
if user is None:
    if User.objects.filter(email__iexact=email).exists():
        raise ImproperlyConfigured('Superuser email already belongs to another account.')
    User.objects.create_superuser(username=username, email=email, password=password)
    print('Superuser created from environment.')
elif not user.is_superuser:
    raise ImproperlyConfigured('Superuser username belongs to a regular account.')
else:
    print('Existing superuser preserved; credentials unchanged.')
PY

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
