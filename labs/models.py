from django.conf import settings
from django.db import models


class LabResult(models.Model):
    class ItemCode(models.TextChoices):
        FPG = "FPG", "空腹血糖"
        OGTT_1H = "OGTT_1H", "OGTT 1小时血糖"
        OGTT_2H = "OGTT_2H", "OGTT 2小时血糖"
        TG = "TG", "甘油三酯"
        HDL_C = "HDL_C", "高密度脂蛋白"
        GGT = "GGT", "γ-谷氨酰转肽酶"
        ALB = "ALB", "白蛋白"
        WBC = "WBC", "白细胞计数"
        TSH = "TSH", "促甲状腺激素"
        MONO_ABS = "MONO_ABS", "单核细胞绝对值"
        CHE = "CHE", "胆碱脂酶"
        ALT = "ALT", "谷丙转氨酶"
        AST = "AST", "谷草转氨酶"
        RBC = "RBC", "红细胞计数"
        HCT = "HCT", "红细胞压积"
        APTT = "APTT", "活化部分凝血酶原时间"
        CREA = "CREA", "肌酐"
        ALP = "ALP", "碱性磷酸酶"
        LYM_ABS = "LYM_ABS", "淋巴细胞绝对值"
        UREA = "UREA", "尿素"
        UA = "UA", "尿酸"
        TT = "TT", "凝血酶时间"
        FIB = "FIB", "纤维蛋白原"
        HGB = "HGB", "血红蛋白"
        PLT = "PLT", "血小板计数"
        FT4 = "FT4", "游离甲状腺素"
        FT3 = "FT3", "游离三碘甲状腺原氨酸"
        DBIL = "DBIL", "直接胆红素"
        NEUT_ABS = "NEUT_ABS", "中性粒细胞绝对值"
        TC = "TC", "总胆固醇"
        TBIL = "TBIL", "总胆红素"
        TBA = "TBA", "总胆汁酸"
        TP = "TP", "总蛋白"

    class ConfirmationStatus(models.TextChoices):
        PENDING = "PENDING", "待确认"
        CONFIRMED = "CONFIRMED", "已确认"
        REJECTED = "REJECTED", "已排除"

    maternal_record = models.ForeignKey(
        "maternal_records.MaternalRecord",
        verbose_name="孕产妇档案",
        on_delete=models.CASCADE,
        related_name="lab_results",
    )
    item_code = models.CharField("项目编码", max_length=40, choices=ItemCode.choices)
    item_name = models.CharField("项目名称", max_length=120)
    value = models.DecimalField("检验值", max_digits=8, decimal_places=3)
    unit = models.CharField("单位", max_length=30, default="mmol/L")
    raw_value = models.CharField("原始值", max_length=80, blank=True)
    raw_unit = models.CharField("原始单位", max_length=30, blank=True)
    standard_value = models.DecimalField("标准化值", max_digits=10, decimal_places=3, null=True, blank=True)
    standard_unit = models.CharField("标准单位", max_length=30, default="mmol/L")
    sampled_at = models.DateTimeField("采样时间", null=True, blank=True)
    reported_at = models.DateTimeField("报告时间", null=True, blank=True)
    source_type = models.CharField("来源", max_length=30, default="MANUAL")
    source_ref = models.CharField("来源标识", max_length=200, blank=True)
    source_task = models.ForeignKey(
        "integrations.IntegrationTask",
        verbose_name="同步任务",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    import_batch = models.ForeignKey(
        "integrations.ImportBatch",
        verbose_name="导入批次",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    is_abnormal = models.BooleanField("异常", default=False)
    threshold_config = models.ForeignKey(
        "system_config.ThresholdConfig",
        verbose_name="命中阈值配置",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    threshold_snapshot_json = models.JSONField("阈值快照", default=dict, blank=True)
    confirmation_status = models.CharField(
        "确认状态",
        max_length=30,
        choices=ConfirmationStatus.choices,
        default=ConfirmationStatus.PENDING,
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="确认人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    confirmed_at = models.DateTimeField("确认时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_lab_result"
        ordering = ["-reported_at", "-created_at"]
        indexes = [
            models.Index(fields=["maternal_record", "item_code"]),
            models.Index(fields=["confirmation_status", "is_abnormal"]),
        ]
        verbose_name = "检验结果"
        verbose_name_plural = "检验结果"
        permissions = [
            ("confirm_lab_abnormal", "Can confirm abnormal lab result"),
        ]

    def __str__(self):
        return f"{self.maternal_record} {self.item_name}={self.value}{self.unit}"


class OGTTOutcome(models.Model):
    class Outcome(models.TextChoices):
        NORMAL = "NORMAL", "正常"
        GDM = "GDM", "妊娠期糖尿病"
        INCOMPLETE = "INCOMPLETE", "资料不完整"

    class ConfirmationStatus(models.TextChoices):
        PENDING = "PENDING", "待医生确认"
        CONFIRMED = "CONFIRMED", "已确认"
        REJECTED = "REJECTED", "已驳回"

    maternal_record = models.OneToOneField(
        "maternal_records.MaternalRecord",
        verbose_name="孕产妇档案",
        on_delete=models.CASCADE,
        related_name="ogtt_outcome",
    )
    fasting_value = models.DecimalField("空腹血糖", max_digits=8, decimal_places=3, null=True, blank=True)
    one_hour_value = models.DecimalField("1小时血糖", max_digits=8, decimal_places=3, null=True, blank=True)
    two_hour_value = models.DecimalField("2小时血糖", max_digits=8, decimal_places=3, null=True, blank=True)
    outcome = models.CharField("结局", max_length=30, choices=Outcome.choices, default=Outcome.INCOMPLETE)
    confirmation_status = models.CharField(
        "医生确认状态",
        max_length=30,
        choices=ConfirmationStatus.choices,
        default=ConfirmationStatus.PENDING,
        db_index=True,
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="确认医生",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    confirmed_at = models.DateTimeField("确认时间", null=True, blank=True)
    threshold_json = models.JSONField("阈值快照", default=dict, blank=True)
    threshold_config_ids_json = models.JSONField("阈值配置ID", default=list, blank=True)
    triggered_thresholds_json = models.JSONField("触发阈值", default=list, blank=True)
    source_type = models.CharField("来源", max_length=30, default="SYSTEM")
    source_ref = models.CharField("来源标识", max_length=200, blank=True)
    calculated_at = models.DateTimeField("判定时间", auto_now=True)

    class Meta:
        db_table = "t_ogtt_outcome"
        verbose_name = "OGTT结局"
        verbose_name_plural = "OGTT结局"
        permissions = [
            ("confirm_ogtt_outcome", "Can confirm OGTT outcome"),
        ]

    def __str__(self):
        return f"{self.maternal_record} - {self.get_outcome_display()}"


