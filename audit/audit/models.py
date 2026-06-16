from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        VIEW = "VIEW", "查看"
        CREATE = "CREATE", "创建"
        UPDATE = "UPDATE", "修改"
        EXPORT = "EXPORT", "导出"
        ACTIVATE_MODEL = "ACTIVATE_MODEL", "启用模型"
        IMPORT = "IMPORT", "导入"
        DELETE_REQUEST = "DELETE_REQUEST", "删除申请"
        DELETE_APPROVE = "DELETE_APPROVE", "删除批准"
        DELETE_REJECT = "DELETE_REJECT", "删除驳回"
        ACCESS_DENIED = "ACCESS_DENIED", "权限拒绝"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="用户",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField("操作", max_length=40, choices=Action.choices)
    target_type = models.CharField("对象类型", max_length=80)
    target_id = models.CharField("对象ID", max_length=80, blank=True)
    summary = models.CharField("摘要", max_length=300)
    ip_address = models.GenericIPAddressField("IP地址", null=True, blank=True)
    request_id = models.CharField("请求ID", max_length=80, blank=True, db_index=True)
    before_json = models.JSONField("变更前", default=dict, blank=True)
    after_json = models.JSONField("变更后", default=dict, blank=True)
    success = models.BooleanField("是否成功", default=True, db_index=True)
    failure_reason = models.TextField("失败原因", blank=True)
    confirmation_json = models.JSONField("二次确认", default=dict, blank=True)
    metadata_json = models.JSONField("扩展信息", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "t_audit_log"
        ordering = ["-created_at"]
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"
        permissions = [
            ("export_audit_log", "Can export audit log"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.target_type} {self.target_id}"


