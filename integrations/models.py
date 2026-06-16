from django.db import models


class IntegrationSource(models.Model):
    class SourceKind(models.TextChoices):
        HIS = "HIS", "HIS/EMR"
        LIS = "LIS", "LIS"
        EXCEL = "EXCEL", "Excel导入"
        MANUAL = "MANUAL", "手工录入"

    code = models.CharField("接入源编码", max_length=50, unique=True)
    name = models.CharField("接入源名称", max_length=120)
    source_kind = models.CharField("接入类型", max_length=30, choices=SourceKind.choices)
    adapter_path = models.CharField("适配器路径", max_length=200, default="integrations.adapters.MockAdapter")
    is_demo = models.BooleanField("演示源", default=False)
    is_active = models.BooleanField("启用", default=True)
    config_json = models.JSONField("配置", default=dict, blank=True)
    auth_config_json = models.JSONField("认证配置", default=dict, blank=True)
    unit_rules_json = models.JSONField("单位换算规则", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_integration_source"
        ordering = ["code"]
        verbose_name = "接入源"
        verbose_name_plural = "接入源"

    def __str__(self):
        return self.name


class IntegrationTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待执行"
        RUNNING = "RUNNING", "执行中"
        SUCCESS = "SUCCESS", "成功"
        FAILED = "FAILED", "失败"

    source = models.ForeignKey(IntegrationSource, verbose_name="接入源", on_delete=models.CASCADE)
    task_type = models.CharField("任务类型", max_length=60, default="PULL")
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    pulled_count = models.PositiveIntegerField("读取数量", default=0)
    error_message = models.TextField("错误信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_integration_task"
        ordering = ["-created_at"]
        verbose_name = "接入任务"
        verbose_name_plural = "接入任务"

    def __str__(self):
        return f"{self.source} - {self.get_status_display()}"


class FieldMapping(models.Model):
    source = models.ForeignKey(IntegrationSource, verbose_name="接入源", on_delete=models.CASCADE, related_name="mappings")
    source_field = models.CharField("来源字段", max_length=120)
    target_model = models.CharField("目标模型", max_length=80)
    target_field = models.CharField("目标字段", max_length=120)
    required = models.BooleanField("必填", default=False)
    source_unit = models.CharField("来源单位", max_length=30, blank=True)
    target_unit = models.CharField("目标单位", max_length=30, blank=True)
    transform_rule_json = models.JSONField("转换规则", default=dict, blank=True)
    condition_rule_json = models.JSONField("条件必填规则", default=dict, blank=True)

    class Meta:
        db_table = "t_field_mapping"
        unique_together = ("source", "source_field", "target_model", "target_field")
        verbose_name = "字段映射"
        verbose_name_plural = "字段映射"

    def __str__(self):
        return f"{self.source_field} -> {self.target_model}.{self.target_field}"


class ImportTemplate(models.Model):
    class TemplateKind(models.TextChoices):
        MATERNAL_RECORD = "MATERNAL_RECORD", "孕产妇档案"
        LAB_RESULT = "LAB_RESULT", "检验数据"

    class FileFormat(models.TextChoices):
        XLSX = "XLSX", "Excel"
        CSV = "CSV", "CSV"

    code = models.CharField("模板编码", max_length=80, unique=True)
    name = models.CharField("模板名称", max_length=120)
    template_kind = models.CharField("模板类型", max_length=30, choices=TemplateKind.choices, default=TemplateKind.MATERNAL_RECORD)
    file_format = models.CharField("文件格式", max_length=20, choices=FileFormat.choices, default=FileFormat.XLSX)
    columns_json = models.JSONField("模板字段", default=list, blank=True)
    sample_rows_json = models.JSONField("示例数据", default=list, blank=True)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_import_template"
        ordering = ["-is_active", "code"]
        verbose_name = "导入模板"
        verbose_name_plural = "导入模板"

    def __str__(self):
        return self.name


class ImportBatch(models.Model):
    class ImportKind(models.TextChoices):
        MATERNAL_RECORD = "MATERNAL_RECORD", "孕产妇档案"
        LAB_RESULT = "LAB_RESULT", "检验数据"

    class Status(models.TextChoices):
        PRECHECK = "PRECHECK", "预检查"
        IMPORTED = "IMPORTED", "已导入"
        FAILED = "FAILED", "失败"

    source = models.ForeignKey(IntegrationSource, verbose_name="接入源", null=True, blank=True, on_delete=models.SET_NULL)
    import_kind = models.CharField("导入类型", max_length=30, choices=ImportKind.choices, default=ImportKind.MATERNAL_RECORD)
    file_name = models.CharField("文件名", max_length=260)
    status = models.CharField("状态", max_length=30, choices=Status.choices, default=Status.PRECHECK)
    total_rows = models.PositiveIntegerField("总行数", default=0)
    success_rows = models.PositiveIntegerField("成功行数", default=0)
    failed_rows = models.PositiveIntegerField("失败行数", default=0)
    skipped_rows = models.PositiveIntegerField("跳过行数", default=0)
    overwritten_rows = models.PositiveIntegerField("覆盖行数", default=0)
    error_json = models.JSONField("错误明细", default=list, blank=True)
    source_metadata_json = models.JSONField("来源元数据", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_import_batch"
        ordering = ["-created_at"]
        verbose_name = "导入批次"
        verbose_name_plural = "导入批次"
        permissions = [
            ("upload_excel_import", "Can upload Excel import"),
        ]

    def __str__(self):
        return f"{self.file_name} - {self.get_status_display()}"


