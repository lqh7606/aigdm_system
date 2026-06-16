from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0003_auditlog_trace_fields"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="auditlog",
            options={
                "ordering": ["-created_at"],
                "permissions": [("export_audit_log", "Can export audit log")],
                "verbose_name": "审计日志",
                "verbose_name_plural": "审计日志",
            },
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("VIEW", "查看"),
                    ("CREATE", "创建"),
                    ("UPDATE", "修改"),
                    ("EXPORT", "导出"),
                    ("ACTIVATE_MODEL", "启用模型"),
                    ("IMPORT", "导入"),
                    ("DELETE_REQUEST", "删除申请"),
                    ("DELETE_APPROVE", "删除批准"),
                    ("DELETE_REJECT", "删除驳回"),
                    ("ACCESS_DENIED", "权限拒绝"),
                ],
                max_length=40,
                verbose_name="操作",
            ),
        ),
    ]
