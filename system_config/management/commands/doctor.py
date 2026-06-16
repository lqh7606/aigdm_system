from django.core.management.base import BaseCommand, CommandError

from system_config.deployment import build_deployment_report


class Command(BaseCommand):
    help = "检查 AIGDM 部署配置、数据库、迁移、目录、模型和管理员状态。"

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="存在失败项时返回非零退出码。")
        parser.add_argument("--allow-sqlite", action="store_true", help="允许 SQLite 作为数据库。")

    def handle(self, *args, **options):
        report = build_deployment_report(allow_sqlite=options["allow_sqlite"])
        self.stdout.write(f"配置文件：{report['env_path']}")
        self.stdout.write(f"当前数据库：{report['database']['engine']} / {report['database']['name']}")
        self.stdout.write("")

        for item in report["checks"]:
            style = self.style.SUCCESS
            if item["state"] == "warning":
                style = self.style.WARNING
            elif item["state"] == "error":
                style = self.style.ERROR
            self.stdout.write(style(f"[{item['state_label']}] {item['name']}：{item['message']}"))
            if item["suggestion"]:
                self.stdout.write(f"  建议：{item['suggestion']}")

        self.stdout.write("")
        self.stdout.write(report["restart_required_note"])

        if options["strict"] and report["has_error"]:
            raise CommandError("部署检查未通过，请先处理失败项。")
