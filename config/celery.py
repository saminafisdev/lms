import os
from pathlib import Path
from celery import Celery
import environ

# Load .env file so Celery picks up DJANGO_SETTINGS_MODULE and all other vars
_base_dir = Path(__file__).resolve().parent.parent
environ.Env.read_env(_base_dir / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("zahra")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.autodiscover_tasks(["config"])
