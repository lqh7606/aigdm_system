import os
import base64
import getpass
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Department, UserProfile
from accounts.role_group_defaults import apply_default_role_group_permissions
from integrations.services import get_or_create_mock_source
from labs.models import LabResult
from labs.services import create_lab_result
from maternal_records.models import MaternalRecord
from maternal_records.services import create_or_update_record_from_payload
from risk.services import assess_maternal_record
from system_config.models import ModelVersion, RetentionPolicy, RuleConfig, ThresholdConfig


class Command(BaseCommand):
    help = "Initialize roles, departments, thresholds, rules, integration sources, and optional sample data."

    def add_arguments(self, parser):
        parser.add_argument("--with-sample-data", action="store_true", help="Create one sample business record.")
        parser.add_argument("--create-admin", action="store_true", help="Create or update the initial system administrator.")
        parser.add_argument("--admin-username", help="系统管理员用户名。")
        parser.add_argument("--admin-password-stdin", action="store_true", help="从标准输入读取本次管理员密码。")
        parser.add_argument("--admin-password-stdin-base64", action="store_true", help="从标准输入读取 UTF-8 base64 编码后的本次管理员密码。")

    def handle(self, *args, **options):
        apply_default_role_group_permissions()
        department = self._ensure_departments()
        if options["create_admin"]:
            self._ensure_admin(department, options)
        self._ensure_thresholds()
        self._ensure_rules()
        self._ensure_retention_policy()
        get_or_create_mock_source()
        self._ensure_placeholder_model_versions()
        if options["with_sample_data"]:
            self._ensure_sample_data()
        self.stdout.write(self.style.SUCCESS("系统初始化完成。"))

    def _ensure_departments(self):
        department, _ = Department.objects.get_or_create(
            code=os.environ.get("AIGDM_DEFAULT_DEPARTMENT_CODE", "OB-PRIMARY"),
            defaults={
                "name": os.environ.get("AIGDM_DEFAULT_DEPARTMENT_NAME", "基层产科门诊"),
                "department_type": Department.DepartmentType.OBSTETRICS,
            },
        )
        Department.objects.get_or_create(code="LAB", defaults={"name": "检验科", "department_type": Department.DepartmentType.LAB})
        Department.objects.get_or_create(code="INFO", defaults={"name": "信息科", "department_type": Department.DepartmentType.ADMIN})
        Department.objects.get_or_create(code="GDM-MGMT", defaults={"name": "妊娠糖尿病管理组", "department_type": Department.DepartmentType.ADMIN})
        return department

    def _ensure_admin(self, department, options):
        username = options.get("admin_username") or os.environ.get("AIGDM_ADMIN_USERNAME", "aigdm_admin")
        password = self._get_admin_password(username, options["admin_password_stdin"], options["admin_password_stdin_base64"])
        if not password:
            self.stdout.write(self.style.WARNING("未提供管理员密码，跳过管理员创建。"))
            return
        admin_user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": "系统管理员", "is_staff": True, "is_superuser": True},
        )
        update_fields = []
        if created or not admin_user.check_password(password):
            admin_user.set_password(password)
            update_fields.append("password")
        if not admin_user.is_staff:
            admin_user.is_staff = True
            update_fields.append("is_staff")
        if not admin_user.is_superuser:
            admin_user.is_superuser = True
            update_fields.append("is_superuser")
        if update_fields:
            admin_user.save(update_fields=update_fields)
        profile, _created = UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={"role": UserProfile.Role.ADMIN, "department": department, "data_scope": UserProfile.DataScope.HOSPITAL},
        )
        profile_updates = []
        if profile.role != UserProfile.Role.ADMIN:
            profile.role = UserProfile.Role.ADMIN
            profile_updates.append("role")
        if profile.department_id is None:
            profile.department = department
            profile_updates.append("department")
        if profile.data_scope != UserProfile.DataScope.HOSPITAL:
            profile.data_scope = UserProfile.DataScope.HOSPITAL
            profile_updates.append("data_scope")
        if profile_updates:
            profile.save(update_fields=profile_updates)

    def _get_admin_password(self, username, password_stdin=False, password_stdin_base64=False):
        if password_stdin_base64:
            return self._read_base64_password()
        if password_stdin:
            return sys.stdin.read().rstrip("\r\n")
        if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            return ""

        self.stdout.write(f"请输入系统管理员 {username} 的密码。该密码只会写入数据库哈希，不会保存到 .env。")
        while True:
            first = getpass.getpass("管理员密码: ")
            if not first:
                return ""
            second = getpass.getpass("确认管理员密码: ")
            if first == second:
                return first
            self.stdout.write(self.style.ERROR("两次输入的管理员密码不一致，请重新输入。"))

    def _read_base64_password(self):
        payload = sys.stdin.read().strip().lstrip("\ufeff")
        try:
            return base64.b64decode(payload.encode("ascii"), validate=True).decode("utf-8")
        except Exception as exc:
            invalid_count = sum(1 for char in payload if char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
            raise CommandError(f"管理员初始化失败：密码传输格式无效（收到长度 {len(payload)}，非法字符数 {invalid_count}）。") from exc

    def _ensure_thresholds(self):
        thresholds = [
            ("FPG", "空腹血糖异常阈值", "5.100", "mmol/L", "早孕评估", ThresholdConfig.ThresholdCategory.LAB_ABNORMAL),
            ("FPG", "OGTT空腹血糖诊断阈值", "5.100", "mmol/L", "OGTT", ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS),
            ("OGTT_1H", "OGTT 1小时诊断阈值", "10.000", "mmol/L", "OGTT", ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS),
            ("OGTT_2H", "OGTT 2小时诊断阈值", "8.500", "mmol/L", "OGTT", ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS),
            ("TG", "甘油三酯参考阈值", "1.700", "mmol/L", "早孕评估", ThresholdConfig.ThresholdCategory.LAB_ABNORMAL),
        ]
        for code, name, value, unit, applies_to, category in thresholds:
            ThresholdConfig.objects.update_or_create(
                code=code,
                category=category,
                scope_type=ThresholdConfig.ScopeType.GLOBAL,
                department=None,
                version="1.0",
                defaults={
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "applies_to": applies_to,
                    "unit_rule_json": {"accept": ["mmol/L", "mg/dL"]},
                    "is_active": True,
                    "active_from": timezone.now(),
                },
            )

    def _ensure_rules(self):
        RuleConfig.objects.update_or_create(
            code="RISK_FLOW_V1",
            defaults={
                "name": "GDM风险评估主流程",
                "description": "孕前糖尿病排除、异常确认、完整模型、降级模型和规则轨。",
                "config_json": {
                    "version": "V3.4.1",
                    "rule_only_without_probability": True,
                    "degraded_minimal_fields": ["MOTHER_AGE", "GESTATIONAL_WEEK", "PRE_PREG_BMI"],
                },
                "is_active": True,
            },
        )

    def _ensure_retention_policy(self):
        RetentionPolicy.objects.update_or_create(
            code="CLINICAL_DATA_DEFAULT",
            defaults={"name": "临床数据默认保留策略", "retention_days": 3650, "action": "到期后人工复核", "enabled": True},
        )

    def _ensure_placeholder_model_versions(self):
        placeholders = [
            (
                "PLACEHOLDER_FULL_MODEL_DISABLED",
                "完整模型占位版本（未启用）",
                ModelVersion.ModelType.FULL,
                ["MOTHER_AGE", "GESTATIONAL_WEEK", "PRE_PREG_BMI", "FPG"],
            ),
            (
                "PLACEHOLDER_DEGRADED_MODEL_DISABLED",
                "降级模型占位版本（未启用）",
                ModelVersion.ModelType.DEGRADED,
                ["MOTHER_AGE", "GESTATIONAL_WEEK", "PRE_PREG_BMI"],
            ),
        ]
        for version_code, display_name, model_type, feature_order in placeholders:
            ModelVersion.objects.get_or_create(
                version_code=version_code,
                defaults={
                    "display_name": display_name,
                    "model_type": model_type,
                    "artifact_path": "",
                    "sha256": "0" * 64,
                    "status": ModelVersion.Status.DRAFT,
                    "status_message": "初始化占位版本，需上传并验证真实模型后启用。",
                    "feature_schema_json": {"feature_order": feature_order, "placeholder": True},
                    "input_schema_json": {"required": feature_order},
                    "output_schema_json": {"risk_probability": "number[0,1]", "risk_level": "LOW|MEDIUM|HIGH"},
                },
            )

    def _ensure_sample_data(self):
        record = create_or_update_record_from_payload(
            {
                "record_no": "P-SAMPLE-001",
                "name": "王女士",
                "age": 31,
                "gestational_week": 10.5,
                "height_cm": 162,
                "pre_preg_weight_kg": 63.5,
                "pre_preg_bmi": 24.2,
                "pregnancy_count": 1,
                "birth_count": 0,
            },
            source_type=MaternalRecord.SourceType.MANUAL,
            source_ref="initialize_system",
        )
        if not record.lab_results.filter(item_code=LabResult.ItemCode.FPG).exists():
            create_lab_result(record, LabResult.ItemCode.FPG, "5.0", source_ref="initialize_system")
        if not record.lab_results.filter(item_code=LabResult.ItemCode.TG).exists():
            create_lab_result(record, LabResult.ItemCode.TG, "1.6", source_ref="initialize_system")
        if not record.risk_assessments.exists():
            assess_maternal_record(record)
