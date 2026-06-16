from django.core.management.base import BaseCommand, CommandError

from system_config.model_lifecycle import (
    DEFAULT_RELEASE_DIR,
    DEFAULT_SOURCE_MODEL,
    DEFAULT_VERSION_CODE,
    ModelLifecycleError,
    create_release_from_source,
)


class Command(BaseCommand):
    help = "复制初始可信PKL模型到不可变发布目录并登记版本。"

    def add_arguments(self, parser):
        parser.add_argument("--source", default=DEFAULT_SOURCE_MODEL)
        parser.add_argument("--version-code", default=DEFAULT_VERSION_CODE)
        parser.add_argument("--display-name", default="初始XGBoost GDM模型")
        parser.add_argument("--release-dir", default=DEFAULT_RELEASE_DIR)

    def handle(self, *args, **options):
        try:
            version, artifact = create_release_from_source(
                source_path=options["source"],
                version_code=options["version_code"],
                display_name=options["display_name"],
                release_dir=options["release_dir"],
            )
        except ModelLifecycleError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"模型已复制到 {artifact}"))
        self.stdout.write(self.style.SUCCESS(f"已登记模型版本 {version.version_code}，当前状态 {version.get_status_display()}"))

