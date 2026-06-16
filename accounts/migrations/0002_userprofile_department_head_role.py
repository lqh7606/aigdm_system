from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("DOCTOR", "医生"),
                    ("NURSE", "护士"),
                    ("DEPARTMENT_HEAD", "科室主任"),
                    ("MANAGER", "医务管理"),
                    ("ADMIN", "系统管理员"),
                ],
                default="DOCTOR",
                max_length=30,
                verbose_name="角色",
            ),
        ),
    ]
