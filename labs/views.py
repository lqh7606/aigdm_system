from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import PermissionAction, require_action_or_response
from audit.models import AuditLog
from audit.services import write_audit_log
from common.api import error, ok, parse_json_body
from maternal_records.models import MaternalRecord
from maternal_records.services import visible_records_for_user

from .models import LabResult, OGTTOutcome
from .services import calculate_ogtt_outcome, confirm_lab_result, confirm_ogtt_outcome, create_lab_result


def _visible_records(request):
    return visible_records_for_user(request.user).exclude(status=MaternalRecord.Status.ARCHIVED)


def _filter_lab_results(request):
    visible_records = _visible_records(request)
    results = LabResult.objects.select_related("maternal_record", "threshold_config").filter(
        maternal_record__in=visible_records
    )
    q = request.GET.get("q", "").strip()
    if q:
        results = results.filter(
            Q(maternal_record__name__icontains=q)
            | Q(maternal_record__record_no__icontains=q)
            | Q(item_name__icontains=q)
            | Q(item_code__icontains=q)
        )

    record_id = request.GET.get("record")
    if record_id:
        results = results.filter(maternal_record_id=record_id)

    pending_only = request.GET.get("pending") == "1"
    if pending_only:
        results = results.filter(
            is_abnormal=True,
            confirmation_status=LabResult.ConfirmationStatus.PENDING,
        )

    return results, q, record_id, pending_only


def lab_list(request):
    denied = require_action_or_response(request, PermissionAction.VIEW_LABS)
    if denied:
        return denied
    results, q, record_id, pending_only = _filter_lab_results(request)
    return render(
        request,
        "labs/list.html",
        {
            "results": results[:80],
            "records": _visible_records(request)[:100],
            "q": q,
            "record_id": str(record_id or ""),
            "pending_only": pending_only,
        },
    )


def record_search(request):
    denied = require_action_or_response(request, PermissionAction.CREATE_LAB_RESULT)
    if denied:
        return denied
    query = request.GET.get("q", "").strip()
    records = _visible_records(request)
    if query:
        records = records.filter(Q(name__icontains=query) | Q(record_no__icontains=query))
    data = [
        {
            "id": record.pk,
            "name": record.name,
            "record_no": record.record_no,
            "label": f"{record.name}（{record.record_no}）",
        }
        for record in records.order_by("-updated_at")[:20]
    ]
    return JsonResponse({"results": data}, json_dumps_params={"ensure_ascii": False})


def create_result(request):
    denied = require_action_or_response(request, PermissionAction.CREATE_LAB_RESULT)
    if denied:
        return denied

    selected_record_id = request.POST.get("maternal_record_id") or request.GET.get("record") or ""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    selected_record = _visible_records(request).filter(pk=selected_record_id).first() if selected_record_id else None
    selected_record_label = f"{selected_record.name}（{selected_record.record_no}）" if selected_record else ""

    if request.method == "POST":
        if not selected_record_id:
            messages.error(request, "请先从搜索结果中选择孕妇档案。")
            return render(
                request,
                "labs/create.html",
                {
                    "item_choices": LabResult.ItemCode.choices,
                    "selected_record_id": "",
                    "selected_record_label": request.POST.get("maternal_record_query", ""),
                    "next_url": next_url,
                },
                status=400,
            )
        record = get_object_or_404(_visible_records(request), pk=selected_record_id)
        try:
            result = create_lab_result(
                record,
                request.POST.get("item_code"),
                request.POST.get("value"),
                unit=request.POST.get("unit") or "mmol/L",
                source_type=MaternalRecord.SourceType.MANUAL,
                source_ref=f"manual_form:{request.user.pk}",
            )
        except (TypeError, ValueError) as exc:
            messages.error(request, f"检验录入失败：{exc}")
            return render(
                request,
                "labs/create.html",
                {
                    "item_choices": LabResult.ItemCode.choices,
                    "selected_record_id": str(selected_record_id),
                    "selected_record_label": f"{record.name}（{record.record_no}）",
                    "next_url": next_url,
                },
                status=400,
            )

        write_audit_log(
            request,
            AuditLog.Action.CREATE,
            "LabResult",
            result.pk,
            f"手工录入检验结果：{record.record_no} {result.item_code}",
            metadata={"record_id": record.pk, "item_code": result.item_code, "value": str(result.value), "unit": result.unit},
        )
        messages.success(request, "检验结果已保存。")
        if next_url.startswith("/"):
            return redirect(next_url)
        return redirect("labs:list")

    return render(
        request,
        "labs/create.html",
        {
            "item_choices": LabResult.ItemCode.choices,
            "selected_record_id": str(selected_record_id),
            "selected_record_label": selected_record_label,
            "next_url": next_url,
        },
    )


