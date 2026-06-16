from django.db import models

from system_config.models import ModelVersion


MISSING_FIELD_LABELS = {
    "age": "年龄",
    "gestational_week": "当前孕周",
    "pre_preg_bmi": "孕前BMI",
    "MOTHER_AGE": "年龄",
    "GESTATIONAL_WEEK": "当前孕周",
    "PRE_PREG_BMI": "孕前BMI",
    "FPG": "空腹血糖",
    "TG": "甘油三酯",
    "OGTT_1H": "OGTT 1小时血糖",
    "OGTT_2H": "OGTT 2小时血糖",
}


def format_degradation_reason(reason, missing_fields=None):
    reason = reason or ""
    missing_fields = missing_fields or []
    if reason == "必填字段缺失" and missing_fields:
        labels = [MISSING_FIELD_LABELS.get(str(field), str(field)) for field in missing_fields]
        return f"{reason}：{'、'.join(labels)}"
    return reason or "-"


class RiskAssessment(models.Model):
    class EngineType(models.TextChoices):
        FULL_MODEL = "FULL_MODEL", "完整模型"
        DEGRADED_MODEL = "DEGRADED_MODEL", "降级模型"
        RULE_ONLY = "RULE_ONLY", "规则评估"
        EXCLUDED = "EXCLUDED", "已排除"

    class RiskLevel(models.TextChoices):
        LOW = "LOW", "低危"
        MEDIUM = "MEDIUM", "中危"
        HIGH = "HIGH", "高危"

    maternal_record = models.ForeignKey(
        "maternal_records.MaternalRecord",
        verbose_name="孕产妇档案",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="risk_assessments",
    )
    assessment_no = models.CharField("评估编号", max_length=80, blank=True)
    engine_type = models.CharField("评估引擎", max_length=30, choices=EngineType.choices)
    assessment_status = models.CharField("评估状态", max_length=30, default="DONE")
    model_version = models.ForeignKey(ModelVersion, verbose_name="模型版本", null=True, blank=True, on_delete=models.SET_NULL)
    full_model_version = models.ForeignKey(
        ModelVersion,
        verbose_name="完整模型版本",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="full_model_assessments",
    )
    degraded_model_version = models.ForeignKey(
        ModelVersion,
        verbose_name="降级模型版本",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="degraded_model_assessments",
    )
    rule_config = models.ForeignKey(
        "system_config.RuleConfig",
        verbose_name="规则版本",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    pre_exclusion_record = models.ForeignKey(
        "risk.PreExclusionRecord",
        verbose_name="前置排除记录",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="risk_assessments",
    )
    risk_probability = models.FloatField("风险概率", null=True, blank=True)
    risk_level = models.CharField("风险等级", max_length=20, choices=RiskLevel.choices, blank=True)
    result_json = models.JSONField("评估结果", default=dict, blank=True)
    model_trace_json = models.JSONField("模型追踪", default=dict, blank=True)
    data_completeness_json = models.JSONField("完整性检查", default=dict, blank=True)
    threshold_snapshot_json = models.JSONField("阈值快照", default=dict, blank=True)
    used_fields_json = models.JSONField("使用字段", default=list, blank=True)
    missing_fields_json = models.JSONField("缺失字段", default=list, blank=True)
    abnormal_confirmation_json = models.JSONField("异常确认摘要", default=dict, blank=True)
    trace_request_id = models.CharField("追踪请求ID", max_length=80, blank=True, db_index=True)
    degradation_reason = models.TextField("降级原因", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_risk_prediction"
        ordering = ["-created_at"]
        verbose_name = "风险评估"
        verbose_name_plural = "风险评估"
        permissions = [
            ("run_risk_assessment", "Can run risk assessment"),
        ]

    def __str__(self):
        return self.assessment_no or f"风险评估 {self.pk}"

    @property
    def display_degradation_reason(self):
        return format_degradation_reason(self.degradation_reason, self.missing_fields_json)

    @property
    def display_model_version(self):
        if self.full_model_version_id:
            return self.full_model_version.version_code
        if self.degraded_model_version_id:
            return self.degraded_model_version.version_code
        if self.model_version_id:
            return self.model_version.version_code
        if self.rule_config_id:
            return self.rule_config.code
        return "-"


class PreExclusionRecord(models.Model):
    class Decision(models.TextChoices):
        NOT_EXCLUDED = "NOT_EXCLUDED", "未排除"
        EXCLUDED = "EXCLUDED", "已排除"

    maternal_record = models.ForeignKey(
        "maternal_records.MaternalRecord",
        verbose_name="孕产妇档案",
        on_delete=models.CASCADE,
        related_name="pre_exclusion_records",
    )
    decision = models.CharField("排除结论", max_length=30, choices=Decision.choices)
    reason = models.CharField("原因", max_length=200, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_pre_exclusion_record"
        ordering = ["-created_at"]
        verbose_name = "预排除记录"
        verbose_name_plural = "预排除记录"

    def __str__(self):
        return f"{self.maternal_record} - {self.get_decision_display()}"

