from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("system_config", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RiskAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("engine_type", models.CharField(choices=[("FULL_MODEL", "Full model"), ("DEGRADED_MODEL", "Degraded model"), ("RULE_ONLY", "Rule only"), ("EXCLUDED", "Excluded")], max_length=30)),
                ("assessment_status", models.CharField(default="DONE", max_length=30)),
                ("risk_probability", models.FloatField(blank=True, null=True)),
                ("risk_level", models.CharField(blank=True, max_length=20)),
                ("result_json", models.JSONField(blank=True, default=dict)),
                ("model_trace_json", models.JSONField(blank=True, default=dict)),
                ("degradation_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("model_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="system_config.modelversion")),
            ],
            options={
                "db_table": "t_risk_prediction",
                "ordering": ["-created_at"],
            },
        ),
    ]