def confirm_lab(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.CONFIRM_LAB_ABNORMAL, "LabResult", pk)
    if denied:
        return denied
    result = get_object_or_404(LabResult, maternal_record__in=_visible_records(request), pk=pk)
    confirm_lab_result(result, user=request.user, rejected=request.POST.get("decision") == "reject")
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "LabResult",
        result.pk,
        f"确认检验异常：{result.maternal_record.record_no} {result.item_code}",
        metadata={"decision": request.POST.get("decision") or "confirm"},
    )
    messages.success(request, "检验确认状态已更新。")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("labs:list")


def calculate_ogtt(request, record_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.CONFIRM_OGTT_OUTCOME, "MaternalRecord", record_id)
    if denied:
        return denied
    record = get_object_or_404(_visible_records(request), pk=record_id)
    outcome = calculate_ogtt_outcome(record)
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "OGTTOutcome",
        outcome.pk,
        f"计算OGTT结局：{record.record_no}",
        metadata={"outcome": outcome.outcome, "confirmation_status": outcome.confirmation_status},
    )
    messages.success(request, "OGTT 结局已计算，等待医生确认。")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("maternal_records:detail", pk=record.pk)


def confirm_ogtt(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.CONFIRM_OGTT_OUTCOME, "OGTTOutcome", pk)
    if denied:
        return denied
    outcome = get_object_or_404(OGTTOutcome, maternal_record__in=_visible_records(request), pk=pk)
    confirm_ogtt_outcome(outcome, user=request.user, rejected=request.POST.get("decision") == "reject")
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "OGTTOutcome",
        outcome.pk,
        f"确认OGTT结局：{outcome.maternal_record.record_no}",
        metadata={"decision": request.POST.get("decision") or "confirm", "outcome": outcome.outcome},
    )
    messages.success(request, "OGTT 结局确认状态已更新。")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("maternal_records:detail", pk=outcome.maternal_record_id)


def lab_result_payload(item):
    return {
        "id": item.pk,
        "院内就诊号": item.maternal_record.record_no,
        "姓名": item.maternal_record.name,
        "项目编码": item.item_code,
        "项目": item.item_name,
        "值": str(item.value),
        "单位": item.unit,
        "原始值": item.raw_value,
        "原始单位": item.raw_unit,
        "标准化值": str(item.standard_value or item.value),
        "标准单位": item.standard_unit or item.unit,
        "异常": item.is_abnormal,
        "确认状态": item.get_confirmation_status_display(),
        "阈值配置ID": item.threshold_config_id,
        "阈值快照": item.threshold_snapshot_json,
    }


def lab_results_api(request):
    if request.method == "GET":
        denied = require_action_or_response(request, PermissionAction.VIEW_LABS)
        if denied:
            return denied
        results, _q, _record_id, _pending_only = _filter_lab_results(request)
        return ok([lab_result_payload(item) for item in results[:100]])
    if request.method == "POST":
        denied = require_action_or_response(request, PermissionAction.CREATE_LAB_RESULT)
        if denied:
            return denied
        payload = parse_json_body(request)
        record = get_object_or_404(_visible_records(request), pk=payload.get("maternal_record_id"))
        result = create_lab_result(
            record,
            payload.get("item_code"),
            payload.get("value"),
            unit=payload.get("unit") or "mmol/L",
            source_type="MANUAL",
            source_ref=payload.get("source_ref", "api"),
        )
        return ok(lab_result_payload(result), status=201)
    return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")


def confirm_lab_api(request, pk):
    if request.method != "POST":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    denied = require_action_or_response(request, PermissionAction.CONFIRM_LAB_ABNORMAL, "LabResult", pk)
    if denied:
        return denied
    result = get_object_or_404(LabResult, maternal_record__in=_visible_records(request), pk=pk)
    payload = parse_json_body(request)
    confirm_lab_result(result, user=request.user, rejected=bool(payload.get("rejected")))
    return ok(lab_result_payload(result))


def confirm_ogtt_api(request, pk):
    if request.method != "POST":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    denied = require_action_or_response(request, PermissionAction.CONFIRM_OGTT_OUTCOME, "OGTTOutcome", pk)
    if denied:
        return denied
    outcome = get_object_or_404(OGTTOutcome, maternal_record__in=_visible_records(request), pk=pk)
    payload = parse_json_body(request)
    confirm_ogtt_outcome(outcome, user=request.user, rejected=bool(payload.get("rejected")))
    return ok(
        {
            "id": outcome.pk,
            "结局": outcome.get_outcome_display(),
            "确认状态": outcome.get_confirmation_status_display(),
            "触发阈值": outcome.triggered_thresholds_json,
        }
    )
