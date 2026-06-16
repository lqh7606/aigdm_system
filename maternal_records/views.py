from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import Coalesce
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import PermissionAction, permission_denied_response, require_action_or_response, validate_record_update_fields
from audit.models import AuditLog
from audit.services import write_audit_log
from common.api import error, ok, parse_json_body
from followups.models import FollowupTask
from labs.models import LabResult

from .models import MaternalRecord, RecordDeletionRequest
from .services import (
    create_deletion_request,
    create_or_update_record_from_payload,
    find_duplicate_records,
    merge_records,
    update_record_basic_info,
    visible_records_for_user,
)


RECORD_PAGE_SIZE_OPTIONS = (10, 20, 50, 100)


def _record_page_size(request):
    try:
        page_size = int(request.GET.get("page_size") or RECORD_PAGE_SIZE_OPTIONS[0])
    except (TypeError, ValueError):
        return RECORD_PAGE_SIZE_OPTIONS[0]
    if page_size not in RECORD_PAGE_SIZE_OPTIONS:
        return RECORD_PAGE_SIZE_OPTIONS[0]
    return page_size


def _active_visible_records(user):
    return visible_records_for_user(user).exclude(status=MaternalRecord.Status.ARCHIVED)


def record_list(request):
    denied = require_action_or_response(request, PermissionAction.VIEW_RECORDS)
    if denied:
        return denied
    records_qs = _active_visible_records(request.user)
    page_size = _record_page_size(request)
    records_paginator = Paginator(records_qs, page_size)
    records_page = records_paginator.get_page(request.GET.get("page"))
    page_record_ids = [record.pk for record in records_page.object_list]
    pending_deletion_ids = set(
        RecordDeletionRequest.objects.filter(
            record_id__in=page_record_ids,
            status=RecordDeletionRequest.Status.PENDING,
        ).values_list("record_id", flat=True)
    )
    merge_targets = list(records_qs[:100])
    return render(
        request,
        "maternal_records/list.html",
        {
            "records": records_page,
            "records_page": records_page,
            "merge_targets": merge_targets,
            "pending_deletion_ids": pending_deletion_ids,
            "page_size": page_size,
            "page_size_options": RECORD_PAGE_SIZE_OPTIONS,
        },
    )


