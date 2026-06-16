from django.db.models import Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import PermissionAction, require_action_or_response
from common.api import error, ok, parse_json_body
from labs.services import abnormal_confirmation_summary
from maternal_records.services import visible_records_for_user
from system_config.model_runtime import ModelRegistry
from system_config.models import ModelVersion

from .models import RiskAssessment
from .services import (
    MODEL_LAB_FEATURE_CODES,
    active_rule_config,
    assess_maternal_record,
    build_model_payload,
    risk_threshold_snapshot,
)


FEATURE_DISPLAY_LABELS = {
    "MOTHER_AGE": "年龄",
    "GESTATIONAL_WEEK": "当前孕周",
    "PRE_PREG_BMI": "孕前BMI",
    "FPG": "空腹血糖",
    "TG": "甘油三酯",
    "母亲年龄": "年龄",
    "孕次": "孕次",
    "产次": "产次",
    "孕前BMI(kg/m2)": "孕前BMI",
    "收缩压": "收缩压",
    "舒张压": "舒张压",
    "空腹血糖": "空腹血糖",
    "甘油三酯": "甘油三酯",
    "总胆固醇": "总胆固醇",
    "γ-谷氨酰转肽酶": "γ-谷氨酰转肽酶",
    "胆碱脂酶": "胆碱脂酶",
    "总胆红素": "总胆红素",
    "孕前BMI×空腹血糖": "孕前BMI×空腹血糖",
    "年龄×孕前BMI": "年龄×孕前BMI",
    "(空腹血糖+甘油三酯)×孕前BMI": "(空腹血糖+甘油三酯)×孕前BMI",
    "TYG指数": "TYG指数",
}


def display_feature_name(name):
    if name in FEATURE_DISPLAY_LABELS:
        return FEATURE_DISPLAY_LABELS[name]
    if name in MODEL_LAB_FEATURE_CODES:
        return MODEL_LAB_FEATURE_CODES[name].label
    return name


def _filter_assessments(request):
    assessments = RiskAssessment.objects.select_related(
        "maternal_record",
        "model_version",
        "full_model_version",
        "degraded_model_version",
        "rule_config",
    ).filter(
        maternal_record__in=visible_records_for_user(request.user)
    )
    q = request.GET.get("q", "").strip()
    if q:
        assessments = assessments.filter(
            Q(assessment_no__icontains=q)
            | Q(maternal_record__name__icontains=q)
            | Q(maternal_record__record_no__icontains=q)
            | Q(model_version__version_code__icontains=q)
            | Q(full_model_version__version_code__icontains=q)
            | Q(degraded_model_version__version_code__icontains=q)
        )
    return assessments, q


def assessment_list(request):
    denied = require_action_or_response(request, PermissionAction.VIEW_RISK)
    if denied:
        return denied
    assessments, q = _filter_assessments(request)
    return render(request, "risk/list.html", {"assessments": assessments[:100], "q": q})


def assess_record(request, record_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    denied = require_action_or_response(request, PermissionAction.RUN_RISK_ASSESSMENT, "MaternalRecord", record_id)
    if denied:
        return denied
    record = get_object_or_404(visible_records_for_user(request.user), pk=record_id)
    assess_maternal_record(record)
    return redirect("risk:list")


def preview_record_assessment(request, record_id):
    denied = require_action_or_response(request, PermissionAction.RUN_RISK_ASSESSMENT, "MaternalRecord", record_id)
    if denied:
        return denied
    record = get_object_or_404(visible_records_for_user(request.user), pk=record_id)
    payload = build_model_payload(record)
    full_version = ModelRegistry.current_production(ModelVersion.ModelType.FULL)
    degraded_version = ModelRegistry.current_production(ModelVersion.ModelType.DEGRADED)
    rule_config = active_rule_config()
    threshold_snapshot = risk_threshold_snapshot(record)
    fields = [
        {"name": key, "display_name": display_feature_name(key), "value": value}
        for key, value in sorted(payload.items(), key=lambda item: display_feature_name(item[0]))
    ]
    missing_fields = []
    if full_version:
        feature_schema = full_version.feature_schema_json or {}
        feature_order = feature_schema.get("feature_order") or feature_schema.get("required") or []
        missing_fields = [field for field in feature_order if field not in payload or payload[field] in (None, "")]
    return JsonResponse(
        {
            "record": {
                "id": record.pk,
                "record_no": record.record_no,
                "name": record.name,
            },
            "model_versions": {
                "full": full_version.version_code if full_version else "-",
                "degraded": degraded_version.version_code if degraded_version else "-",
            },
            "rule_version": rule_config.code if rule_config else "-",
            "fields": fields,
            "missing_fields": missing_fields,
            "missing_fields_display": [display_feature_name(field) for field in missing_fields],
            "abnormal_summary": abnormal_confirmation_summary(record),
            "threshold_summary": threshold_snapshot,
        },
        json_dumps_params={"ensure_ascii": False},
    )


def assessment_payload(item):
    return {
        "id": item.pk,
        "评估编号": item.assessment_no,
        "姓名": item.maternal_record.name if item.maternal_record else "",
        "院内就诊号": item.maternal_record.record_no if item.maternal_record else "",
        "engine_type": item.engine_type,
        "引擎": item.get_engine_type_display(),
        "风险等级": item.get_risk_level_display() if item.risk_level else "",
        "风险概率": item.risk_probability,
        "模型版本": item.display_model_version,
        "完整模型版本": item.full_model_version.version_code if item.full_model_version else "",
        "降级模型版本": item.degraded_model_version.version_code if item.degraded_model_version else "",
        "规则版本": item.rule_config.code if item.rule_config else "",
        "阈值快照": item.threshold_snapshot_json,
        "使用字段": item.used_fields_json,
        "缺失字段": item.missing_fields_json,
        "异常确认摘要": item.abnormal_confirmation_json,
        "降级原因": item.degradation_reason,
        "降级原因展示": item.display_degradation_reason,
        "追踪请求ID": item.trace_request_id,
        "创建时间": item.created_at,
    }


def assessments_api(request):
    if request.method == "GET":
        denied = require_action_or_response(request, PermissionAction.VIEW_RISK)
        if denied:
            return denied
        assessments, _ = _filter_assessments(request)
        return ok([assessment_payload(item) for item in assessments[:100]])
    if request.method == "POST":
        denied = require_action_or_response(request, PermissionAction.RUN_RISK_ASSESSMENT)
        if denied:
            return denied
        payload = parse_json_body(request)
        record = get_object_or_404(visible_records_for_user(request.user), pk=payload.get("maternal_record_id"))
        item = assess_maternal_record(record)
        return ok(assessment_payload(item), status=201)
    return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
