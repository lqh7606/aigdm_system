from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0002_importtemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="importtemplate",
            name="template_kind",
            field=models.CharField(
                choices=[("MATERNAL_RECORD", "孕产妇档案"), ("LAB_RESULT", "检验数据")],
                default="MATERNAL_RECORD",
                max_length=30,
                verbose_name="模板类型",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="import_kind",
            field=models.CharField(
                choices=[("MATERNAL_RECORD", "孕产妇档案"), ("LAB_RESULT", "检验数据")],
                default="MATERNAL_RECORD",
                max_length=30,
                verbose_name="导入类型",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="skipped_rows",
            field=models.PositiveIntegerField(default=0, verbose_name="跳过行数"),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="overwritten_rows",
            field=models.PositiveIntegerField(default=0, verbose_name="覆盖行数"),
        ),
    ]
