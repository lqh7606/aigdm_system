from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0004_source_mapping_traceability"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="importbatch",
            options={
                "ordering": ["-created_at"],
                "permissions": [("upload_excel_import", "Can upload Excel import")],
                "verbose_name": "导入批次",
                "verbose_name_plural": "导入批次",
            },
        ),
    ]