def record_detail(request, pk):
    denied = require_action_or_response(request, PermissionAction.VIEW_RECORDS, "MaternalRecord", pk)
    if denied:
        return denied
    record = get_object_or_404(visible_records_for_user(request.user), pk=pk)
    visible_records = _active_visible_records(request.user)
    write_audit_log(request, AuditLog.Action.VIEW, "MaternalRecord", record.pk, f"查看孕妇档案：{record.name}")
    followup_chains = record.followup_chains.prefetch_related(
        Prefetch(
            "tasks",
            queryset=FollowupTask.objects.exclude(status=FollowupTask.Status.CANCELLED),
            to_attr="visible_tasks",
        )
    ).all()
    lab_results = (
        record.lab_results.annotate(
            review_order=Case(
                When(confirmation_status=LabResult.ConfirmationStatus.PENDING, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            effective_at=Coalesce("reported_at", "sampled_at", "created_at"),
        )
        .order_by("review_order", "-effective_at", "-created_at", "-pk")
    )
    lab_paginator = Paginator(lab_results, 8)
    lab_results_page = lab_paginator.get_page(request.GET.get("lab_page"))
    risk_assessments = record.risk_assessments.select_related(
        "model_version",
        "full_model_version",
        "degraded_model_version",
        "rule_config",
    ).order_by("-created_at", "-pk")
    risk_paginator = Paginator(risk_assessments, 8)
    risk_assessments_page = risk_paginator.get_page(request.GET.get("risk_page"))
    return render(
        request,
        "maternal_records/detail.html",
        {
            "record": record,
            "merge_targets": visible_records.exclude(pk=record.pk)[:100],
            "followup_chains": followup_chains,
            "lab_results_page": lab_results_page,
            "risk_assessments_page": risk_assessments_page,
        },
    )


def update_record(request, pk):
    if request.method != "POST":
        return redirect("maternal_records:detail", pk=pk)
    denied = require_action_or_response(request, PermissionAction.UPDATE_RECORD, "MaternalRecord", pk)
    if denied:
        return denied
    record = get_object_or_404(_active_visible_records(request.user), pk=pk)
    is_valid, forbidden_fields = validate_record_update_fields(request.user, request.POST.keys())
    if not is_valid:
        return permission_denied_response(
            request,
            PermissionAction.SUPPLEMENT_WHITELIST_FIELDS,
            "MaternalRecord",
            record.pk,
            f"无权补录字段：{', '.join(forbidden_fields)}。",
        )
    before, after, changes = update_record_basic_info(record, request.POST, user=request.user)
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "MaternalRecord",
        record.pk,
        f"修改孕妇档案基础信息：{record.name}",
        before=before,
        after=after,
        metadata={"changes": changes},
    )
    messages.success(request, "档案基础信息已更新。")
    return redirect("maternal_records:detail", pk=record.pk)


def request_record_deletion(request, pk):
    if request.method != "POST":
        return redirect("maternal_records:list")
    denied = require_action_or_response(request, PermissionAction.REQUEST_RECORD_DELETION, "MaternalRecord", pk)
    if denied:
        return denied
    record = get_object_or_404(_active_visible_records(request.user), pk=pk)
    try:
        deletion_request = create_deletion_request(record, request.POST.get("reason"), user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("maternal_records:list")
    write_audit_log(
        request,
        AuditLog.Action.DELETE_REQUEST,
        "RecordDeletionRequest",
        deletion_request.pk,
        f"提交档案删除申请：{record.record_no}",
        metadata={"reason": deletion_request.reason, "record_snapshot": deletion_request.record_snapshot},
    )
    messages.success(request, "删除申请已提交，待系统管理员审批。")
    return redirect("maternal_records:list")


def create_record(request):
    if request.method != "POST":
        return redirect("maternal_records:list")
    denied = require_action_or_response(request, PermissionAction.CREATE_RECORD)
    if denied:
        return denied
    payload = {
        "record_no": request.POST.get("record_no"),
        "name": request.POST.get("name"),
        "id_card": request.POST.get("id_card"),
        "phone": request.POST.get("phone"),
        "age": request.POST.get("age"),
        "last_menstrual_period": request.POST.get("last_menstrual_period"),
        "expected_delivery_date": request.POST.get("expected_delivery_date"),
        "height_cm": request.POST.get("height_cm"),
        "pre_preg_weight_kg": request.POST.get("pre_preg_weight_kg"),
        "gestational_week": request.POST.get("gestational_week"),
        "systolic_bp": request.POST.get("systolic_bp"),
        "diastolic_bp": request.POST.get("diastolic_bp"),
        "diabetes_before_pregnancy": request.POST.get("diabetes_before_pregnancy") == "on",
    }
    record = create_or_update_record_from_payload(payload)
    if record.primary_doctor_id is None:
        record.primary_doctor = request.user
        record.save(update_fields=["primary_doctor", "updated_at"])
    write_audit_log(request, AuditLog.Action.CREATE, "MaternalRecord", record.pk, f"创建孕妇档案：{record.name}")
    messages.success(request, "档案已保存。")
    return redirect("maternal_records:list")


def merge_record_view(request):
    if request.method != "POST":
        return redirect("maternal_records:list")
    denied = require_action_or_response(request, PermissionAction.MERGE_RECORD)
    if denied:
        return denied
    source = get_object_or_404(visible_records_for_user(request.user), pk=request.POST.get("source_id"))
    target = get_object_or_404(visible_records_for_user(request.user), pk=request.POST.get("target_id"))
    try:
        merge = merge_records(source, target, request.POST.get("reason") or "人工确认重复档案", user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(request.POST.get("next") or "maternal_records:list")
    write_audit_log(
        request,
        AuditLog.Action.UPDATE,
        "MergeRecord",
        merge.pk,
        f"合并孕妇档案：{source.record_no} -> {target.record_no}",
    )
    messages.success(request, "档案合并已完成。")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("maternal_records:detail", pk=target.pk)


def maternal_records_api(request):
    if request.method == "GET":
        denied = require_action_or_response(request, PermissionAction.VIEW_RECORDS)
        if denied:
            return denied
        data = [
            {
                "id": item.pk,
                "院内就诊号": item.record_no,
                "姓名": item.name,
                "年龄": item.age,
                "孕周": str(item.gestational_week or ""),
                "孕前BMI": str(item.pre_preg_bmi or ""),
                "状态": item.get_status_display(),
            }
            for item in _active_visible_records(request.user)[:100]
        ]
        return ok(data)
    if request.method == "POST":
        denied = require_action_or_response(request, PermissionAction.CREATE_RECORD)
        if denied:
            return denied
        payload = parse_json_body(request)
        duplicates = list(find_duplicate_records(payload.get("id_card"), payload.get("phone"), payload.get("name")))
        record = create_or_update_record_from_payload(payload)
        if record.primary_doctor_id is None:
            record.primary_doctor = request.user
            record.save(update_fields=["primary_doctor", "updated_at"])
        write_audit_log(request, AuditLog.Action.CREATE, "MaternalRecord", record.pk, f"接口创建孕妇档案：{record.name}")
        return ok(
            {
                "id": record.pk,
                "院内就诊号": record.record_no,
                "重复候选数量": len([item for item in duplicates if item.pk != record.pk]),
            },
            status=201,
        )
    return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
