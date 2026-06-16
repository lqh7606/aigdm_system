from django.conf import settings
from django.db import models


class FollowupChain(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待随访"
        BOOKED = "BOOKED", "已预约"
        IN_PROGRESS = "IN_PROGRESS", "执行中"
        WAIT_DOCTOR_CONFIRM = "WAIT_DOCTOR_CONFIRM", "待医生确认"
        CONTINUE_TRACKING = "CONTINUE_TRACKING", "继续跟踪"
        PLANNED_NEXT = "PLANNED_NEXT", "已计划下次随访"
        WAIT_ACTIVATE = "WAIT_ACTIVATE", "待激活"
        OVERDUE = "OVERDUE", "逾期"
        TRANSFER_COMPLETED = "TRANSFER_COMPLETED", "转诊完成"
        LOST_CONFIRMED = "LOST_CONFIRMED", "失访确认"
        CANCELLED = "CANCELLED", "取消"
        # Legacy values kept for installed demo databases.
        ACTIVE = "ACTIVE", "进行中"
        CLOSED = "CLOSED", "已关闭"

    maternal_record = models.ForeignKey(
        "maternal_records.MaternalRecord",
        verbose_name="孕产妇档案",
        on_delete=models.CASCADE,
        related_name="followup_chains",
    )
    risk_assessment = models.ForeignKey(
        "risk.RiskAssessment",
        verbose_name="触发评估",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="followup_chains",
    )
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.WAIT_ACTIVATE)
    dedup_active_record = models.OneToOneField(
        "maternal_records.MaternalRecord",
        verbose_name="活跃链路去重键",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_followup_chain",
    )
    last_ogtt_outcome = models.ForeignKey(
        "labs.OGTTOutcome",
        verbose_name="最近OGTT结局",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    last_assessment_ids_json = models.JSONField("关联评估ID", default=list, blank=True)
    reason = models.CharField("触发原因", max_length=200, blank=True)
    next_followup_at = models.DateTimeField("下次随访时间", null=True, blank=True)
    activated_at = models.DateTimeField("激活时间", null=True, blank=True)
    closed_at = models.DateTimeField("关闭时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_followup_chain"
        ordering = ["-created_at"]
        verbose_name = "随访链"
        verbose_name_plural = "随访链"

    def __str__(self):
        return f"{self.maternal_record} - {self.get_status_display()}"


class FollowupTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待处理"
        BOOKED = "BOOKED", "已预约"
        IN_PROGRESS = "IN_PROGRESS", "执行中"
        WAIT_DOCTOR_CONFIRM = "WAIT_DOCTOR_CONFIRM", "待医生确认"
        DONE = "DONE", "已完成"
        CANCELLED = "CANCELLED", "已取消"
        OVERDUE = "OVERDUE", "已逾期"

    chain = models.ForeignKey(FollowupChain, verbose_name="随访链", on_delete=models.CASCADE, related_name="tasks")
    task_name = models.CharField("任务名称", max_length=120)
    task_type = models.CharField("任务类型", max_length=40, default="FOLLOWUP")
    due_at = models.DateTimeField("截止时间", null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="负责人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.PENDING)
    result_text = models.TextField("处理结果", blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_followup_task"
        ordering = ["status", "due_at", "-created_at"]
        verbose_name = "随访任务"
        verbose_name_plural = "随访任务"
        permissions = [
            ("execute_followup_task", "Can execute followup task"),
            ("confirm_followup_outcome", "Can confirm followup outcome"),
        ]

    def __str__(self):
        return f"{self.task_name} - {self.get_status_display()}"


class InterventionRecord(models.Model):
    class InterventionType(models.TextChoices):
        DIET = "DIET", "饮食指导"
        EXERCISE = "EXERCISE", "运动指导"
        REFERRAL = "REFERRAL", "转诊建议"
        EDUCATION = "EDUCATION", "健康宣教"

    chain = models.ForeignKey(FollowupChain, verbose_name="随访链", on_delete=models.CASCADE, related_name="interventions")
    intervention_type = models.CharField("干预类型", max_length=30, choices=InterventionType.choices)
    content = models.TextField("干预内容")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="记录人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_intervention_record"
        ordering = ["-created_at"]
        verbose_name = "干预记录"
        verbose_name_plural = "干预记录"

    def __str__(self):
        return f"{self.get_intervention_type_display()} - {self.chain}"


class SystemReminder(models.Model):
    class ReminderType(models.TextChoices):
        DUE = "DUE", "到期提醒"
        OVERDUE = "OVERDUE", "逾期提醒"
        DOCTOR_CONFIRM = "DOCTOR_CONFIRM", "医生确认"
        OGTT_RETURN = "OGTT_RETURN", "OGTT回收"

    class Status(models.TextChoices):
        PENDING = "PENDING", "待提醒"
        SENT = "SENT", "已提醒"
        HANDLED = "HANDLED", "已处理"
        CANCELLED = "CANCELLED", "已取消"

    task = models.ForeignKey(FollowupTask, verbose_name="随访任务", on_delete=models.CASCADE, related_name="reminders")
    reminder_type = models.CharField("提醒类型", max_length=40, choices=ReminderType.choices, default=ReminderType.DUE)
    remind_at = models.DateTimeField("提醒时间")
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.PENDING)
    message = models.CharField("提醒内容", max_length=300)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="处理人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    handled_at = models.DateTimeField("处理时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_system_reminder"
        ordering = ["remind_at"]
        verbose_name = "系统提醒"
        verbose_name_plural = "系统提醒"

    def __str__(self):
        return self.message


