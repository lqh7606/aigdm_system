from django.core.management.base import BaseCommand, CommandError

from system_config.model_lifecycle import validate_model_version
from system_config.models import ModelVersion


class Command(BaseCommand):
    help = "验证模型版本；依赖、结构和试推理通过后进入待启用状态。"

    def add_arguments(self, parser):
        parser.add_argument("version_code")

    def handle(self, *args, **options):
        try:
            version = ModelVersion.objects.get(version_code=options["version_code"])
        except ModelVersion.DoesNotExist as exc:
            raise CommandError("未找到模型版本。") from exc

        try:
            validate_model_version(version)
        except Exception as exc:
            raise CommandError(f"模型验证失败：{exc}") from exc

        version.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(f"{version.version_code} 当前状态为 {version.get_status_display()}：{version.status_message}")
        )

