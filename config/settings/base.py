import environ
from pathlib import Path
from datetime import timedelta

env = environ.Env(DEBUG=(bool, False))

BASE_DIR = Path(__file__).resolve().parent.parent.parent

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "djoser",
    "django_filters",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "taggit",
    "accounts",
    "courses",
    "certificates",
    "consultations",
    "doors",
    "books",
    "blogs",
    "orders",
    "videos",
    "email_templates",
    "reviews",
    "site_settings",
    "memberships",
    "donations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

AUTH_USER_MODEL = "accounts.User"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": 9,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("ACCESS_TOKEN_LIFETIME_MINUTES", default=60)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
    "AUTH_HEADER_TYPES": ("JWT",),
}

DJOSER = {
    "LOGIN_FIELD": "email",
    "USER_CREATE_PASSWORD_RETYPE": True,
    "SEND_ACTIVATION_EMAIL": False,
    "SERIALIZERS": {
        "user_create": "accounts.serializers.CustomUserCreateSerializer",
        "user_create_password_retype": "accounts.serializers.CustomUserCreatePasswordRetypeSerializer",
        "current_user": "accounts.serializers.CustomUserSerializer",
        "user": "accounts.serializers.CustomUserSerializer",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Zahra LMS API",
    "DESCRIPTION": "API documentation for Zahra LMS",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

TAGGIT_CASE_INSENSITIVE = True

# ---------------------------------------------------------------------------
# Bunny.net
# ---------------------------------------------------------------------------
BUNNY_STORAGE_ZONE = env("BUNNY_STORAGE_ZONE", default="")
BUNNY_STORAGE_API_KEY = env("BUNNY_STORAGE_API_KEY", default="")
BUNNY_CDN_HOSTNAME = env("BUNNY_CDN_HOSTNAME", default="")
BUNNY_STREAM_LIBRARY_ID = env.int("BUNNY_STREAM_LIBRARY_ID", default=0)
BUNNY_STREAM_API_KEY = env("BUNNY_STREAM_API_KEY", default="")

USE_BUNNY_STORAGE = env.bool("USE_BUNNY_STORAGE", default=False)

if USE_BUNNY_STORAGE:
    BUNNY_USERNAME = BUNNY_STORAGE_ZONE
    BUNNY_PASSWORD = BUNNY_STORAGE_API_KEY
    BUNNY_HOSTNAME = BUNNY_CDN_HOSTNAME.rstrip("/") + "/"
    BUNNY_REGION = env("BUNNY_REGION", default="sg")
    STORAGES = {
        "default": {
            "BACKEND": "django_bunny.storage.BunnyStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@zahraahassane.com")
DEFAULT_FROM_NAME = env("DEFAULT_FROM_NAME", default="Zahra LMS")

# ---------------------------------------------------------------------------
# Redis & Celery
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
REDIS_CACHE_URL = env("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "zahra",
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# ---------------------------------------------------------------------------
# Third-party credentials (optional in base — required overrides in prod)
# ---------------------------------------------------------------------------
SENDGRID_API_KEY = env("SENDGRID_API_KEY", default="")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
CURRENCY = "usd"
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5174")

ZOOM_ACCOUNT_ID = env("ZOOM_ACCOUNT_ID", default="")
ZOOM_CLIENT_ID = env("ZOOM_CLIENT_ID", default="")
ZOOM_CLIENT_SECRET = env("ZOOM_CLIENT_SECRET", default="")
ZOOM_HOST_EMAIL = env("ZOOM_HOST_EMAIL", default="")
