from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integrations", "0004_source_mapping_traceability"),
        ("labs", "0001_initial"),
        ("system_config", "0005_thresholdconfig_scope_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="labresult",
            name="raw_value",
            field=models.CharField(blank=True, max_length=80, verbose_name="原始值"),
        ),
        migrations.AddField(
            model_name="labresult",
            name="raw_unit",
            field=models.CharField(blank=True, max_length=30, verbose_name="原始单位"),
        ),
        migrations.AddField(
            model_name="labresult",
            name="standard_value",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name="标准化值"),
        ),
        migrations.AddField(
            model_name="labresult",
            name="standard_unit",
            field=models.CharField(default="mmol/L", max_length=30, verbose_name="标准单位"),
        ),
        migrations.AddField(
            model_name="labresult",
            name="source_task",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="integrations.integrationtask",
                verbose_name="同步任务",
            ),
        ),
        migrations.AddField(
            model_name="labresult",
            name="import_batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="integrations.importbatch",
                verbose_name="导入批次",
            ),
        ),
        migrations.AddField(
            model_name="labresult",
            name="threshold_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="system_config.thresholdconfig",
                verbose_name="命中阈值配置",
            ),
        ),
        migrations.AddField(
            model_name="labresult",
            name="threshold_snapshot_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="阈值快照"),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="confirmation_status",
            field=models.CharField(
                choices=[("PENDING", "待医生确认"), ("CONFIRMED", "已确认"), ("REJECTED", "已驳回")],
                db_index=True,
                default="PENDING",
                max_length=30,
                verbose_name="医生确认状态",
            ),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="confirmed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
                verbose_name="确认医生",
            ),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="确认时间"),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="threshold_config_ids_json",
            field=models.JSONField(blank=True, default=list, verbose_name="阈值配置ID"),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="triggered_thresholds_json",
            field=models.JSONField(blank=True, default=list, verbose_name="触发阈值"),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="source_type",
            field=models.CharField(default="SYSTEM", max_length=30, verbose_name="来源"),
        ),
        migrations.AddField(
            model_name="ogttoutcome",
            name="source_ref",
            field=models.CharField(blank=True, max_length=200, verbose_name="来源标识"),
        ),
    ]
