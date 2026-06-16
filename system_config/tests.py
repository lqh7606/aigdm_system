import base64
import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import joblib
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department, UserProfile

from .admin import ModelVersionAdmin, SystemNoticeAdmin
from .deployment import read_env_file
from .model_lifecycle import ModelLifecycleError, activate_model_version, create_release_from_uploaded_file, sha256_file
from .model_runtime import ModelRegistry, PKLModelExecutor
from .models import ModelVersion, SystemNotice


def _b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class FeatureNameModel:
    feature_names_in_ = ["MOTHER_AGE", "FPG"]

    def predict_proba(self, values):
        return [[0.25, 0.75]]


class NoFeatureNameModel:
    def predict_proba(self, values):
        return [[0.7, 0.3]]


class DeploymentCommandTests(TestCase):
    def test_setup_env_writes_sqlite_env_without_mysql_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            call_command(
                "setup_env",
                env_file=str(env_path),
                non_interactive=True,
                db_engine="sqlite",
                admin_username="aigdm_admin",
            )
            values = read_env_file(env_path)

        self.assertEqual(values["AIGDM_DB_ENGINE"], "sqlite")
        self.assertEqual(values["AIGDM_ADMIN_USERNAME"], "aigdm_admin")
        self.assertNotIn("AIGDM_ADMIN_PASSWORD", values)

    def test_setup_env_removes_existing_admin_password_from_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("AIGDM_DB_ENGINE=sqlite\nAIGDM_ADMIN_PASSWORD=old-secret\n", encoding="utf-8")
            call_command(
                "setup_env",
                env_file=str(env_path),
                non_interactive=True,
                db_engine="sqlite",
                admin_username="aigdm_admin",
            )
            values = read_env_file(env_path)

        self.assertEqual(values["AIGDM_ADMIN_USERNAME"], "aigdm_admin")
        self.assertNotIn("AIGDM_ADMIN_PASSWORD", values)

    def test_initialize_system_updates_existing_admin_password_from_stdin(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="aigdm_admin",
            password="old-secret",
            is_staff=False,
            is_superuser=False,
        )

        with patch("sys.stdin", StringIO(_b64("new-secret"))):
            call_command(
                "initialize_system",
                create_admin=True,
                admin_username="aigdm_admin",
                admin_password_stdin_base64=True,
                verbosity=0,
            )

        admin.refresh_from_db()
        self.assertTrue(admin.check_password("new-secret"))
        self.assertFalse(admin.check_password("old-secret"))
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.userprofile.role, UserProfile.Role.ADMIN)
        self.assertEqual(admin.userprofile.data_scope, UserProfile.DataScope.HOSPITAL)

    def test_verify_system_admin_accepts_admin_credentials_from_env(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="aigdm_admin",
            password="admin-secret",
            is_staff=True,
            is_superuser=True,
        )
        UserProfile.objects.create(user=admin, role=UserProfile.Role.ADMIN, data_scope=UserProfile.DataScope.HOSPITAL)

        with patch("sys.stdin", StringIO("admin-secret\n")):
            call_command(
                "verify_system_admin",
                username="aigdm_admin",
                password_stdin=True,
                verbosity=0,
            )

    def test_verify_system_admin_accepts_base64_stdin_password(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="aigdm_admin",
            password="测试Pass@123",
            is_staff=True,
            is_superuser=True,
        )
        UserProfile.objects.create(user=admin, role=UserProfile.Role.ADMIN, data_scope=UserProfile.DataScope.HOSPITAL)

        with patch("sys.stdin", StringIO(_b64("测试Pass@123"))):
            call_command(
                "verify_system_admin",
                username="aigdm_admin",
                password_stdin_base64=True,
                expected_password_length=10,
                verbosity=0,
            )

    def test_verify_system_admin_accepts_base64_stdin_with_bom_prefix(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="aigdm_admin",
            password="admin-secret",
            is_staff=True,
            is_superuser=True,
        )
        UserProfile.objects.create(user=admin, role=UserProfile.Role.ADMIN, data_scope=UserProfile.DataScope.HOSPITAL)

        with patch("sys.stdin", StringIO("\ufeff" + _b64("admin-secret"))):
            call_command(
                "verify_system_admin",
                username="aigdm_admin",
                password_stdin_base64=True,
                expected_password_length=12,
                verbosity=0,
            )

    def test_verify_system_admin_rejects_non_admin_credentials(self):
        User = get_user_model()
        doctor = User.objects.create_user(username="doctor", password="doctor-secret")
        UserProfile.objects.create(user=doctor, role=UserProfile.Role.DOCTOR, data_scope=UserProfile.DataScope.HOSPITAL)

        with self.assertRaisesMessage(Exception, "当前用户不是系统管理员"):
            with patch("sys.stdin", StringIO("doctor-secret\n")):
                call_command(
                    "verify_system_admin",
                    username="doctor",
                    password_stdin=True,
                    verbosity=0,
                )

    def test_verify_system_admin_reports_database_context_for_wrong_password(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="aigdm_admin",
            password="admin-secret",
            is_staff=True,
            is_superuser=True,
        )
        UserProfile.objects.create(user=admin, role=UserProfile.Role.ADMIN, data_scope=UserProfile.DataScope.HOSPITAL)

        with self.assertRaisesMessage(Exception, "密码不正确（aigdm_admin，收到密码长度 12）。当前数据库"):
            with patch("sys.stdin", StringIO("wrong-secret\n")):
                call_command(
                    "verify_system_admin",
                    username="aigdm_admin",
                    password_stdin=True,
                    verbosity=0,
                )

    def test_verify_system_admin_reports_password_transfer_length_mismatch(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="aigdm_admin",
            password="admin-secret",
            is_staff=True,
            is_superuser=True,
        )
        UserProfile.objects.create(user=admin, role=UserProfile.Role.ADMIN, data_scope=UserProfile.DataScope.HOSPITAL)

        with self.assertRaisesMessage(Exception, "启动器传入密码长度异常，本地长度 99，服务端收到长度 12"):
            with patch("sys.stdin", StringIO("wrong-secret\n")):
                call_command(
                    "verify_system_admin",
                    username="aigdm_admin",
                    password_stdin=True,
                    expected_password_length=99,
                    verbosity=0,
                )


class ModelVersionUploadLifecycleTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.model_dir = Path(self.tempdir.name) / "model_files"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.settings_override = override_settings(MODEL_DIR=self.model_dir)
        self.settings_override.enable()
        self.department = Department.objects.create(
            code="OB-MODEL",
            name="模型配置测试科室",
            department_type=Department.DepartmentType.OBSTETRICS,
        )
        self.system_admin = get_user_model().objects.create_user("model_admin", password="password", is_staff=True)
        UserProfile.objects.create(
            user=self.system_admin,
            role=UserProfile.Role.ADMIN,
            department=self.department,
            data_scope=UserProfile.DataScope.HOSPITAL,
        )
        self.doctor = get_user_model().objects.create_user("model_doctor", password="password", is_staff=True)
        UserProfile.objects.create(
            user=self.doctor,
            role=UserProfile.Role.DOCTOR,
            department=self.department,
            data_scope=UserProfile.DataScope.HOSPITAL,
        )
        self.client = Client()

    def tearDown(self):
        self.settings_override.disable()
        self.tempdir.cleanup()
        ModelRegistry.invalidate()
        PKLModelExecutor.invalidate()

    def _uploaded_model(self, model, file_name="model.pkl"):
        source = Path(self.tempdir.name) / file_name
        joblib.dump(model, source)
        return SimpleUploadedFile(file_name, source.read_bytes(), content_type="application/octet-stream")

    def _model_change_payload(self, version, **overrides):
        payload = {
            "version_code": version.version_code,
            "display_name": version.display_name,
            "model_type": version.model_type,
            "artifact_format": version.artifact_format,
            "model_family": version.model_family,
            "artifact_path": version.artifact_path,
            "sha256": version.sha256,
            "dependency_status_json": json.dumps(version.dependency_status_json),
            "validation_report_json": json.dumps(version.validation_report_json),
            "manifest_json": json.dumps(version.manifest_json),
            "feature_schema_json": json.dumps(version.feature_schema_json),
            "input_schema_json": json.dumps(version.input_schema_json),
            "output_schema_json": json.dumps(version.output_schema_json),
            "_save": "Save",
        }
        payload.update(overrides)
        return payload

    def test_uploaded_pkl_generates_version_files_and_feature_schema(self):
        uploaded = self._uploaded_model(FeatureNameModel(), "feature_model.pkl")

        version = create_release_from_uploaded_file(
            uploaded,
            ModelVersion.ModelType.FULL,
            version_code="feature_model_v1",
            display_name="Feature Model V1",
        )

        artifact = self.model_dir / "releases" / "feature_model_v1" / "model.pkl"
        self.assertEqual(version.status, ModelVersion.Status.STAGED)
        self.assertEqual(version.model_family, ModelVersion.ModelFamily.SKLEARN)
        self.assertEqual(version.sha256, sha256_file(artifact))
        self.assertEqual(version.feature_schema_json["feature_order"], ["MOTHER_AGE", "FPG"])
        self.assertEqual(version.feature_schema_json["feature_source"], "model_metadata")
        self.assertEqual(version.input_schema_json["required"], ["MOTHER_AGE", "FPG"])
        self.assertEqual(version.manifest_json["feature_count"], 2)
        self.assertTrue((artifact.parent / "sha256.txt").exists())
        self.assertTrue((artifact.parent / "manifest.json").exists())
        self.assertTrue((artifact.parent / "feature_schema.json").exists())
        self.assertTrue((artifact.parent / "input_schema.json").exists())
        self.assertTrue((artifact.parent / "output_schema.json").exists())

    def test_uploaded_pkl_without_feature_names_is_failed_record(self):
        uploaded = self._uploaded_model(NoFeatureNameModel(), "no_features.pkl")

        with self.assertRaises(ModelLifecycleError):
            create_release_from_uploaded_file(uploaded, ModelVersion.ModelType.FULL, version_code="no_features_v1")

        version = ModelVersion.objects.get(version_code="no_features_v1")
        self.assertEqual(version.status, ModelVersion.Status.FAILED)
        self.assertIn("特征顺序", version.status_message)
        self.assertIn("error", version.validation_report_json)

    def test_duplicate_version_code_is_rejected_without_overwrite(self):
        first_upload = self._uploaded_model(FeatureNameModel(), "duplicate_first.pkl")
        create_release_from_uploaded_file(first_upload, ModelVersion.ModelType.FULL, version_code="duplicate_model")
        second_upload = self._uploaded_model(FeatureNameModel(), "duplicate_second.pkl")

        with self.assertRaises(ModelLifecycleError):
            create_release_from_uploaded_file(second_upload, ModelVersion.ModelType.FULL, version_code="duplicate_model")

        self.assertEqual(ModelVersion.objects.filter(version_code="duplicate_model").count(), 1)

    def test_activation_retires_all_same_type_production_preserves_degraded_and_clears_caches(self):
        old_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "old_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="old_model",
        )
        extra_old_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "extra_old_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="extra_old_model",
        )
        degraded_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "degraded_model.pkl"),
            ModelVersion.ModelType.DEGRADED,
            version_code="degraded_model",
        )
        new_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "new_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="new_model",
        )
        activate_model_version(old_version)
        activate_model_version(degraded_version)
        old_version.refresh_from_db()
        extra_old_version.status = ModelVersion.Status.PRODUCTION
        extra_old_version.activated_at = old_version.activated_at + timedelta(seconds=1)
        extra_old_version.save(update_fields=["status", "activated_at", "updated_at"])
        PKLModelExecutor._model_cache = {old_version.pk: object(), new_version.pk: object()}
        ModelRegistry._cached_versions = {ModelVersion.ModelType.FULL: old_version}
        ModelRegistry._cached_at = {ModelVersion.ModelType.FULL: 999}

        activated = activate_model_version(new_version)
        old_version.refresh_from_db()
        extra_old_version.refresh_from_db()
        degraded_version.refresh_from_db()

        self.assertEqual(activated.status, ModelVersion.Status.PRODUCTION)
        self.assertEqual(activated.predecessor_id, extra_old_version.pk)
        self.assertEqual(old_version.status, ModelVersion.Status.RETIRED)
        self.assertEqual(extra_old_version.status, ModelVersion.Status.RETIRED)
        self.assertEqual(degraded_version.status, ModelVersion.Status.PRODUCTION)
        self.assertEqual(ModelRegistry._cached_versions, {})
        self.assertEqual(PKLModelExecutor._model_cache, {})

    def test_admin_action_activates_single_selected_model_version(self):
        old_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "admin_old_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="admin_old_model",
        )
        new_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "admin_new_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="admin_new_model",
        )
        activate_model_version(old_version)
        self.client.force_login(self.system_admin)

        response = self.client.post(
            reverse("admin:system_config_modelversion_changelist"),
            {
                "action": "activate_selected_model_version",
                "_selected_action": [str(new_version.pk)],
                "select_across": "0",
            },
            follow=True,
        )

        old_version.refresh_from_db()
        new_version.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "已启用为生产版本")
        self.assertEqual(new_version.status, ModelVersion.Status.PRODUCTION)
        self.assertEqual(old_version.status, ModelVersion.Status.RETIRED)

    def test_admin_action_rejects_multiple_selected_model_versions(self):
        first_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "multi_first_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="multi_first_model",
        )
        second_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "multi_second_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="multi_second_model",
        )
        self.client.force_login(self.system_admin)

        response = self.client.post(
            reverse("admin:system_config_modelversion_changelist"),
            {
                "action": "activate_selected_model_version",
                "_selected_action": [str(first_version.pk), str(second_version.pk)],
                "select_across": "0",
            },
            follow=True,
        )

        first_version.refresh_from_db()
        second_version.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "每次只能启用一个模型版本")
        self.assertEqual(first_version.status, ModelVersion.Status.STAGED)
        self.assertEqual(second_version.status, ModelVersion.Status.STAGED)

    def test_admin_action_rejects_invalid_activation_status(self):
        production_version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "already_production_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="already_production_model",
        )
        activate_model_version(production_version)
        self.client.force_login(self.system_admin)

        response = self.client.post(
            reverse("admin:system_config_modelversion_changelist"),
            {
                "action": "activate_selected_model_version",
                "_selected_action": [str(production_version.pk)],
                "select_across": "0",
            },
            follow=True,
        )

        production_version.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "启用失败")
        self.assertEqual(production_version.status, ModelVersion.Status.PRODUCTION)

    def test_admin_change_view_does_not_allow_manual_status_activation(self):
        version = create_release_from_uploaded_file(
            self._uploaded_model(FeatureNameModel(), "manual_status_model.pkl"),
            ModelVersion.ModelType.FULL,
            version_code="manual_status_model",
        )
        self.client.force_login(self.system_admin)

        response = self.client.post(
            reverse("admin:system_config_modelversion_change", args=[version.pk]),
            self._model_change_payload(version, status=ModelVersion.Status.PRODUCTION),
            follow=True,
        )

        version.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(version.status, ModelVersion.Status.STAGED)

    def test_model_version_admin_marks_lifecycle_fields_readonly(self):
        admin = ModelVersionAdmin(ModelVersion, AdminSite())

        self.assertIn("status", admin.readonly_fields)
        self.assertIn("status_message", admin.readonly_fields)
        self.assertIn("predecessor", admin.readonly_fields)

    def test_admin_upload_view_requires_model_config_permission(self):
        url = reverse("admin:system_config_modelversion_upload_pkl")

        self.client.force_login(self.system_admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "上传并验证")

        self.client.force_login(self.doctor)
        response = self.client.get(url)
        self.assertIn(response.status_code, {302, 403})
        self.assertNotEqual(response.status_code, 200)


class SystemFrontendVisibilityTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(code="OB-SYS", name="产科系统测试", department_type=Department.DepartmentType.OBSTETRICS)
        self.user = get_user_model().objects.create_user("doctor", password="password")
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.DOCTOR, department=self.department, data_scope=UserProfile.DataScope.HOSPITAL)
        self.client = Client()
        self.client.force_login(self.user)

    def test_system_admin_pages_are_not_frontend_routes_or_nav_items(self):
        response = self.client.get("/")
        self.assertNotContains(response, "模型配置")
        self.assertNotContains(response, "部署状态")
        self.assertNotContains(response, "审计日志")
        self.assertEqual(self.client.get("/system/models/").status_code, 404)
        self.assertEqual(self.client.get("/system/deployment/").status_code, 404)

    def test_home_displays_notice_titles_time_and_dialogs_without_inline_body(self):
        notice = SystemNotice.objects.create(title="停诊通知", content="本周五下午停诊", is_active=True)
        response = self.client.get("/")
        notice_time = timezone.localtime(notice.updated_at).strftime("%Y-%m-%d %H:%M")

        self.assertContains(response, "系统通知")
        self.assertContains(response, "停诊通知")
        self.assertContains(response, notice_time)
        self.assertContains(response, 'class="notice-title-button"', html=False)
        self.assertContains(response, f'id="notice-dialog-{notice.pk}"', html=False)
        self.assertContains(response, "本周五下午停诊")
        self.assertNotContains(response, "<p>本周五下午停诊</p>", html=True)
        self.assertNotContains(response, "最近一次风险评估")
        self.assertNotContains(response, "SHA256")

    def test_home_notice_with_link_renders_direct_link_without_dialog(self):
        notice = SystemNotice.objects.create(
            title="院内公告",
            content="点击后跳转到院内公告网站",
            is_active=True,
            link_url="https://example.com/notice",
        )

        response = self.client.get("/")

        self.assertContains(response, "院内公告")
        self.assertContains(response, f'href="{notice.link_url}"', html=False)
        self.assertNotContains(response, f"notice-dialog-{notice.pk}")
        self.assertNotContains(response, "点击后跳转到院内公告网站")

    def test_home_notice_order_uses_pinned_importance_and_updated_at(self):
        SystemNotice.objects.create(title="重要通知", content="重要", importance=SystemNotice.Importance.IMPORTANT)
        SystemNotice.objects.create(title="紧急通知", content="紧急", importance=SystemNotice.Importance.URGENT)
        SystemNotice.objects.create(title="置顶通知", content="置顶", importance=SystemNotice.Importance.NORMAL, is_pinned=True)

        response = self.client.get("/")
        body = response.content.decode("utf-8")

        self.assertLess(body.index("置顶通知"), body.index("紧急通知"))
        self.assertLess(body.index("紧急通知"), body.index("重要通知"))


class SystemNoticeAdminPermissionTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(code="OB-NOTICE", name="通知权限测试", department_type=Department.DepartmentType.OBSTETRICS)
        self.manager = get_user_model().objects.create_user("manager", password="password", is_staff=True)
        UserProfile.objects.create(user=self.manager, role=UserProfile.Role.MANAGER, department=self.department, data_scope=UserProfile.DataScope.HOSPITAL)
        self.system_admin = get_user_model().objects.create_user("system_admin", password="password", is_staff=True)
        UserProfile.objects.create(
            user=self.system_admin,
            role=UserProfile.Role.ADMIN,
            department=self.department,
            data_scope=UserProfile.DataScope.HOSPITAL,
        )
        self.doctor = get_user_model().objects.create_user("doctor", password="password", is_staff=True)
        UserProfile.objects.create(user=self.doctor, role=UserProfile.Role.DOCTOR, department=self.department, data_scope=UserProfile.DataScope.HOSPITAL)
        self.admin = SystemNoticeAdmin(SystemNotice, AdminSite())
        self.factory = RequestFactory()

    def _request_for(self, user):
        request = self.factory.get("/admin/system_config/systemnotice/")
        request.user = user
        return request

    def test_only_system_admin_can_edit_notice(self):
        self.assertTrue(self.admin.has_add_permission(self._request_for(self.system_admin)))
        self.assertTrue(self.admin.has_change_permission(self._request_for(self.system_admin)))
        self.assertFalse(self.admin.has_add_permission(self._request_for(self.manager)))
        self.assertFalse(self.admin.has_change_permission(self._request_for(self.manager)))
        self.assertFalse(self.admin.has_add_permission(self._request_for(self.doctor)))
        self.assertFalse(self.admin.has_change_permission(self._request_for(self.doctor)))

    def test_admin_exposes_notice_layering_fields(self):
        self.assertIn("notice_type", self.admin.list_display)
        self.assertIn("importance", self.admin.list_display)
        self.assertIn("is_pinned", self.admin.list_display)
        self.assertIn("notice_type", self.admin.list_filter)
        self.assertIn("importance", self.admin.list_filter)
        self.assertIn("is_pinned", self.admin.list_filter)
        self.assertIn("link_url", self.admin.search_fields)
