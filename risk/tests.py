import math
import statistics
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department, UserProfile
from followups.models import FollowupChain
from labs.models import LabResult
from labs.services import create_lab_result
from maternal_records.services import create_or_update_record_from_payload
from system_config.models import ModelVersion, RuleConfig

from .models import RiskAssessment
from .services import assess_maternal_record, build_model_payload, field_completeness


class RiskServiceTests(TestCase):
    def test_pre_gestational_diabetes_is_excluded_before_model(self):
        record = create_or_update_record_from_payload(
            {"record_no": "RISK001", "name": "排除孕妇", "diabetes_before_pregnancy": True}
        )
        assessment = assess_maternal_record(record)
        self.assertEqual(assessment.engine_type, RiskAssessment.EngineType.EXCLUDED)
        self.assertIsNone(assessment.risk_probability)

    def test_missing_required_fields_uses_rule_only_without_probability(self):
        record = create_or_update_record_from_payload({"record_no": "RISK002", "name": "缺失孕妇"})
        assessment = assess_maternal_record(record)
        self.assertEqual(assessment.engine_type, RiskAssessment.EngineType.RULE_ONLY)
        self.assertIsNone(assessment.risk_probability)
        self.assertEqual(assessment.degradation_reason, "必填字段缺失")

    def test_pending_abnormal_confirmation_blocks_model(self):
        record = create_or_update_record_from_payload(
            {
                "record_no": "RISK003",
                "name": "异常孕妇",
                "age": 31,
                "gestational_week": 10,
                "pre_preg_bmi": 24,
            }
        )
        create_lab_result(record, LabResult.ItemCode.FPG, "5.5")
        assessment = assess_maternal_record(record)
        self.assertEqual(assessment.engine_type, RiskAssessment.EngineType.RULE_ONLY)
        self.assertEqual(assessment.degradation_reason, "存在待确认异常检验结果")


    def test_model_payload_maps_chinese_feature_names_and_derived_features(self):
        record = create_or_update_record_from_payload(
            {
                "record_no": "RISK004",
                "name": "模型映射孕妇",
                "age": 32,
                "gestational_week": 24,
                "pre_preg_bmi": 28.79,
                "pregnancy_count": 2,
                "birth_count": 1,
                "systolic_bp": 130,
                "diastolic_bp": 85,
            }
        )
        create_lab_result(record, LabResult.ItemCode.FPG, "5.6")
        create_lab_result(record, LabResult.ItemCode.TG, "2.2")
        create_lab_result(record, LabResult.ItemCode.TC, "4.6")
        create_lab_result(record, LabResult.ItemCode.GGT, "18")
        create_lab_result(record, LabResult.ItemCode.CHE, "7200")
        create_lab_result(record, LabResult.ItemCode.TBIL, "10.5")

        payload = build_model_payload(record)

        self.assertEqual(payload["MOTHER_AGE"], 32)
        self.assertEqual(payload["GESTATIONAL_WEEK"], 24)
        self.assertEqual(payload["PRE_PREG_BMI"], 28.79)
        self.assertEqual(payload["FPG"], 5.6)
        self.assertEqual(payload["TG"], 2.2)
        self.assertEqual(payload["母亲年龄"], 32)
        self.assertEqual(payload["孕次"], 2)
        self.assertEqual(payload["产次"], 1)
        self.assertEqual(payload["孕前BMI(kg/m2)"], 28.79)
        self.assertEqual(payload["收缩压"], 130)
        self.assertEqual(payload["舒张压"], 85)
        self.assertEqual(payload["空腹血糖"], 5.6)
        self.assertEqual(payload["甘油三酯"], 2.2)
        self.assertEqual(payload["总胆固醇"], 4.6)
        self.assertEqual(payload["γ-谷氨酰转肽酶"], 18)
        self.assertEqual(payload["胆碱脂酶"], 7200)
        self.assertEqual(payload["总胆红素"], 10.5)

        basic_values = [32, 2, 1]
        metabolism_values = [5.6, 28.79, 2.2, 4.6]
        liver_values = [18, 7200, 10.5]
        self.assertAlmostEqual(payload["基础信息组_mean"], sum(basic_values) / len(basic_values))
        self.assertAlmostEqual(payload["基础信息组_std"], statistics.stdev(basic_values))
        self.assertAlmostEqual(payload["基础信息组_max"], 32)
        self.assertAlmostEqual(payload["基础信息组_range"], 31)
        self.assertAlmostEqual(payload["代谢综合征组_mean"], sum(metabolism_values) / len(metabolism_values))
        self.assertAlmostEqual(payload["代谢综合征组_std"], statistics.stdev(metabolism_values))
        self.assertAlmostEqual(payload["代谢综合征组_max"], 28.79)
        self.assertAlmostEqual(payload["代谢综合征组_range"], 28.79 - 2.2)
        self.assertAlmostEqual(payload["肝脏核心组_mean"], sum(liver_values) / len(liver_values))
        self.assertAlmostEqual(payload["肝脏核心组_std"], statistics.stdev(liver_values))
        self.assertAlmostEqual(payload["肝脏核心组_max"], 7200)
        self.assertAlmostEqual(payload["肝脏核心组_range"], 7200 - 10.5)
        self.assertAlmostEqual(payload["孕前BMI×空腹血糖"], 28.79 * 5.6)
        self.assertAlmostEqual(payload["年龄×孕前BMI"], 32 * 28.79)
        self.assertAlmostEqual(payload["(空腹血糖+甘油三酯)×孕前BMI"], (5.6 + 2.2) * 28.79)
        self.assertAlmostEqual(payload["TYG指数"], math.log((2.2 * 88.57) * (5.6 * 18.0182) / 2))

    def test_model_payload_exposes_chinese_lab_schema_names(self):
        record = create_or_update_record_from_payload(
            {"record_no": "RISK005", "name": "中文检验字段孕妇", "age": 32, "gestational_week": 24, "pre_preg_bmi": 28.79}
        )
        create_lab_result(record, LabResult.ItemCode.ALB, "38")
        create_lab_result(record, LabResult.ItemCode.WBC, "7.2")

        payload = build_model_payload(record)
        completeness = field_completeness(record, ["白蛋白", "白细胞计数"])

        self.assertEqual(payload["白蛋白"], 38)
        self.assertEqual(payload["白细胞计数"], 7.2)
        self.assertTrue(completeness["complete"])
        self.assertEqual(completeness["missing_fields"], [])

    def test_medium_risk_assessment_creates_followup(self):
        record = create_or_update_record_from_payload(
            {
                "record_no": "RISK005",
                "name": "中危评估孕妇",
                "age": 32,
                "gestational_week": 24,
                "pre_preg_bmi": 28.79,
            }
        )
        create_lab_result(record, LabResult.ItemCode.FPG, "5.0")
        model_version = ModelVersion.objects.create(
            version_code="test-medium-followup",
            display_name="Test medium followup",
            artifact_path="dummy.pkl",
            sha256="0" * 64,
            status=ModelVersion.Status.PRODUCTION,
            feature_schema_json={"feature_order": ["MOTHER_AGE"]},
        )

        with (
            patch("risk.services.ModelRegistry.current_production", return_value=model_version),
            patch(
                "risk.services.PKLModelExecutor.predict",
                return_value={
                    "risk_probability": 0.5,
                    "risk_level": RiskAssessment.RiskLevel.MEDIUM,
                    "factors": [],
                },
            ),
        ):
            assessment = assess_maternal_record(record)

        self.assertEqual(assessment.engine_type, RiskAssessment.EngineType.FULL_MODEL)
        self.assertEqual(assessment.risk_level, RiskAssessment.RiskLevel.MEDIUM)
        chain = FollowupChain.objects.get(maternal_record=record)
        self.assertEqual(chain.risk_assessment, assessment)
        self.assertEqual(chain.reason, "中危风险评估")
        self.assertEqual(chain.tasks.get().task_name, "中危孕妇首次随访")


    def test_missing_model_feature_does_not_call_predict_with_zero(self):
        record = create_or_update_record_from_payload(
            {"record_no": "RISK006", "name": "缺少检验孕妇", "age": 32, "gestational_week": 24, "pre_preg_bmi": 28.79}
        )
        model_version = ModelVersion.objects.create(
            version_code="test-requires-fpg",
            display_name="Requires FPG",
            artifact_path="dummy.pkl",
            sha256="0" * 64,
            status=ModelVersion.Status.PRODUCTION,
            feature_schema_json={"feature_order": ["MOTHER_AGE", "FPG"]},
        )

        def current(model_type=ModelVersion.ModelType.FULL):
            return model_version if model_type == ModelVersion.ModelType.FULL else None

        with (
            patch("risk.services.ModelRegistry.current_production", side_effect=current),
            patch("risk.services.PKLModelExecutor.predict") as predict,
        ):
            assessment = assess_maternal_record(record)

        self.assertEqual(assessment.engine_type, RiskAssessment.EngineType.RULE_ONLY)
        self.assertIn("FPG", assessment.missing_fields_json)
        predict.assert_not_called()

    def test_pending_abnormal_blocks_degraded_model_too(self):
        record = create_or_update_record_from_payload(
            {"record_no": "RISK007", "name": "异常阻断孕妇", "age": 32, "gestational_week": 24, "pre_preg_bmi": 28.79}
        )
        create_lab_result(record, LabResult.ItemCode.FPG, "5.6")
        full_version = ModelVersion.objects.create(
            version_code="test-full-abnormal-block",
            display_name="Full abnormal block",
            artifact_path="dummy.pkl",
            sha256="0" * 64,
            status=ModelVersion.Status.PRODUCTION,
            model_type=ModelVersion.ModelType.FULL,
            feature_schema_json={"feature_order": ["MOTHER_AGE", "FPG"]},
        )
        degraded_version = ModelVersion.objects.create(
            version_code="test-degraded-abnormal-block",
            display_name="Degraded abnormal block",
            artifact_path="dummy.pkl",
            sha256="0" * 64,
            status=ModelVersion.Status.PRODUCTION,
            model_type=ModelVersion.ModelType.DEGRADED,
            feature_schema_json={"feature_order": ["MOTHER_AGE"]},
        )

        def current(model_type=ModelVersion.ModelType.FULL):
            return degraded_version if model_type == ModelVersion.ModelType.DEGRADED else full_version

        with (
            patch("risk.services.ModelRegistry.current_production", side_effect=current),
            patch("risk.services.PKLModelExecutor.predict") as predict,
        ):
            assessment = assess_maternal_record(record)

        self.assertEqual(assessment.engine_type, RiskAssessment.EngineType.RULE_ONLY)
        self.assertTrue(assessment.abnormal_confirmation_json["has_pending_abnormal"])
        predict.assert_not_called()


