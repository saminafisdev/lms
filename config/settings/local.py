from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# Database — SQLite for local dev
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------------------
# Debug Toolbar
# ---------------------------------------------------------------------------
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
INTERNAL_IPS = ["127.0.0.1", "10.10.13.8"]

# ---------------------------------------------------------------------------
# CORS — allow everything locally
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Email — print to console instead of sending
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Media — use local filesystem, not Bunny
# ---------------------------------------------------------------------------
USE_BUNNY_STORAGE = env.bool("USE_BUNNY_STORAGE", default=False)
