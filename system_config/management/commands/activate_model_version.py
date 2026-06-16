from django.core.management.base import BaseCommand, CommandError

from system_config.model_lifecycle import ModelLifecycleError, activate_model_version
from system_config.model_runtime import ModelRegistry
from system_config.models import ModelVersion


class Command(BaseCommand):
    help = "以事务方式将待启用或已停用模型版本切换为生产版本。"

    def add_arguments(self, parser):
        parser.add_argument("version_code")

    def handle(self, *args, **options):
        try:
            version = ModelVersion.objects.get(version_code=options["version_code"])
            activated = activate_model_version(version)
        except ModelVersion.DoesNotExist as exc:
            raise CommandError("未找到模型版本。") from exc
        except ModelLifecycleError as exc:
            raise CommandError(str(exc)) from exc

        ModelRegistry.invalidate()
        self.stdout.write(self.style.SUCCESS(f"{activated.version_code} 已切换为生产版本。"))

