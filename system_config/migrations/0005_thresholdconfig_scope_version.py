from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_userprofile_department_head_role"),
        ("system_config", "0004_systemnotice_layering"),
    ]

    operations = [
        migrations.AlterField(
            model_name="thresholdconfig",
            name="code",
            field=models.CharField(db_index=True, max_length=80, verbose_name="阈值编码"),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="category",
            field=models.CharField(
                choices=[
                    ("LAB_ABNORMAL", "检验异常"),
                    ("OGTT_DIAGNOSIS", "OGTT诊断"),
                    ("MODEL_RULE", "模型规则"),
                ],
                db_index=True,
                default="LAB_ABNORMAL",
                max_length=40,
                verbose_name="阈值分类",
            ),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="version",
            field=models.CharField(default="1.0", max_length=40, verbose_name="版本号"),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="scope_type",
            field=models.CharField(
                choices=[("GLOBAL", "全局"), ("DEPARTMENT", "科室")],
                db_index=True,
                default="GLOBAL",
                max_length=30,
                verbose_name="作用范围",
            ),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="accounts.department",
                verbose_name="适用科室",
            ),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="unit_rule_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="单位换算规则"),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="active_from",
            field=models.DateTimeField(blank=True, null=True, verbose_name="生效时间"),
        ),
        migrations.AddField(
            model_name="thresholdconfig",
            name="retired_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="停用时间"),
        ),
        migrations.AddIndex(
            model_name="thresholdconfig",
            index=models.Index(fields=["code", "category", "scope_type", "is_active"], name="t_threshold_code_cat_scope_idx"),
        ),
        migrations.AddIndex(
            model_name="thresholdconfig",
            index=models.Index(fields=["department", "code", "is_active"], name="t_threshold_dept_code_idx"),
        ),
        migrations.AddConstraint(
            model_name="thresholdconfig",
            constraint=models.UniqueConstraint(
                fields=("code", "category", "scope_type", "department", "version"),
                name="uk_threshold_scope_version",
            ),
        ),
    ]
