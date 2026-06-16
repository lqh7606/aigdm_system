from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect


class RequireLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        allowed_prefixes = (
            settings.LOGIN_URL,
            "/accounts/logout/",
            "/admin/",
            "/static/",
        )
        if not request.user.is_authenticated and not path.startswith(allowed_prefixes):
            if path.startswith("/api/"):
                return JsonResponse(
                    {"成功": False, "错误码": "UNAUTHENTICATED", "消息": "请先登录系统。"},
                    status=401,
                    json_dumps_params={"ensure_ascii": False},
                )
            return redirect(f"{settings.LOGIN_URL}?next={path}")
        return self.get_response(request)
