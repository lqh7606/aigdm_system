from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0002_alter_riskassessment_options_and_more"),
        ("system_config", "0005_thresholdconfig_scope_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="riskassessment",
            name="full_model_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="full_model_assessments",
                to="system_config.modelversion",
                verbose_name="完整模型版本",
            ),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="degraded_model_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="degraded_model_assessments",
                to="system_config.modelversion",
                verbose_name="降级模型版本",
            ),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="rule_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="system_config.ruleconfig",
                verbose_name="规则版本",
            ),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="pre_exclusion_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="risk_assessments",
                to="risk.preexclusionrecord",
                verbose_name="前置排除记录",
            ),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="threshold_snapshot_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="阈值快照"),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="used_fields_json",
            field=models.JSONField(blank=True, default=list, verbose_name="使用字段"),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="missing_fields_json",
            field=models.JSONField(blank=True, default=list, verbose_name="缺失字段"),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="abnormal_confirmation_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="异常确认摘要"),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="trace_request_id",
            field=models.CharField(blank=True, db_index=True, max_length=80, verbose_name="追踪请求ID"),
        ),
    ]
