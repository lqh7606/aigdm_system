import time

from django.contrib.auth import logout
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.shortcuts import redirect, render

from .admin_permissions import can_access_admin
from .forms import ProfileForm
from .models import UserProfile


def _style_password_form(form):
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")
    return form


class ChineseLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    max_failures = 5
    lock_seconds = 15 * 60

    def dispatch(self, request, *args, **kwargs):
        locked_until = request.session.get("login_locked_until", 0)
        if locked_until and locked_until > time.time():
            messages.error(request, "登录失败次数过多，请稍后再试。")
            return render(request, self.template_name, self.get_context_data())
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "系统登录"
        return context

    def get_success_url(self):
        if can_access_admin(self.request.user):
            return "/admin/"
        return super().get_success_url()

    def form_invalid(self, form):
        failures = int(self.request.session.get("login_failure_count", 0)) + 1
        self.request.session["login_failure_count"] = failures
        if failures >= self.max_failures:
            self.request.session["login_locked_until"] = time.time() + self.lock_seconds
            messages.error(self.request, "登录失败次数过多，账号已临时锁定。")
        return super().form_invalid(form)

    def form_valid(self, form):
        self.request.session.pop("login_failure_count", None)
        self.request.session.pop("login_locked_until", None)
        return super().form_valid(form)


def logout_view(request):
    logout(request)
    return redirect("accounts:login")


def permission_denied_page(request, exception=None):
    message = str(exception) if exception else "没有权限执行该操作。"
    if not message:
        message = "没有权限执行该操作。"
    return render(
        request,
        "errors/403.html",
        {"error_code": "GDM-403-001", "message": message},
        status=403,
    )


def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile_form = ProfileForm(
        initial={
            "first_name": request.user.first_name,
            "email": request.user.email,
            "mobile": profile.mobile,
        }
    )
    password_form = _style_password_form(PasswordChangeForm(request.user))

    if request.method == "POST" and request.POST.get("action") == "profile":
        profile_form = ProfileForm(request.POST)
        if profile_form.is_valid():
            request.user.first_name = profile_form.cleaned_data["first_name"]
            request.user.email = profile_form.cleaned_data["email"]
            request.user.save(update_fields=["first_name", "email"])
            profile.mobile = profile_form.cleaned_data["mobile"]
            profile.save(update_fields=["mobile", "updated_at"])
            messages.success(request, "个人信息已更新。")
            return redirect("accounts:profile")

    if request.method == "POST" and request.POST.get("action") == "password":
        password_form = _style_password_form(PasswordChangeForm(request.user, request.POST))
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "密码已修改。")
            return redirect("accounts:profile")

    return render(
        request,
        "accounts/profile.html",
        {
            "profile": profile,
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )

