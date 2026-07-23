"""Base settings for Vidalys Pay."""
import os
from pathlib import Path

import environ

env = environ.Env(
    DEBUG=(bool, False),
    APP_NAME=(str, "Vidalys Pay"),
    LOG_LEVEL=(str, "INFO"),
    INVITATION_EXPIRATION_HOURS=(int, 24),
    SELLER_SESSION_DAYS=(int, 30),
    WORKER_POLL_SECONDS=(int, 3),
    MAX_NOTIFICATION_ATTEMPTS=(int, 5),
    OUTBOX_STALE_LOCK_SECONDS=(int, 600),
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

environ.Env.read_env(os.path.join(BASE_DIR, ".env"), override=False)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
APP_NAME = env("APP_NAME")
APP_BASE_URL = env("APP_BASE_URL", default="http://localhost:8000")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.admin_panel",
    "apps.sellers",
    "apps.payment_links",
    "apps.boletos",
    "apps.webhooks",
    "apps.notifications",
    "apps.integrations.pagarme",
    "apps.integrations.evolution",
    "apps.integrations.n8n",
    "apps.audit",
    "apps.shipping",
    "apps.freight",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.sellers.middleware.SellerSessionMiddleware",
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
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgresql://vidalys_pay:vidalys_pay@localhost:5432/vidalys_pay"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Session
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "vidalys_seller_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 2592000  # 30 days

# CSRF
CSRF_COOKIE_HTTPONLY = True

# DRF
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

# Vidalys Pay specific
INVITATION_EXPIRATION_HOURS = env.int("INVITATION_EXPIRATION_HOURS")
SELLER_SESSION_DAYS = env.int("SELLER_SESSION_DAYS")
INVITATION_TOKEN_PEPPER = env("INVITATION_TOKEN_PEPPER", default="")
API_KEY_PEPPER = env("API_KEY_PEPPER", default="")
WORKER_POLL_SECONDS = env.int("WORKER_POLL_SECONDS")
MAX_NOTIFICATION_ATTEMPTS = env.int("MAX_NOTIFICATION_ATTEMPTS")
OUTBOX_STALE_LOCK_SECONDS = env.int("OUTBOX_STALE_LOCK_SECONDS")
BOLETO_MANAGER_WHATSAPP_PHONES = env.list(
    "BOLETO_MANAGER_WHATSAPP_PHONES",
    default=[],
)
BOLETO_NOTIFY_CUSTOMER_ON_PAID = env.bool(
    "BOLETO_NOTIFY_CUSTOMER_ON_PAID",
    default=False,
)
BOLETO_NOTIFY_CUSTOMER_ON_CANCELED = env.bool(
    "BOLETO_NOTIFY_CUSTOMER_ON_CANCELED",
    default=False,
)
BOLETO_REMINDERS_ENABLED = env.bool("BOLETO_REMINDERS_ENABLED", default=True)
BOLETO_REMINDER_DAYS = tuple(
    sorted(
        {
            int(value)
            for value in env.list("BOLETO_REMINDER_DAYS", default=["3", "0", "-1"])
        },
        reverse=True,
    )
)
BOLETO_REMINDER_SCAN_SECONDS = env.int(
    "BOLETO_REMINDER_SCAN_SECONDS",
    default=3600,
)
BOLETO_REMINDER_TIME_ZONE = env(
    "BOLETO_REMINDER_TIME_ZONE",
    default="America/Sao_Paulo",
)
BOLETO_REMINDER_WHATSAPP_ENABLED = env.bool(
    "BOLETO_REMINDER_WHATSAPP_ENABLED",
    default=True,
)
BOLETO_REMINDER_NOTIFY_CUSTOMER = env.bool(
    "BOLETO_REMINDER_NOTIFY_CUSTOMER",
    default=False,
)

# Web Push (VAPID)
WEBPUSH_VAPID_PUBLIC_KEY = env("WEBPUSH_VAPID_PUBLIC_KEY", default="")
WEBPUSH_VAPID_PRIVATE_KEY = env("WEBPUSH_VAPID_PRIVATE_KEY", default="")
WEBPUSH_VAPID_SUBJECT = env("WEBPUSH_VAPID_SUBJECT", default="mailto:contato@vidalys.com.br")

# Pagar.me
PAGARME_BASE_URL = env("PAGARME_BASE_URL", default="https://api.pagar.me/core/v5")
PAGARME_CREDENTIAL = env("PAGARME_CREDENTIAL", default="")
PAGARME_SECRET_KEY = env("PAGARME_SECRET_KEY", default="")  # deprecated, use PAGARME_CREDENTIAL
PAGARME_CONNECT_TIMEOUT_SECONDS = env.int("PAGARME_CONNECT_TIMEOUT_SECONDS", default=5)
PAGARME_READ_TIMEOUT_SECONDS = env.int("PAGARME_READ_TIMEOUT_SECONDS", default=20)
PAGARME_WEBHOOK_AUTH_MODE = env("PAGARME_WEBHOOK_AUTH_MODE", default="basic")
PAGARME_WEBHOOK_BASIC_AUTH_USER = env("PAGARME_WEBHOOK_BASIC_AUTH_USER", default="")
PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD = env("PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD", default="")

# CNPJ lookup (BrasilAPI)
CNPJ_LOOKUP_BASE_URL = env(
    "CNPJ_LOOKUP_BASE_URL",
    default="https://brasilapi.com.br/api/cnpj/v1",
)
CNPJ_LOOKUP_CONNECT_TIMEOUT_SECONDS = env.int(
    "CNPJ_LOOKUP_CONNECT_TIMEOUT_SECONDS",
    default=5,
)
CNPJ_LOOKUP_READ_TIMEOUT_SECONDS = env.int(
    "CNPJ_LOOKUP_READ_TIMEOUT_SECONDS",
    default=10,
)
CNPJ_LOOKUP_USER_AGENT = env(
    "CNPJ_LOOKUP_USER_AGENT",
    default="Vidalys-Pay-CNPJ/1.0",
)

# Evolution API
EVOLUTION_API_URL = env("EVOLUTION_API_URL", default="")
EVOLUTION_API_KEY = env("EVOLUTION_API_KEY", default="")
EVOLUTION_INSTANCE = env("EVOLUTION_INSTANCE", default="")

# Correios CWS â€” freight calculation
CORREIOS_ENABLED = env.bool("CORREIOS_ENABLED", default=False)
CORREIOS_USUARIO = env("CORREIOS_USUARIO", default="")
CORREIOS_CODIGO_ACESSO = env("CORREIOS_CODIGO_ACESSO", default="")
CORREIOS_CARTAO_POSTAGEM = env("CORREIOS_CARTAO_POSTAGEM", default="")
CORREIOS_CONTRATO = env("CORREIOS_CONTRATO", default="")
CORREIOS_DR = env("CORREIOS_DR", default="")
CORREIOS_CNPJ = env("CORREIOS_CNPJ", default="")
CORREIOS_CEP_ORIGEM = env("CORREIOS_CEP_ORIGEM", default="")
CORREIOS_PAC_PRODUCT_CODE = env("CORREIOS_PAC_PRODUCT_CODE", default="03298")
CORREIOS_SEDEX_PRODUCT_CODE = env("CORREIOS_SEDEX_PRODUCT_CODE", default="03220")
CORREIOS_CONNECT_TIMEOUT_SECONDS = env.int("CORREIOS_CONNECT_TIMEOUT_SECONDS", default=5)
CORREIOS_READ_TIMEOUT_SECONDS = env.int("CORREIOS_READ_TIMEOUT_SECONDS", default=15)
CORREIOS_TOKEN_CACHE_MARGIN_SECONDS = env.int("CORREIOS_TOKEN_CACHE_MARGIN_SECONDS", default=300)
CORREIOS_ALLOW_ESTIMATE_FALLBACK = env.bool("CORREIOS_ALLOW_ESTIMATE_FALLBACK", default=False)
CORREIOS_DEFAULT_LENGTH_CM = env.int("CORREIOS_DEFAULT_LENGTH_CM", default=20)
CORREIOS_DEFAULT_WIDTH_CM = env.int("CORREIOS_DEFAULT_WIDTH_CM", default=20)
CORREIOS_DEFAULT_HEIGHT_CM = env.int("CORREIOS_DEFAULT_HEIGHT_CM", default=20)
CORREIOS_DIAS_ADICIONAIS = env.int("CORREIOS_DIAS_ADICIONAIS", default=0)
