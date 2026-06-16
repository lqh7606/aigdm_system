from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0003_importtemplate_kind_importbatch_kind_stats"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationsource",
            name="is_demo",
            field=models.BooleanField(default=False, verbose_name="演示源"),
        ),
        migrations.AddField(
            model_name="integrationsource",
            name="auth_config_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="认证配置"),
        ),
        migrations.AddField(
            model_name="integrationsource",
            name="unit_rules_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="单位换算规则"),
        ),
        migrations.AddField(
            model_name="fieldmapping",
            name="source_unit",
            field=models.CharField(blank=True, max_length=30, verbose_name="来源单位"),
        ),
        migrations.AddField(
            model_name="fieldmapping",
            name="target_unit",
            field=models.CharField(blank=True, max_length=30, verbose_name="目标单位"),
        ),
        migrations.AddField(
            model_name="fieldmapping",
            name="transform_rule_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="转换规则"),
        ),
        migrations.AddField(
            model_name="fieldmapping",
            name="condition_rule_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="条件必填规则"),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="source_metadata_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="来源元数据"),
        ),
    ]
