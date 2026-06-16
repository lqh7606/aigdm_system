from django.conf import settings
from django.db import models


class Department(models.Model):
    class DepartmentType(models.TextChoices):
        OBSTETRICS = "OBSTETRICS", "产科"
        COMMUNITY = "COMMUNITY", "基层门诊"
        LAB = "LAB", "检验科"
        ADMIN = "ADMIN", "管理部门"

    code = models.CharField("科室编码", max_length=50, unique=True)
    name = models.CharField("科室名称", max_length=120)
    department_type = models.CharField("科室类型", max_length=30, choices=DepartmentType.choices)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_department"
        ordering = ["code"]
        verbose_name = "科室"
        verbose_name_plural = "科室"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    class Role(models.TextChoices):
        DOCTOR = "DOCTOR", "医生"
        NURSE = "NURSE", "护士"
        DEPARTMENT_HEAD = "DEPARTMENT_HEAD", "科室主任"
        MANAGER = "MANAGER", "医务管理"
        ADMIN = "ADMIN", "系统管理员"

    class DataScope(models.TextChoices):
        SELF = "SELF", "本人"
        DEPARTMENT = "DEPARTMENT", "本科室"
        HOSPITAL = "HOSPITAL", "全院"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="用户", on_delete=models.CASCADE)
    role = models.CharField("角色", max_length=30, choices=Role.choices, default=Role.DOCTOR)
    department = models.ForeignKey(
        Department,
        verbose_name="所属科室",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    data_scope = models.CharField("数据范围", max_length=30, choices=DataScope.choices, default=DataScope.DEPARTMENT)
    mobile = models.CharField("联系电话", max_length=30, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "t_user_profile"
        verbose_name = "用户档案"
        verbose_name_plural = "用户档案"

    def __str__(self):
        return f"{self.user} - {self.get_role_display()}"


