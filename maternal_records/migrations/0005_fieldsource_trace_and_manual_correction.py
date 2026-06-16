from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("maternal_records", "0004_recorddeletionrequest"),
    ]

    operations = [
        migrations.AlterField(
            model_name="maternalrecord",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("MANUAL", "手工录入"),
                    ("MANUAL_CORRECTION", "人工修正"),
                    ("HIS", "HIS"),
                    ("EMR", "电子病历"),
                    ("LIS", "LIS"),
                    ("EXCEL", "Excel导入"),
                ],
                default="MANUAL",
                max_length=30,
                verbose_name="主要来源",
            ),
        ),
        migrations.AddField(
            model_name="fieldsource",
            name="object_type",
            field=models.CharField(default="maternal_record", max_length=80, verbose_name="对象类型"),
        ),
        migrations.AlterField(
            model_name="fieldsource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("MANUAL", "手工录入"),
                    ("MANUAL_CORRECTION", "人工修正"),
                    ("HIS", "HIS"),
                    ("EMR", "电子病历"),
                    ("LIS", "LIS"),
                    ("EXCEL", "Excel导入"),
                ],
                max_length=30,
                verbose_name="来源类型",
            ),
        ),
        migrations.AddField(
            model_name="fieldsource",
            name="source_system",
            field=models.CharField(blank=True, max_length=80, verbose_name="来源系统"),
        ),
        migrations.AddField(
            model_name="fieldsource",
            name="source_record_id",
            field=models.CharField(blank=True, max_length=120, verbose_name="来源记录ID"),
        ),
        migrations.AddField(
            model_name="fieldsource",
            name="normalized_value",
            field=models.CharField(blank=True, max_length=500, verbose_name="标准化值"),
        ),
        migrations.AddField(
            model_name="fieldsource",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
                verbose_name="更新人",
            ),
        ),
        migrations.AddField(
            model_name="fieldsource",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="更新时间"),
        ),
    ]
