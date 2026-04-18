#!/bin/sh
set -e

ROLE="${APP_ROLE:-web}"

case "$ROLE" in
  celery)
    echo "Starting Celery worker..."
    exec celery -A config worker --loglevel=info
    ;;
  beat)
    echo "Starting Celery beat..."
    exec celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
  web)
    echo "Running migrations..."
    python manage.py migrate --noinput

    echo "Collecting static files..."
    python manage.py collectstatic --noinput

    echo "Starting Gunicorn..."
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-120}" \
      --access-logfile - \
      --error-logfile -
    ;;
  *)
    echo "Unknown APP_ROLE: $ROLE. Use web, celery, or beat."
    exit 1
    ;;
esac
