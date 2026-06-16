from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_config", "0003_systemnotice"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemnotice",
            name="importance",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "普通"), (2, "重要"), (3, "紧急")],
                db_index=True,
                default=1,
                verbose_name="重要程度",
            ),
        ),
        migrations.AddField(
            model_name="systemnotice",
            name="is_pinned",
            field=models.BooleanField(db_index=True, default=False, verbose_name="置顶"),
        ),
        migrations.AddField(
            model_name="systemnotice",
            name="link_url",
            field=models.URLField(blank=True, max_length=500, verbose_name="跳转链接"),
        ),
        migrations.AddField(
            model_name="systemnotice",
            name="notice_type",
            field=models.CharField(
                choices=[
                    ("GENERAL", "普通通知"),
                    ("BUSINESS", "业务通知"),
                    ("MAINTENANCE", "系统维护"),
                    ("POLICY", "政策公告"),
                ],
                db_index=True,
                default="GENERAL",
                max_length=30,
                verbose_name="通知类型",
            ),
        ),
        migrations.AlterModelOptions(
            name="systemnotice",
            options={
                "ordering": ["-is_pinned", "-importance", "-updated_at"],
                "verbose_name": "系统通知",
                "verbose_name_plural": "系统通知",
            },
        ),
    ]
