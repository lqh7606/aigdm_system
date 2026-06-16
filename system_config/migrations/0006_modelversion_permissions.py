from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("system_config", "0005_thresholdconfig_scope_version"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="modelversion",
            options={
                "ordering": ["-created_at"],
                "permissions": [("manage_model_config", "Can manage model config")],
                "verbose_name": "模型版本",
                "verbose_name_plural": "模型版本",
            },
        ),
    ]
