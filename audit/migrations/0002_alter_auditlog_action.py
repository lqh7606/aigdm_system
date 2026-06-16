from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
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
                ],
                max_length=40,
                verbose_name="操作",
            ),
        ),
    ]
