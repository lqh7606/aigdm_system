from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0003_assessment_traceability"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="riskassessment",
            options={
                "ordering": ["-created_at"],
                "permissions": [("run_risk_assessment", "Can run risk assessment")],
                "verbose_name": "风险评估",
                "verbose_name_plural": "风险评估",
            },
        ),
    ]
