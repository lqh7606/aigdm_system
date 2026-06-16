from django.conf import settings
from django.db import models


class MaternalRecord(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "在管"
        MERGED = "MERGED", "已合并"
        ARCHIVED = "ARCHIVED", "已归档"

    class SourceType(models.TextChoices):
        MANUAL = "MANUAL", "手工录入"
        MANUAL_CORRECTION = "MANUAL_CORRECTION", "人工修正"
        HIS = "HIS", "HIS"
        EMR = "EMR", "电子病历"
        LIS = "LIS", "LIS"
        EXCEL = "EXCEL", "Excel导入"

    record_no = models.CharField("院内就诊号", max_length=80, unique=True)
    name = models.CharField("姓名", max_length=80)
    id_card_masked = models.CharField("证件号脱敏", max_length=80, blank=True)
    id_card_hash = models.CharField("证件号哈希", max_length=128, blank=True, db_index=True)
    phone_masked = models.CharField("电话脱敏", max_length=60, blank=True)
    age = models.PositiveSmallIntegerField("年龄", null=True, blank=True)
    expected_delivery_date = models.DateField("预产期", null=True, blank=True)
    current_weight_kg = models.DecimalField("当前体重kg", max_digits=5, decimal_places=1, null=True, blank=True)
    systolic_bp = models.PositiveSmallIntegerField("收缩压", null=True, blank=True)
    diastolic_bp = models.PositiveSmallIntegerField("舒张压", null=True, blank=True)
    department = models.ForeignKey(
        "accounts.Department",
        verbose_name="管理科室",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    primary_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="责任医生",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    height_cm = models.DecimalField("身高cm", max_digits=5, decimal_places=1, null=True, blank=True)
    pre_preg_weight_kg = models.DecimalField("孕前体重kg", max_digits=5, decimal_places=1, null=True, blank=True)
    pre_preg_bmi = models.DecimalField("孕前BMI", max_digits=5, decimal_places=2, null=True, blank=True)
    gestational_week = models.DecimalField("当前孕周", max_digits=4, decimal_places=1, null=True, blank=True)
    last_menstrual_period = models.DateField("末次月经", null=True, blank=True)
    pregnancy_count = models.PositiveSmallIntegerField("孕次", null=True, blank=True)
    birth_count = models.PositiveSmallIntegerField("产次", null=True, blank=True)
    multiple_pregnancy = models.BooleanField("多胎妊娠", default=False)
    fetal_count = models.PositiveSmallIntegerField("胎数", default=1)
    diabetes_before_pregnancy = models.BooleanField("妊娠前糖尿病", default=False)
    status = models.CharField("档案状态", max_length=30, choices=Status.choices, default=Status.ACTIVE)
    source_type = models.CharField("主要来源", max_length=30, choices=SourceType.choices, default=SourceType.MANUAL)
    merged_into = models.ForeignKey(
        "self",
        verbose_name="合并到",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_records",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_maternal_record"
        ordering = ["-updated_at"]
        verbose_name = "孕产妇档案"
        verbose_name_plural = "孕产妇档案"
        permissions = [
            ("supplement_whitelist_fields", "Can supplement whitelist fields"),
        ]

    def __str__(self):
        return f"{self.name}（{self.record_no}）"


class MergeRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待审批"
        APPROVED = "APPROVED", "已合并"
        REJECTED = "REJECTED", "已驳回"

    source_record = models.ForeignKey(
        MaternalRecord,
        verbose_name="来源档案",
        on_delete=models.CASCADE,
        related_name="merge_as_source",
    )
    target_record = models.ForeignKey(
        MaternalRecord,
        verbose_name="目标档案",
        on_delete=models.CASCADE,
        related_name="merge_as_target",
    )
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.PENDING)
    reason = models.CharField("合并原因", max_length=300)
    approved_by = models.ForeignKey(
        "auth.User",
        verbose_name="审批人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    approved_at = models.DateTimeField("审批时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_maternal_merge_record"
        ordering = ["-created_at"]
        verbose_name = "档案合并记录"
        verbose_name_plural = "档案合并记录"

    def __str__(self):
        return f"{self.source_record} -> {self.target_record}"


class RecordAccessGrant(models.Model):
    class GrantType(models.TextChoices):
        USER = "USER", "指定用户"
        DEPARTMENT = "DEPARTMENT", "指定科室"
        ROLE = "ROLE", "指定角色"

    record = models.ForeignKey(
        MaternalRecord,
        verbose_name="孕妇档案",
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    grant_type = models.CharField("授权类型", max_length=30, choices=GrantType.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="授权用户",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="maternal_record_access_grants",
    )
    department = models.ForeignKey(
        "accounts.Department",
        verbose_name="授权科室",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="maternal_record_access_grants",
    )
    role = models.CharField("授权角色", max_length=30, blank=True)
    reason = models.CharField("授权原因", max_length=300, blank=True)
    is_active = models.BooleanField("启用", default=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="授权人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_maternal_record_access",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_record_access_grant"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["record", "is_active"]),
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["department", "role", "is_active"]),
        ]
        verbose_name = "孕妇档案授权"
        verbose_name_plural = "孕妇档案授权"

    def __str__(self):
        target = self.user or self.department or self.role or self.grant_type
        return f"{self.record} -> {target}"


class RecordDeletionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待审批"
        APPROVED = "APPROVED", "已批准"
        REJECTED = "REJECTED", "已驳回"

    class ApprovalAction(models.TextChoices):
        ARCHIVE = "ARCHIVE", "归档"
        DELETE = "DELETE", "物理删除"

    record = models.ForeignKey(
        MaternalRecord,
        verbose_name="孕产妇档案",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deletion_requests",
    )
    record_snapshot = models.JSONField("档案快照", default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="申请人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maternal_record_deletion_requests",
    )
    reason = models.TextField("删除原因")
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True)
    approval_action = models.CharField("审批动作", max_length=30, choices=ApprovalAction.choices, blank=True)
    approval_comment = models.TextField("审批意见", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="审批人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_maternal_record_deletion_requests",
    )
    requested_at = models.DateTimeField("申请时间", auto_now_add=True)
    reviewed_at = models.DateTimeField("审批时间", null=True, blank=True)

    class Meta:
        db_table = "t_record_deletion_request"
        ordering = ["-requested_at"]
        verbose_name = "档案删除申请"
        verbose_name_plural = "档案删除申请"

    def __str__(self):
        record_label = self.record_snapshot.get("record_no") or self.record_id or "未知档案"
        return f"{record_label} - {self.get_status_display()}"


class FieldSource(models.Model):
    object_type = models.CharField("对象类型", max_length=80, default="maternal_record")
    field_name = models.CharField("字段名", max_length=120)
    maternal_record = models.ForeignKey(
        MaternalRecord,
        verbose_name="孕产妇档案",
        on_delete=models.CASCADE,
        related_name="field_sources",
    )
    source_type = models.CharField("来源类型", max_length=30, choices=MaternalRecord.SourceType.choices)
    source_system = models.CharField("来源系统", max_length=80, blank=True)
    source_record_id = models.CharField("来源记录ID", max_length=120, blank=True)
    source_ref = models.CharField("来源标识", max_length=200, blank=True)
    raw_value = models.CharField("原始值", max_length=500, blank=True)
    normalized_value = models.CharField("标准化值", max_length=500, blank=True)
    confidence = models.DecimalField("可信度", max_digits=4, decimal_places=2, default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="更新人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    captured_at = models.DateTimeField("采集时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_field_source"
        ordering = ["-captured_at"]
        verbose_name = "字段来源"
        verbose_name_plural = "字段来源"

    def __str__(self):
        return f"{self.maternal_record_id}:{self.field_name}:{self.get_source_type_display()}"


