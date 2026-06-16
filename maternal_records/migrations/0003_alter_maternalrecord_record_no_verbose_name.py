from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maternal_records", "0002_maternalrecord_current_weight_kg_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="maternalrecord",
            name="record_no",
            field=models.CharField(max_length=80, unique=True, verbose_name="院内就诊号"),
        ),
    ]
