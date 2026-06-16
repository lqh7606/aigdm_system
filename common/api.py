import json

from django.http import JsonResponse


def parse_json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def ok(data=None, status=200):
    return JsonResponse({"成功": True, "数据": data or {}}, status=status, json_dumps_params={"ensure_ascii": False})


def error(message, status=400, code="BAD_REQUEST", extra=None):
    payload = {"成功": False, "错误码": code, "消息": message}
    if extra:
        payload["详情"] = extra
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


