"""Settings base — comuns a todos os ambientes."""

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from celery.schedules import crontab
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="inseguro-troque-em-producao")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # terceiros
    "rest_framework",
    "django_filters",
    "django_celery_beat",
    "django_prometheus",
    "corsheaders",
    "drf_spectacular",
    # apps do sistema
    "core",
    "projetos",
    "chamados",
    "documentacao",
    "apontamentos",
    "relatorios",
    "busca",
    "almoxarifado",
    "integracoes",
    "web",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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
                "web.context.shell",
            ],
        },
    },
]


def _database_from_url(url: str) -> dict:
    p = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": p.path.lstrip("/"),
        "USER": p.username,
        "PASSWORD": p.password,
        "HOST": p.hostname,
        "PORT": p.port or 5432,
        "CONN_MAX_AGE": 60,
    }


DATABASES = {
    "default": _database_from_url(
        config("DATABASE_URL", default="postgres://postgres:postgres@localhost:5432/sistema_interno")
    )
}

AUTH_USER_MODEL = "core.User"
LOGIN_URL = "/entrar/"
LOGIN_REDIRECT_URL = "/tarefas/"
LOGOUT_REDIRECT_URL = "/entrar/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Anexos: máximo 20 MB
ANEXO_TAMANHO_MAXIMO_BYTES = 20 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.PaginacaoPadrao",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.UserRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {"user": "1000/hour", "busca": "60/min", "integracao": "600/min"},
    "EXCEPTION_HANDLER": "core.exceptions.tratar_excecao",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sistema Interno Life Laboral — API",
    "DESCRIPTION": "Chamados, horas, documentação, almoxarifado, projetos e integrações.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# Front-end desacoplado / sistemas externos: origens liberadas via variável de ambiente
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")
# Sem Redis (ex.: plano free do Render): tarefas rodam de forma síncrona e o cache fica em memória.
# SLA vencido e alertas continuam funcionando; só o agendamento periódico (beat) fica parado.
SEM_REDIS = not REDIS_URL
CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = REDIS_URL or None
CELERY_TASK_ALWAYS_EAGER = SEM_REDIS
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "sla-vencimentos": {"task": "chamados.verificar_sla", "schedule": crontab(minute="*/15")},
    "reentregar-eventos": {"task": "integracoes.reentregar_pendentes", "schedule": crontab(minute="*/5")},
    "alertas-repostos": {"task": "almoxarifado.resolver_alertas_repostos", "schedule": crontab(hour=7, minute=0)},
    "estoque-resumo-diario": {"task": "almoxarifado.resumo_diario", "schedule": crontab(hour=7, minute=30)},
}

CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
        if SEM_REDIS
        else {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
    )
}

# Cache da matriz de permissões (segundos)
PERMISSOES_CACHE_SEGUNDOS = 60
# Feriado muda uma vez por ano; a invalidação é por signal, então o TTL é só rede de segurança.
FERIADOS_CACHE_SEGUNDOS = 60 * 60 * 24

EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="sistema@lifelaboral.local")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
