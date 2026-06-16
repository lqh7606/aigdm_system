from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("maternal_records", "0003_alter_maternalrecord_record_no_verbose_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecordDeletionRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("record_snapshot", models.JSONField(blank=True, default=dict, verbose_name="档案快照")),
                ("reason", models.TextField(verbose_name="删除原因")),
                (
                    "status",
                    models.CharField(
                        choices=[("PENDING", "待审批"), ("APPROVED", "已批准"), ("REJECTED", "已驳回")],
                        db_index=True,
                        default="PENDING",
                        max_length=30,
                        verbose_name="状态",
                    ),
                ),
                (
                    "approval_action",
                    models.CharField(
                        blank=True,
                        choices=[("ARCHIVE", "归档"), ("DELETE", "物理删除")],
                        max_length=30,
                        verbose_name="审批动作",
                    ),
                ),
                ("approval_comment", models.TextField(blank=True, verbose_name="审批意见")),
                ("requested_at", models.DateTimeField(auto_now_add=True, verbose_name="申请时间")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="审批时间")),
                (
                    "record",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deletion_requests",
                        to="maternal_records.maternalrecord",
                        verbose_name="孕产妇档案",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="maternal_record_deletion_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="申请人",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_maternal_record_deletion_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="审批人",
                    ),
                ),
            ],
            options={
                "verbose_name": "档案删除申请",
                "verbose_name_plural": "档案删除申请",
                "db_table": "t_record_deletion_request",
                "ordering": ["-requested_at"],
            },
        ),
    ]
