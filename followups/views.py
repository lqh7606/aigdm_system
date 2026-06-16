from django.contrib import messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.permissions import PermissionAction, require_action_or_response
from audit.models import AuditLog
from audit.services import write_audit_log
from common.api import error, ok, parse_json_body
from labs.models import LabResult
from labs.services import create_lab_result
from maternal_records.services import visible_records_for_user

from .models import FollowupChain, FollowupTask, SystemReminder
from .services import cancel_followup_task, complete_followup_task, confirm_followup_outcome


def _visible_records(user):
    return visible_records_for_user(user)


def _visible_reminders(user):
    visible_records = _visible_records(user)
    return SystemReminder.objects.select_related("task", "task__chain", "task__chain__maternal_record").filter(
        task__chain__maternal_record__in=visible_records
    ).exclude(status=SystemReminder.Status.CANCELLED)


def _visible_task(request, pk):
    return get_object_or_404(
        FollowupTask.objects.select_related("chain", "chain__maternal_record", "assigned_to"),
        chain__maternal_record__in=_visible_records(request.user),
        pk=pk,
    )


def followup_home(request):
    denied = require_action_or_response(request, PermissionAction.VIEW_FOLLOWUPS)
    if denied:
        return denied
    visible_records = _visible_records(request.user)
    return render(
        request,
        "followups/home.html",
        {
            "chains": FollowupChain.objects.select_related("maternal_record", "risk_assessment").filter(maternal_record__in=visible_records)[:30],
            "tasks": FollowupTask.objects.select_related("chain", "chain__maternal_record")
            .filter(chain__maternal_record__in=visible_records)
            .exclude(status=FollowupTask.Status.CANCELLED)[:50],
            "reminders": _visible_reminders(request.user)[:20],
        },
    )


def _build_followup_result(post_data, created_lab=None):
    labels = [
        ("contact_method", "联系方式"),
        ("followup_result", "随访结果"),
        ("review_time", "复查时间"),
        ("unfinished_reason", "未完成原因"),
        ("remark", "备注"),
    ]
    parts = [f"{label}：{post_data.get(name)}" for name, label in labels if post_data.get(name)]
    if created_lab:
        parts.append(f"复查检验：{created_lab.item_name} {created_lab.value} {created_lab.unit}")
    return "\n".join(parts) or "已完成随访。"


def task_detail(request, pk):
    denied = require_action_or_response(request, PermissionAction.VIEW_FOLLOWUPS, "FollowupTask", pk)
    if denied:
        return denied
    task = _visible_task(request, pk)
    record = task.chain.maternal_record

    if request.method == "POST":
        denied = require_action_or_response(request, PermissionAction.EXECUTE_FOLLOWUP_TASK, "FollowupTask", pk)
        if denied:
            return denied
        created_lab = None
        review_code = request.POST.get("review_item_code")
        review_value = request.POST.get("review_value")
        if review_code and review_value:
            try:
                created_lab = create_lab_result(
                    record,
                    review_code,
                    review_value,
                    unit=request.POST.get("review_unit") or "mmol/L",
                    source_type="MANUAL",
                    source_ref=f"followup_task:{task.pk}",
                )
            except ValueError as exc:
                messages.error(request, f"复查结果登记失败：{exc}")
                return render(
                    request,
                    "followups/task_detail.html",
                    {"task": task, "record": record, "item_choices": LabResult.ItemCode.choices},
                    status=400,
                )

        complete_followup_task(task, _build_followup_result(request.POST, created_lab=created_lab), user=request.user)
        write_audit_log(
            request,
            AuditLog.Action.UPDATE,
            "FollowupTask",
            task.pk,
            f"完成随访任务：{record.record_no} {task.task_name}",
            metadata={"created_lab_id": created_lab.pk if created_lab else None},
        )
        messages.success(request, "随访任务已提交，等待医生确认。")
        return redirect("followups:task_detail", pk=task.pk)

    return render(
        request,
        "followups/task_detail.html",
        {"task": task, "record": record, "item_choices": LabResult.ItemCode.choices},
    )


def complete_task(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.EXECUTE_FOLLOWUP_TASK, "FollowupTask", pk)
    if denied:
        return denied
    task = _visible_task(request, pk)
    complete_followup_task(task, "页面快速完成：已联系孕妇并完成健康宣教。", user=request.user)
    messages.success(request, "随访任务已完成。")
    return redirect("followups:task_detail", pk=task.pk)


def cancel_task(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.EXECUTE_FOLLOWUP_TASK, "FollowupTask", pk)
    if denied:
        return denied
    task = _visible_task(request, pk)
    reason = request.POST.get("reason") or "页面删除，任务已取消。"
    try:
        cancel_followup_task(task, reason=reason, user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("followups:task_detail", pk=task.pk)
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "FollowupTask",
        task.pk,
        f"取消随访任务：{task.chain.maternal_record.record_no} {task.task_name}",
        metadata={"reason": reason},
    )
    messages.success(request, "随访任务已删除，并标记为已取消。")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("followups:home")


def confirm_task_outcome(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.CONFIRM_FOLLOWUP_OUTCOME, "FollowupTask", pk)
    if denied:
        return denied
    task = _visible_task(request, pk)
    next_followup_at = parse_datetime(request.POST.get("next_followup_at") or "")
    if next_followup_at and timezone.is_naive(next_followup_at):
        next_followup_at = timezone.make_aware(next_followup_at)
    confirm_followup_outcome(
        task,
        decision=request.POST.get("decision") or "CLOSE",
        comment=request.POST.get("doctor_comment") or "",
        next_followup_at=next_followup_at,
        user=request.user,
    )
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "FollowupTask",
        task.pk,
        f"确认随访结局：{task.chain.maternal_record.record_no} {task.task_name}",
        metadata={"decision": request.POST.get("decision") or "CLOSE"},
    )
    messages.success(request, "随访结局已确认。")
    return redirect("followups:task_detail", pk=task.pk)


def followup_task_payload(item):
    chain = item.chain
    return {
        "id": item.pk,
        "姓名": chain.maternal_record.name,
        "任务": item.task_name,
        "任务类型": item.task_type,
        "任务状态": item.get_status_display(),
        "链路ID": chain.pk,
        "链路状态": chain.get_status_display(),
        "截止时间": item.due_at,
        "去重键孕妇ID": chain.dedup_active_record_id,
        "关联评估ID": chain.last_assessment_ids_json,
        "最近OGTT结局ID": chain.last_ogtt_outcome_id,
    }


def followup_tasks_api(request):
    if request.method == "GET":
        denied = require_action_or_response(request, PermissionAction.VIEW_FOLLOWUPS)
        if denied:
            return denied
        visible_records = _visible_records(request.user)
        tasks = FollowupTask.objects.select_related("chain", "chain__maternal_record").filter(
            chain__maternal_record__in=visible_records
        )[:100]
        return ok([followup_task_payload(item) for item in tasks])
    return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")


def complete_task_api(request, pk):
    if request.method != "POST":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    denied = require_action_or_response(request, PermissionAction.EXECUTE_FOLLOWUP_TASK, "FollowupTask", pk)
    if denied:
        return denied
    task = _visible_task(request, pk)
    payload = parse_json_body(request)
    complete_followup_task(task, payload.get("result_text") or "已完成随访。", user=request.user)
    return ok(followup_task_payload(task))
