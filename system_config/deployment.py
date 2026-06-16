import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.utils import get_random_secret_key
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from .models import ModelVersion


ENV_ORDER = [
    "DJANGO_SETTINGS_MODULE",
    "AIGDM_DEBUG",
    "AIGDM_SECRET_KEY",
    "AIGDM_ALLOWED_HOSTS",
    "AIGDM_DB_ENGINE",
    "AIGDM_DB_NAME",
    "AIGDM_DB_USER",
    "AIGDM_DB_PASSWORD",
    "AIGDM_DB_HOST",
    "AIGDM_DB_PORT",
    "AIGDM_MODEL_DIR",
    "AIGDM_IMPORT_DIR",
    "AIGDM_BACKUP_DIR",
    "AIGDM_STATIC_ROOT",
    "AIGDM_MODEL_REGISTRY_TTL_SECONDS",
    "AIGDM_MODEL_TIMEOUT_SECONDS",
    "AIGDM_ADMIN_USERNAME",
]

SENSITIVE_KEYS = {"AIGDM_SECRET_KEY", "AIGDM_DB_PASSWORD"}
NON_PERSISTED_KEYS = {"AIGDM_ADMIN_PASSWORD"}


def default_env_path():
    return Path(settings.BASE_DIR) / ".env"


def default_env_values():
    base_dir = Path(settings.BASE_DIR)
    return {
        "DJANGO_SETTINGS_MODULE": "aigdm.settings.production",
        "AIGDM_DEBUG": "0",
        "AIGDM_SECRET_KEY": get_random_secret_key(),
        "AIGDM_ALLOWED_HOSTS": "127.0.0.1,localhost,aigdm.local",
        "AIGDM_DB_ENGINE": "mysql",
        "AIGDM_DB_NAME": "aigdm",
        "AIGDM_DB_USER": "aigdm",
        "AIGDM_DB_PASSWORD": "",
        "AIGDM_DB_HOST": "127.0.0.1",
        "AIGDM_DB_PORT": "3306",
        "AIGDM_MODEL_DIR": str(base_dir / "model_files"),
        "AIGDM_IMPORT_DIR": str(base_dir / "import_files"),
        "AIGDM_BACKUP_DIR": str(base_dir / "backups"),
        "AIGDM_STATIC_ROOT": str(base_dir / "staticfiles"),
        "AIGDM_MODEL_REGISTRY_TTL_SECONDS": "5",
        "AIGDM_MODEL_TIMEOUT_SECONDS": "10",
        "AIGDM_ADMIN_USERNAME": "aigdm_admin",
    }


