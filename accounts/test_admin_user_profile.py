from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department, UserProfile


class UserAdminProfileTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            code="OB-ADMIN",
            name="后台权限测试科室",
            department_type=Department.DepartmentType.OBSTETRICS,
        )
        self.admin_user = User.objects.create_user("profile_admin", password="StrongPass123")
        UserProfile.objects.create(
            user=self.admin_user,
            role=UserProfile.Role.ADMIN,
            department=self.department,
            data_scope=UserProfile.DataScope.HOSPITAL,
        )
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_user_add_page_uses_fixed_profile_fields_without_inline_add_link(self):
        response = self.client.get(reverse("admin:auth_user_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户档案")
        self.assertContains(response, "角色")
        self.assertContains(response, "所属科室")
        self.assertContains(response, "数据范围")
        self.assertNotContains(response, "添加另一个 用户档案")

    def test_user_add_creates_single_controlled_profile(self):
        response = self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "new_doctor",
                "password1": "NewStrongPass123",
                "password2": "NewStrongPass123",
                "role": UserProfile.Role.DOCTOR,
                "department": str(self.department.pk),
                "data_scope": UserProfile.DataScope.DEPARTMENT,
                "mobile": "13800138000",
                "_save": "保存",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="new_doctor")
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)
        self.assertEqual(user.userprofile.role, UserProfile.Role.DOCTOR)
        self.assertEqual(user.userprofile.department, self.department)
        self.assertEqual(user.userprofile.data_scope, UserProfile.DataScope.DEPARTMENT)
        self.assertEqual(user.userprofile.mobile, "13800138000")

    def test_user_add_requires_department_for_non_admin_roles(self):
        response = self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "new_nurse",
                "password1": "NewStrongPass123",
                "password2": "NewStrongPass123",
                "role": UserProfile.Role.NURSE,
                "data_scope": UserProfile.DataScope.DEPARTMENT,
                "_save": "保存",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "非系统管理员必须选择所属科室。")
        self.assertFalse(User.objects.filter(username="new_nurse").exists())

    def test_user_change_page_does_not_expose_profile_inline_add_link(self):
        user = User.objects.create_user("existing_doctor", password="StrongPass123")
        UserProfile.objects.create(
            user=user,
            role=UserProfile.Role.DOCTOR,
            department=self.department,
            data_scope=UserProfile.DataScope.SELF,
        )

        response = self.client.get(reverse("admin:auth_user_change", args=[user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户档案")
        self.assertNotContains(response, "添加另一个 用户档案")
