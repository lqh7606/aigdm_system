from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("labs", "0003_alter_labresult_item_code"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="labresult",
            options={
                "ordering": ["-reported_at", "-created_at"],
                "permissions": [("confirm_lab_abnormal", "Can confirm abnormal lab result")],
                "verbose_name": "检验结果",
                "verbose_name_plural": "检验结果",
            },
        ),
        migrations.AlterModelOptions(
            name="ogttoutcome",
            options={
                "permissions": [("confirm_ogtt_outcome", "Can confirm OGTT outcome")],
                "verbose_name": "OGTT结局",
                "verbose_name_plural": "OGTT结局",
            },
        ),
    ]