def read_env_file(path):
    path = Path(path)
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def write_env_file(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    persisted_values = {key: value for key, value in values.items() if key not in NON_PERSISTED_KEYS}
    ordered_keys = [key for key in ENV_ORDER if key in persisted_values]
    extra_keys = sorted(key for key in persisted_values if key not in ENV_ORDER)
    lines = [
        "# AIGDM 本机部署配置",
        "# 此文件包含数据库密码和密钥，不要提交到 GitHub。",
    ]
    for key in ordered_keys + extra_keys:
        lines.append(f"{key}={persisted_values.get(key, '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def masked_value(key, value):
    if key in SENSITIVE_KEYS and value:
        return "<已隐藏>"
    return value


def test_mysql_config(values):
    try:
        import MySQLdb
    except ImportError as exc:
        return False, "当前 Python 环境未安装 mysqlclient，无法连接 MySQL。"

    try:
        connection_params = {
            "host": values.get("AIGDM_DB_HOST", "127.0.0.1"),
            "port": int(values.get("AIGDM_DB_PORT", "3306")),
            "user": values.get("AIGDM_DB_USER", "aigdm"),
            "passwd": values.get("AIGDM_DB_PASSWORD", ""),
            "db": values.get("AIGDM_DB_NAME", "aigdm"),
            "charset": "utf8mb4",
            "connect_timeout": 5,
        }
        db = MySQLdb.connect(**connection_params)
        db.close()
    except Exception as exc:
        return False, f"MySQL 连接失败：{exc}"
    return True, "MySQL 连接成功。"


def _check_migrations():
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    return len(plan)


def _add_check(checks, name, state, message, suggestion=""):
    checks.append(
        {
            "name": name,
            "state": state,
            "state_label": {"ok": "通过", "warning": "警告", "error": "失败"}[state],
            "message": message,
            "suggestion": suggestion,
        }
    )


def build_deployment_report(allow_sqlite=False):
    env_path = default_env_path()
    env_values = read_env_file(env_path)
    checks = []

    if env_path.exists():
        _add_check(checks, ".env 配置文件", "ok", f"已找到：{env_path}")
    else:
        _add_check(checks, ".env 配置文件", "error", "未找到 .env。", "运行 python manage.py setup_env 生成本机配置。")

    db_settings = connection.settings_dict
    db_engine = db_settings.get("ENGINE", "")
    if "sqlite" in db_engine and not allow_sqlite:
        _add_check(checks, "数据库配置", "error", "当前连接 SQLite，不是生产 MySQL。", "检查 .env 中 AIGDM_DB_ENGINE=mysql 是否存在。")
    else:
        _add_check(checks, "数据库配置", "ok", f"{db_engine} / {db_settings.get('NAME')}")

    database_ready = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database_ready = True
        _add_check(checks, "数据库连接", "ok", "数据库连接正常。")
    except Exception as exc:
        _add_check(checks, "数据库连接", "error", f"数据库连接失败：{exc}", "检查 MySQL 服务、账号、密码和网络。")

    if database_ready:
        try:
            pending = _check_migrations()
            if pending:
                _add_check(checks, "数据库迁移", "error", f"还有 {pending} 个迁移未应用。", "运行 python manage.py migrate。")
            else:
                _add_check(checks, "数据库迁移", "ok", "所有迁移已应用。")
        except Exception as exc:
            _add_check(checks, "数据库迁移", "error", f"迁移状态检查失败：{exc}")

    directory_items = [
        ("模型目录", settings.MODEL_DIR),
        ("导入目录", settings.IMPORT_DIR),
        ("备份目录", settings.BACKUP_DIR),
        ("静态文件目录", settings.STATIC_ROOT),
    ]
    for label, path in directory_items:
        target = Path(path)
        if target.exists():
            _add_check(checks, label, "ok", str(target))
        else:
            _add_check(checks, label, "error", f"目录不存在：{target}", f"创建目录：{target}")

    if database_ready:
        try:
            production = ModelVersion.objects.filter(status=ModelVersion.Status.PRODUCTION).first()
            if production:
                _add_check(checks, "生产模型", "ok", f"当前生产版本：{production.version_code}")
            else:
                _add_check(checks, "生产模型", "warning", "尚未启用生产模型。", "完成模型复制、验证和启用后可使用完整模型评估。")
        except Exception as exc:
            _add_check(checks, "生产模型", "warning", f"模型状态检查失败：{exc}")

        try:
            username = os.environ.get("AIGDM_ADMIN_USERNAME", "aigdm_admin")
            exists = get_user_model().objects.filter(username=username).exists()
            if exists:
                _add_check(checks, "系统管理员", "ok", f"管理员账号存在：{username}")
            else:
                _add_check(checks, "系统管理员", "error", f"管理员账号不存在：{username}", "运行 initialize_system --create-admin，并在提示中输入管理员密码。")
        except Exception as exc:
            _add_check(checks, "系统管理员", "error", f"管理员检查失败：{exc}")

    env_display = []
    for key in ENV_ORDER:
        raw_value = os.environ.get(key, env_values.get(key, ""))
        env_display.append({"key": key, "value": masked_value(key, raw_value)})

    has_error = any(item["state"] == "error" for item in checks)
    has_warning = any(item["state"] == "warning" for item in checks)
    return {
        "env_path": env_path,
        "env_exists": env_path.exists(),
        "env_values": env_display,
        "checks": checks,
        "has_error": has_error,
        "has_warning": has_warning,
        "database": {
            "engine": db_engine,
            "name": db_settings.get("NAME", ""),
            "host": db_settings.get("HOST", ""),
            "port": db_settings.get("PORT", ""),
            "user": db_settings.get("USER", ""),
        },
        "restart_required_note": "数据库、密钥、目录等启动前配置修改后，需要重启服务才会生效。",
    }
