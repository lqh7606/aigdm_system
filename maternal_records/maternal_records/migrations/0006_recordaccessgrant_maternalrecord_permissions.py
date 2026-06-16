from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0002_userprofile_department_head_role"),
        ("maternal_records", "0005_fieldsource_trace_and_manual_correction"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="maternalrecord",
            options={
                "ordering": ["-updated_at"],
                "permissions": [("supplement_whitelist_fields", "Can supplement whitelist fields")],
                "verbose_name": "孕产妇档案",
                "verbose_name_plural": "孕产妇档案",
            },
        ),
        migrations.CreateModel(
            name="RecordAccessGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "grant_type",
                    models.CharField(
                        choices=[("USER", "指定用户"), ("DEPARTMENT", "指定科室"), ("ROLE", "指定角色")],
                        max_length=30,
                        verbose_name="授权类型",
                    ),
                ),
                ("role", models.CharField(blank=True, max_length=30, verbose_name="授权角色")),
                ("reason", models.CharField(blank=True, max_length=300, verbose_name="授权原因")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maternal_record_access_grants",
                        to="accounts.department",
                        verbose_name="授权科室",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="granted_maternal_record_access",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="授权人",
                    ),
                ),
                (
                    "record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_grants",
                        to="maternal_records.maternalrecord",
                        verbose_name="孕妇档案",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maternal_record_access_grants",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="授权用户",
                    ),
                ),
            ],
            options={
                "verbose_name": "孕妇档案授权",
                "verbose_name_plural": "孕妇档案授权",
                "db_table": "t_record_access_grant",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="recordaccessgrant",
            index=models.Index(fields=["record", "is_active"], name="t_record_ac_record__a6074a_idx"),
        ),
        migrations.AddIndex(
            model_name="recordaccessgrant",
            index=models.Index(fields=["user", "is_active"], name="t_record_ac_user_id_a226ec_idx"),
        ),
        migrations.AddIndex(
            model_name="recordaccessgrant",
            index=models.Index(fields=["department", "role", "is_active"], name="t_record_ac_departm_1e7b62_idx"),
        ),
    ]
