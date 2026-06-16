from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=80, unique=True, verbose_name="模板编码")),
                ("name", models.CharField(max_length=120, verbose_name="模板名称")),
                (
                    "file_format",
                    models.CharField(
                        choices=[("XLSX", "Excel"), ("CSV", "CSV")],
                        default="XLSX",
                        max_length=20,
                        verbose_name="文件格式",
                    ),
                ),
                ("columns_json", models.JSONField(blank=True, default=list, verbose_name="模板字段")),
                ("sample_rows_json", models.JSONField(blank=True, default=list, verbose_name="示例数据")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={
                "verbose_name": "导入模板",
                "verbose_name_plural": "导入模板",
                "db_table": "t_import_template",
                "ordering": ["-is_active", "code"],
            },
        ),
    ]
