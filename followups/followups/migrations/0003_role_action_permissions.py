from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("followups", "0002_state_machine_dedup_trace"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="followuptask",
            options={
                "ordering": ["status", "due_at", "-created_at"],
                "permissions": [
                    ("execute_followup_task", "Can execute followup task"),
                    ("confirm_followup_outcome", "Can confirm followup outcome"),
                ],
                "verbose_name": "随访任务",
                "verbose_name_plural": "随访任务",
            },
        ),
    ]
