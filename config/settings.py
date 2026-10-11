from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", cast=bool, default=False)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv(), default="localhost,127.0.0.1")
HTTPS = config("HTTPS", cast=bool, default=False)    # True em producao (atras do proxy com TLS)

if not DEBUG and (len(SECRET_KEY) < 40 or "troque" in SECRET_KEY):
    raise ImproperlyConfigured("SECRET_KEY fraca. Gere uma com: python -c \"import secrets; print(secrets.token_urlsafe(50))\"")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework.authtoken", "drf_spectacular",
    "clientes", "chamados", "estoque", "ordens", "dashboard", "api",
    "seguranca",   # por ultimo: sincroniza os perfis depois que todas as permissoes existem
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "seguranca.middleware.CabecalhosSegurancaMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "seguranca.middleware.UsuarioAtualMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "config.menu.menu",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": config("DB_NAME"), "USER": config("DB_USER"),
    "PASSWORD": config("DB_PASSWORD"), "HOST": config("DB_HOST"),
    "PORT": config("DB_PORT", default="5432"),
}}
# Cache guarda os contadores de tentativas de login e de limite de requisicoes.
# Em producao (varios processos do gunicorn) usa o banco, para todos verem os mesmos contadores.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_erp"}
          if config("CACHE_NO_BANCO", cast=bool, default=False)
          else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"          # nao e servido publicamente: anexos saem pela view com login
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- Autenticacao e senhas ----------
LOGIN_URL = "/entrar/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/entrar/"
AUTHENTICATION_BACKENDS = ["seguranca.backends.BackendComBloqueio"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",       # padrao (senhas antigas migram no proximo login)
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_MAX_FALHAS_USUARIO = 5      # falhas seguidas do mesmo usuario...
LOGIN_MAX_FALHAS_IP = 20          # ...ou do mesmo IP (escritorio inteiro atras de um IP)
LOGIN_JANELA_MINUTOS = 15         # dentro desta janela
LOGIN_BLOQUEIO_MINUTOS = 15       # bloqueiam o login por este tempo
CONFIAR_X_FORWARDED_FOR = HTTPS   # IP real vem do proxy so em producao

# ---------- Sessao e cookies ----------
SESSION_COOKIE_AGE = config("SESSAO_HORAS", cast=int, default=8) * 3600
SESSION_SAVE_EVERY_REQUEST = True          # o prazo conta a partir do ultimo uso (expira por inatividade)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = HTTPS

# ---------- HTTPS e cabecalhos ----------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if HTTPS:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000             # 1 ano
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", cast=Csv(), default="")
# HSTS preload inscreve o dominio numa lista embutida nos navegadores (dificil de desfazer):
# so ligar quando o dominio de producao for definitivo.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
CSP_CDNS = ["https://cdn.jsdelivr.net", "https://unpkg.com"]
CSP_CAMINHOS_RELAXADOS = ["/api/docs/"]

# ---------- Anexos ----------
ANEXO_TAMANHO_MAX_MB = 10

# ---------- API ----------
API_TOKEN_HORAS = config("API_TOKEN_HORAS", cast=int, default=8)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "seguranca.autenticacao.TokenComExpiracao",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle",
                                 "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "600/min", "login": "10/min"},
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Rastro - API", "VERSION": "1.0.0",
    "DESCRIPTION": "Autentique em /api/token/ (token valido por API_TOKEN_HORAS) e envie 'Authorization: Token <token>'.",
    "ENUM_NAME_OVERRIDES": {"TipoChamadoEnum": "chamados.models.Tipo"},
}

# ---------- Logs (stdout do container; nunca registrar senha ou token) ----------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"padrao": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "padrao"}},
    "loggers": {
        "seguranca": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
