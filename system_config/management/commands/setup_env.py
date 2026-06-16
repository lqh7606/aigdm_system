import getpass
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from system_config.deployment import (
    default_env_path,
    default_env_values,
    read_env_file,
    test_mysql_config,
    write_env_file,
)


class Command(BaseCommand):
    help = "交互式生成或更新 AIGDM 本机 .env 部署配置。"

    def add_arguments(self, parser):
        parser.add_argument("--env-file", default=str(default_env_path()), help="要写入的 .env 文件路径。")
        parser.add_argument("--non-interactive", action="store_true", help="使用命令行参数直接生成配置。")
        parser.add_argument("--skip-db-check", action="store_true", help="跳过 MySQL 连通性测试。")
        parser.add_argument("--db-engine", choices=["mysql", "sqlite"], help="数据库类型。")
        parser.add_argument("--db-host", help="MySQL 地址。")
        parser.add_argument("--db-port", help="MySQL 端口。")
        parser.add_argument("--db-name", help="数据库名。")
        parser.add_argument("--db-user", help="数据库用户名。")
        parser.add_argument("--db-password", help="数据库密码。")
        parser.add_argument("--model-dir", help="模型目录。")
        parser.add_argument("--import-dir", help="导入目录。")
        parser.add_argument("--backup-dir", help="备份目录。")
        parser.add_argument("--static-root", help="静态文件目录。")
        parser.add_argument("--allowed-hosts", help="允许访问的主机名列表。")
        parser.add_argument("--admin-username", help="系统管理员用户名。")

    def _prompt(self, label, default="", secret=False):
        if secret:
            suffix = "（留空保持当前值）" if default else ""
            value = getpass.getpass(f"{label}{suffix}: ")
        else:
            suffix = f" [{default}]" if default else ""
            value = input(f"{label}{suffix}: ").strip()
        return value or default

    def _value(self, options, option_name, key, values, label, secret=False):
        provided = options.get(option_name)
        if provided is not None:
            return provided
        if options["non_interactive"]:
            return values.get(key, "")
        return self._prompt(label, values.get(key, ""), secret=secret)

    def handle(self, *args, **options):
        env_path = Path(options["env_file"])
        values = default_env_values()
        values.update(read_env_file(env_path))

        values["AIGDM_DB_ENGINE"] = self._value(options, "db_engine", "AIGDM_DB_ENGINE", values, "数据库类型 mysql/sqlite")
        values["AIGDM_DB_HOST"] = self._value(options, "db_host", "AIGDM_DB_HOST", values, "MySQL 地址")
        values["AIGDM_DB_PORT"] = self._value(options, "db_port", "AIGDM_DB_PORT", values, "MySQL 端口")
        values["AIGDM_DB_NAME"] = self._value(options, "db_name", "AIGDM_DB_NAME", values, "数据库名")
        values["AIGDM_DB_USER"] = self._value(options, "db_user", "AIGDM_DB_USER", values, "数据库用户名")
        values["AIGDM_DB_PASSWORD"] = self._value(options, "db_password", "AIGDM_DB_PASSWORD", values, "数据库密码", secret=True)
        values["AIGDM_MODEL_DIR"] = self._value(options, "model_dir", "AIGDM_MODEL_DIR", values, "模型目录")
        values["AIGDM_IMPORT_DIR"] = self._value(options, "import_dir", "AIGDM_IMPORT_DIR", values, "导入目录")
        values["AIGDM_BACKUP_DIR"] = self._value(options, "backup_dir", "AIGDM_BACKUP_DIR", values, "备份目录")
        values["AIGDM_STATIC_ROOT"] = self._value(options, "static_root", "AIGDM_STATIC_ROOT", values, "静态文件目录")
        values["AIGDM_ALLOWED_HOSTS"] = self._value(options, "allowed_hosts", "AIGDM_ALLOWED_HOSTS", values, "允许访问的主机")
        values["AIGDM_ADMIN_USERNAME"] = self._value(options, "admin_username", "AIGDM_ADMIN_USERNAME", values, "系统管理员用户名")

        if values["AIGDM_DB_ENGINE"] == "mysql" and not options["skip_db_check"]:
            ok, message = test_mysql_config(values)
            if not ok:
                raise CommandError(message)
            self.stdout.write(self.style.SUCCESS(message))

        write_env_file(env_path, values)
        self.stdout.write(self.style.SUCCESS(f"已写入本机配置：{env_path}"))
        self.stdout.write("下一步建议运行：python manage.py doctor")
