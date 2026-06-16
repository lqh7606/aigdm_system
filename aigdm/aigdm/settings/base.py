import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


def load_dotenv_defaults(env_path):
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv_defaults(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("AIGDM_SECRET_KEY", "change-before-production")
DEBUG = os.environ.get("AIGDM_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("AIGDM_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "common",
    "accounts",
    "maternal_records",
    "labs",
    "integrations",
    "system_config",
    "risk",
    "followups",
    "audit",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.RequireLoginMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aigdm.urls"

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
                "accounts.permissions.permission_context",
            ],
        },
    },
]

WSGI_APPLICATION = "aigdm.wsgi.application"

if os.environ.get("AIGDM_DB_ENGINE") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("AIGDM_DB_NAME", "aigdm"),
            "USER": os.environ.get("AIGDM_DB_USER", "aigdm"),
            "PASSWORD": os.environ.get("AIGDM_DB_PASSWORD", ""),
            "HOST": os.environ.get("AIGDM_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("AIGDM_DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("AIGDM_STATIC_ROOT", BASE_DIR / "staticfiles"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

MODEL_DIR = Path(os.environ.get("AIGDM_MODEL_DIR", BASE_DIR / "model_files"))
IMPORT_DIR = Path(os.environ.get("AIGDM_IMPORT_DIR", BASE_DIR / "import_files"))
BACKUP_DIR = Path(os.environ.get("AIGDM_BACKUP_DIR", BASE_DIR / "backups"))
MODEL_REGISTRY_TTL_SECONDS = int(os.environ.get("AIGDM_MODEL_REGISTRY_TTL_SECONDS", "5"))
MODEL_TIMEOUT_SECONDS = int(os.environ.get("AIGDM_MODEL_TIMEOUT_SECONDS", "10"))

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

