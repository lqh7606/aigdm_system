from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_alter_auditlog_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="request_id",
            field=models.CharField(blank=True, db_index=True, max_length=80, verbose_name="请求ID"),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="before_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="变更前"),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="after_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="变更后"),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="success",
            field=models.BooleanField(db_index=True, default=True, verbose_name="是否成功"),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="failure_reason",
            field=models.TextField(blank=True, verbose_name="失败原因"),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="confirmation_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="二次确认"),
        ),
    ]
