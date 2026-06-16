from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("followups", "0001_initial"),
        ("labs", "0002_traceable_lab_values_and_ogtt_confirmation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="followupchain",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "待随访"),
                    ("BOOKED", "已预约"),
                    ("IN_PROGRESS", "执行中"),
                    ("WAIT_DOCTOR_CONFIRM", "待医生确认"),
                    ("CONTINUE_TRACKING", "继续跟踪"),
                    ("PLANNED_NEXT", "已计划下次随访"),
                    ("WAIT_ACTIVATE", "待激活"),
                    ("OVERDUE", "逾期"),
                    ("TRANSFER_COMPLETED", "转诊完成"),
                    ("LOST_CONFIRMED", "失访确认"),
                    ("CANCELLED", "取消"),
                    ("ACTIVE", "进行中"),
                    ("CLOSED", "已关闭"),
                ],
                default="WAIT_ACTIVATE",
                max_length=30,
                verbose_name="状态",
            ),
        ),
        migrations.AddField(
            model_name="followupchain",
            name="dedup_active_record",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_followup_chain",
                to="maternal_records.maternalrecord",
                verbose_name="活跃链路去重键",
            ),
        ),
        migrations.AddField(
            model_name="followupchain",
            name="last_ogtt_outcome",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="labs.ogttoutcome",
                verbose_name="最近OGTT结局",
            ),
        ),
        migrations.AddField(
            model_name="followupchain",
            name="last_assessment_ids_json",
            field=models.JSONField(blank=True, default=list, verbose_name="关联评估ID"),
        ),
        migrations.AddField(
            model_name="followupchain",
            name="next_followup_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="下次随访时间"),
        ),
        migrations.AlterField(
            model_name="followuptask",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "待处理"),
                    ("BOOKED", "已预约"),
                    ("IN_PROGRESS", "执行中"),
                    ("WAIT_DOCTOR_CONFIRM", "待医生确认"),
                    ("DONE", "已完成"),
                    ("CANCELLED", "已取消"),
                    ("OVERDUE", "已逾期"),
                ],
                default="PENDING",
                max_length=30,
                verbose_name="状态",
            ),
        ),
        migrations.AddField(
            model_name="followuptask",
            name="task_type",
            field=models.CharField(default="FOLLOWUP", max_length=40, verbose_name="任务类型"),
        ),
        migrations.AddField(
            model_name="systemreminder",
            name="reminder_type",
            field=models.CharField(
                choices=[
                    ("DUE", "到期提醒"),
                    ("OVERDUE", "逾期提醒"),
                    ("DOCTOR_CONFIRM", "医生确认"),
                    ("OGTT_RETURN", "OGTT回收"),
                ],
                default="DUE",
                max_length=40,
                verbose_name="提醒类型",
            ),
        ),
        migrations.AlterField(
            model_name="systemreminder",
            name="status",
            field=models.CharField(
                choices=[("PENDING", "待提醒"), ("SENT", "已提醒"), ("HANDLED", "已处理"), ("CANCELLED", "已取消")],
                default="PENDING",
                max_length=30,
                verbose_name="状态",
            ),
        ),
        migrations.AddField(
            model_name="systemreminder",
            name="handled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
                verbose_name="处理人",
            ),
        ),
        migrations.AddField(
            model_name="systemreminder",
            name="handled_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="处理时间"),
        ),
    ]