class RiskViewTests(TestCase):
    def test_assessment_list_searches_by_record_no_and_assessment_no(self):
        user = get_user_model().objects.create_superuser("admin", "admin@example.com", "password")
        record = create_or_update_record_from_payload({"record_no": "RISK-Q-001", "name": "评估检索孕妇"})
        RiskAssessment.objects.create(
            maternal_record=record,
            assessment_no="ASSESS-Q-001",
            engine_type=RiskAssessment.EngineType.RULE_ONLY,
            degradation_reason="测试",
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse("risk:list"), {"q": "RISK-Q-001"})
        self.assertContains(response, "ASSESS-Q-001")
        self.assertContains(response, "院内就诊号")
        self.assertContains(response, "risk-list-table")
        self.assertContains(response, "risk-cell-reason")

        response = client.get(reverse("risk:list"), {"q": "ASSESS-Q-001"})
        self.assertContains(response, "评估检索孕妇")

    def test_missing_required_fields_reason_displays_concrete_fields(self):
        user = get_user_model().objects.create_superuser("admin2", "admin2@example.com", "password")
        record = create_or_update_record_from_payload({"record_no": "RISK-Q-002", "name": "缺字段孕妇"})
        RiskAssessment.objects.create(
            maternal_record=record,
            assessment_no="ASSESS-Q-002",
            engine_type=RiskAssessment.EngineType.RULE_ONLY,
            degradation_reason="必填字段缺失",
            missing_fields_json=["age", "gestational_week", "UNKNOWN_FIELD"],
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse("risk:list"), {"q": "ASSESS-Q-002"})
        self.assertContains(response, "必填字段缺失：年龄、当前孕周、UNKNOWN_FIELD")

        response = client.get(reverse("risk:api_assessments"))
        self.assertEqual(response.status_code, 200)
        item = response.json()["数据"][0]
        self.assertEqual(item["降级原因展示"], "必填字段缺失：年龄、当前孕周、UNKNOWN_FIELD")

    def test_assessment_list_uses_model_version_display_fallback(self):
        user = get_user_model().objects.create_superuser("admin3", "admin3@example.com", "password")
        record = create_or_update_record_from_payload({"record_no": "RISK-Q-003", "name": "版本展示孕妇"})
        full_version = ModelVersion.objects.create(
            version_code="full-display-v1",
            display_name="Full display",
            artifact_path="dummy.pkl",
            sha256="2" * 64,
            status=ModelVersion.Status.PRODUCTION,
        )
        rule = RuleConfig.objects.create(code="RULE-DISPLAY-V1", name="规则展示", is_active=True)
        RiskAssessment.objects.create(
            maternal_record=record,
            assessment_no="ASSESS-Q-003",
            engine_type=RiskAssessment.EngineType.FULL_MODEL,
            full_model_version=full_version,
        )
        RiskAssessment.objects.create(
            maternal_record=record,
            assessment_no="ASSESS-Q-004",
            engine_type=RiskAssessment.EngineType.RULE_ONLY,
            rule_config=rule,
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse("risk:list"), {"q": "ASSESS-Q-003"})
        self.assertContains(response, "full-display-v1")

        response = client.get(reverse("risk:list"), {"q": "ASSESS-Q-004"})
        self.assertContains(response, "RULE-DISPLAY-V1")

    def test_preview_assessment_returns_visible_model_inputs(self):
        department = Department.objects.create(
            code="OB-RISK",
            name="产科风险",
            department_type=Department.DepartmentType.OBSTETRICS,
        )
        user = get_user_model().objects.create_user("risk_doctor", password="StrongPass123")
        UserProfile.objects.create(user=user, role=UserProfile.Role.DOCTOR, department=department)
        record = create_or_update_record_from_payload(
            {
                "record_no": "RISK-PREVIEW-001",
                "name": "预览孕妇",
                "age": 32,
                "gestational_week": 24,
                "pre_preg_bmi": 28.79,
            }
        )
        record.primary_doctor = user
        record.department = department
        record.save(update_fields=["primary_doctor", "department", "updated_at"])
        create_lab_result(record, LabResult.ItemCode.FPG, "4.8")
        create_lab_result(record, LabResult.ItemCode.TG, "1.6")
        ModelVersion.objects.create(
            version_code="preview-full-v1",
            display_name="Preview full",
            artifact_path="dummy.pkl",
            sha256="3" * 64,
            status=ModelVersion.Status.PRODUCTION,
            model_type=ModelVersion.ModelType.FULL,
            feature_schema_json={"feature_order": ["MOTHER_AGE", "GESTATIONAL_WEEK", "PRE_PREG_BMI", "FPG"]},
        )
        ModelVersion.objects.create(
            version_code="preview-degraded-v1",
            display_name="Preview degraded",
            artifact_path="dummy.pkl",
            sha256="4" * 64,
            status=ModelVersion.Status.PRODUCTION,
            model_type=ModelVersion.ModelType.DEGRADED,
            feature_schema_json={"feature_order": ["MOTHER_AGE"]},
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse("risk:preview_record", args=[record.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        field_names = {item["name"] for item in payload["fields"]}
        display_names = {item["display_name"] for item in payload["fields"]}
        self.assertEqual(payload["record"]["record_no"], "RISK-PREVIEW-001")
        self.assertEqual(payload["model_versions"]["full"], "preview-full-v1")
        self.assertEqual(payload["model_versions"]["degraded"], "preview-degraded-v1")
        self.assertIn("MOTHER_AGE", field_names)
        self.assertIn("FPG", field_names)
        self.assertIn("年龄", display_names)
        self.assertIn("当前孕周", display_names)
        self.assertIn("孕前BMI", display_names)
        self.assertIn("空腹血糖", display_names)
        self.assertIn("孕前BMI×空腹血糖", display_names)
        self.assertIn("年龄×孕前BMI", display_names)
        self.assertIn("(空腹血糖+甘油三酯)×孕前BMI", display_names)
        self.assertIn("TYG指数", display_names)
        self.assertEqual(payload["missing_fields"], [])
        self.assertEqual(payload["missing_fields_display"], [])
