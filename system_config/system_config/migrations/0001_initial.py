from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ModelVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_code", models.CharField(max_length=120, unique=True)),
                ("display_name", models.CharField(max_length=200)),
                ("model_type", models.CharField(choices=[("FULL", "Full model"), ("DEGRADED", "Degraded model")], default="FULL", max_length=20)),
                ("artifact_format", models.CharField(choices=[("PKL", "PKL"), ("JOBLIB", "Joblib"), ("ONNX", "ONNX")], default="PKL", max_length=20)),
                ("model_family", models.CharField(choices=[("XGBOOST", "XGBoost"), ("SKLEARN", "Scikit-learn"), ("UNKNOWN", "Unknown")], default="XGBOOST", max_length=30)),
                ("artifact_path", models.CharField(max_length=500)),
                ("sha256", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("VALIDATING", "Validating"), ("STAGED", "Staged"), ("PRODUCTION", "Production"), ("RETIRED", "Retired"), ("FAILED", "Failed")], db_index=True, default="DRAFT", max_length=20)),
                ("status_message", models.TextField(blank=True)),
                ("dependency_status_json", models.JSONField(blank=True, default=dict)),
                ("validation_report_json", models.JSONField(blank=True, default=dict)),
                ("manifest_json", models.JSONField(blank=True, default=dict)),
                ("feature_schema_json", models.JSONField(blank=True, default=dict)),
                ("input_schema_json", models.JSONField(blank=True, default=dict)),
                ("output_schema_json", models.JSONField(blank=True, default=dict)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("predecessor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="successors", to="system_config.modelversion")),
            ],
            options={
                "db_table": "t_model_version",
                "ordering": ["-created_at"],
            },
        ),
    ]

