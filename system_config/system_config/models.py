from django.db import models
from django.conf import settings
from django.utils import timezone


class ModelVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        VALIDATING = "VALIDATING", "验证中"
        STAGED = "STAGED", "待启用"
        PRODUCTION = "PRODUCTION", "生产中"
        RETIRED = "RETIRED", "已停用"
        FAILED = "FAILED", "验证失败"

    class ArtifactFormat(models.TextChoices):
        PKL = "PKL", "PKL"
        JOBLIB = "JOBLIB", "Joblib"
        ONNX = "ONNX", "ONNX"

    class ModelFamily(models.TextChoices):
        XGBOOST = "XGBOOST", "XGBoost"
        SKLEARN = "SKLEARN", "Scikit-learn"
        UNKNOWN = "UNKNOWN", "未知"

    class ModelType(models.TextChoices):
        FULL = "FULL", "完整模型"
        DEGRADED = "DEGRADED", "降级模型"

    version_code = models.CharField("版本编码", max_length=120, unique=True)
    display_name = models.CharField("显示名称", max_length=200)
    model_type = models.CharField(
        "模型类型",
        max_length=20,
        choices=ModelType.choices,
        default=ModelType.FULL,
    )
    artifact_format = models.CharField(
        "文件格式",
        max_length=20,
        choices=ArtifactFormat.choices,
        default=ArtifactFormat.PKL,
    )
    model_family = models.CharField(
        "模型家族",
        max_length=30,
        choices=ModelFamily.choices,
        default=ModelFamily.XGBOOST,
    )
    artifact_path = models.CharField("文件路径", max_length=500)
    sha256 = models.CharField("SHA256", max_length=64)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    status_message = models.TextField("状态说明", blank=True)
    dependency_status_json = models.JSONField("依赖检查", default=dict, blank=True)
    validation_report_json = models.JSONField("验证报告", default=dict, blank=True)
    manifest_json = models.JSONField("发布清单", default=dict, blank=True)
    feature_schema_json = models.JSONField("特征结构", default=dict, blank=True)
    input_schema_json = models.JSONField("输入结构", default=dict, blank=True)
    output_schema_json = models.JSONField("输出结构", default=dict, blank=True)
    activated_at = models.DateTimeField("启用时间", null=True, blank=True)
    retired_at = models.DateTimeField("停用时间", null=True, blank=True)
    predecessor = models.ForeignKey(
        "self",
        verbose_name="前序版本",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="successors",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_model_version"
        ordering = ["-created_at"]
        verbose_name = "模型版本"
        verbose_name_plural = "模型版本"
        permissions = [
            ("manage_model_config", "Can manage model config"),
        ]

    def mark_failed(self, message, report=None):
        self.status = self.Status.FAILED
        self.status_message = message
        if report is not None:
            self.validation_report_json = report
        self.save(update_fields=["status", "status_message", "validation_report_json", "updated_at"])

    def activate(self):
        self.status = self.Status.PRODUCTION
        self.activated_at = timezone.now()
        self.retired_at = None
        self.save(update_fields=["status", "activated_at", "retired_at", "updated_at"])

    def retire(self):
        self.status = self.Status.RETIRED
        self.retired_at = timezone.now()
        self.save(update_fields=["status", "retired_at", "updated_at"])

    def __str__(self):
        return f"{self.version_code} ({self.status})"


class RuleConfig(models.Model):
    code = models.CharField("规则编码", max_length=80, unique=True)
    name = models.CharField("规则名称", max_length=160)
    description = models.TextField("规则说明", blank=True)
    config_json = models.JSONField("规则配置", default=dict, blank=True)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_rule_config"
        ordering = ["code"]
        verbose_name = "规则配置"
        verbose_name_plural = "规则配置"

    def __str__(self):
        return self.name


class ThresholdConfig(models.Model):
    class ThresholdCategory(models.TextChoices):
        LAB_ABNORMAL = "LAB_ABNORMAL", "检验异常"
        OGTT_DIAGNOSIS = "OGTT_DIAGNOSIS", "OGTT诊断"
        MODEL_RULE = "MODEL_RULE", "模型规则"

    class ScopeType(models.TextChoices):
        GLOBAL = "GLOBAL", "全局"
        DEPARTMENT = "DEPARTMENT", "科室"

    code = models.CharField("阈值编码", max_length=80, db_index=True)
    name = models.CharField("阈值名称", max_length=160)
    category = models.CharField(
        "阈值分类",
        max_length=40,
        choices=ThresholdCategory.choices,
        default=ThresholdCategory.LAB_ABNORMAL,
        db_index=True,
    )
    version = models.CharField("版本号", max_length=40, default="1.0")
    scope_type = models.CharField("作用范围", max_length=30, choices=ScopeType.choices, default=ScopeType.GLOBAL, db_index=True)
    department = models.ForeignKey(
        "accounts.Department",
        verbose_name="适用科室",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    value = models.DecimalField("阈值", max_digits=10, decimal_places=3)
    unit = models.CharField("单位", max_length=30, blank=True)
    applies_to = models.CharField("适用场景", max_length=120, blank=True)
    unit_rule_json = models.JSONField("单位换算规则", default=dict, blank=True)
    is_active = models.BooleanField("启用", default=True)
    active_from = models.DateTimeField("生效时间", null=True, blank=True)
    retired_at = models.DateTimeField("停用时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_threshold_config"
        ordering = ["code"]
        indexes = [
            models.Index(fields=["code", "category", "scope_type", "is_active"], name="t_threshold_code_cat_scope_idx"),
            models.Index(fields=["department", "code", "is_active"], name="t_threshold_dept_code_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "category", "scope_type", "department", "version"],
                name="uk_threshold_scope_version",
            )
        ]
        verbose_name = "阈值配置"
        verbose_name_plural = "阈值配置"

    def snapshot(self):
        return {
            "id": self.pk,
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "version": self.version,
            "scope_type": self.scope_type,
            "department_id": self.department_id,
            "value": str(self.value),
            "unit": self.unit,
            "applies_to": self.applies_to,
            "unit_rule_json": self.unit_rule_json,
            "active_from": self.active_from.isoformat() if self.active_from else None,
        }

    def __str__(self):
        return f"{self.name}={self.value}{self.unit}"


class RetentionPolicy(models.Model):
    code = models.CharField("策略编码", max_length=80, unique=True)
    name = models.CharField("策略名称", max_length=160)
    retention_days = models.PositiveIntegerField("保留天数", default=3650)
    action = models.CharField("到期动作", max_length=80, default="人工复核")
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_retention_policy"
        ordering = ["code"]
        verbose_name = "数据保留策略"
        verbose_name_plural = "数据保留策略"

    def __str__(self):
        return self.name


class SystemNotice(models.Model):
    class NoticeType(models.TextChoices):
        GENERAL = "GENERAL", "普通通知"
        BUSINESS = "BUSINESS", "业务通知"
        MAINTENANCE = "MAINTENANCE", "系统维护"
        POLICY = "POLICY", "政策公告"

    class Importance(models.IntegerChoices):
        NORMAL = 1, "普通"
        IMPORTANT = 2, "重要"
        URGENT = 3, "紧急"

    title = models.CharField("通知标题", max_length=160)
    content = models.TextField("通知内容")
    notice_type = models.CharField(
        "通知类型",
        max_length=30,
        choices=NoticeType.choices,
        default=NoticeType.GENERAL,
        db_index=True,
    )
    importance = models.PositiveSmallIntegerField(
        "重要程度",
        choices=Importance.choices,
        default=Importance.NORMAL,
        db_index=True,
    )
    is_pinned = models.BooleanField("置顶", default=False, db_index=True)
    link_url = models.URLField("跳转链接", max_length=500, blank=True)
    is_active = models.BooleanField("启用", default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="创建人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_system_notices",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="更新人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_system_notices",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_system_notice"
        ordering = ["-is_pinned", "-importance", "-updated_at"]
        verbose_name = "系统通知"
        verbose_name_plural = "系统通知"

    def __str__(self):
        return self.title

