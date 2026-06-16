import math
import statistics
import uuid

from django.utils import timezone

from labs.models import LabResult
from labs.services import abnormal_confirmation_summary, latest_standard_lab_value
from maternal_records.services import completeness_for_risk
from system_config.model_runtime import ModelExecutionError, ModelRegistry, PKLModelExecutor
from system_config.models import ModelVersion, RuleConfig, ThresholdConfig
from system_config.thresholds import threshold_snapshot_for_codes

from .models import PreExclusionRecord, RiskAssessment


MODEL_LAB_FEATURE_CODES = {
    LabResult.ItemCode.GGT.label: LabResult.ItemCode.GGT,
    LabResult.ItemCode.ALB.label: LabResult.ItemCode.ALB,
    LabResult.ItemCode.WBC.label: LabResult.ItemCode.WBC,
    LabResult.ItemCode.TSH.label: LabResult.ItemCode.TSH,
    LabResult.ItemCode.MONO_ABS.label: LabResult.ItemCode.MONO_ABS,
    LabResult.ItemCode.CHE.label: LabResult.ItemCode.CHE,
    LabResult.ItemCode.TG.label: LabResult.ItemCode.TG,
    LabResult.ItemCode.ALT.label: LabResult.ItemCode.ALT,
    LabResult.ItemCode.AST.label: LabResult.ItemCode.AST,
    LabResult.ItemCode.RBC.label: LabResult.ItemCode.RBC,
    LabResult.ItemCode.HCT.label: LabResult.ItemCode.HCT,
    LabResult.ItemCode.APTT.label: LabResult.ItemCode.APTT,
    LabResult.ItemCode.CREA.label: LabResult.ItemCode.CREA,
    LabResult.ItemCode.ALP.label: LabResult.ItemCode.ALP,
    LabResult.ItemCode.FPG.label: LabResult.ItemCode.FPG,
    LabResult.ItemCode.LYM_ABS.label: LabResult.ItemCode.LYM_ABS,
    LabResult.ItemCode.UREA.label: LabResult.ItemCode.UREA,
    LabResult.ItemCode.UA.label: LabResult.ItemCode.UA,
    LabResult.ItemCode.TT.label: LabResult.ItemCode.TT,
    LabResult.ItemCode.FIB.label: LabResult.ItemCode.FIB,
    LabResult.ItemCode.HGB.label: LabResult.ItemCode.HGB,
    LabResult.ItemCode.PLT.label: LabResult.ItemCode.PLT,
    LabResult.ItemCode.FT4.label: LabResult.ItemCode.FT4,
    LabResult.ItemCode.FT3.label: LabResult.ItemCode.FT3,
    LabResult.ItemCode.DBIL.label: LabResult.ItemCode.DBIL,
    LabResult.ItemCode.NEUT_ABS.label: LabResult.ItemCode.NEUT_ABS,
    LabResult.ItemCode.TC.label: LabResult.ItemCode.TC,
    LabResult.ItemCode.TBIL.label: LabResult.ItemCode.TBIL,
    LabResult.ItemCode.TBA.label: LabResult.ItemCode.TBA,
    LabResult.ItemCode.TP.label: LabResult.ItemCode.TP,
}

BASE_FEATURES = {
    "MOTHER_AGE": "age",
    "GESTATIONAL_WEEK": "gestational_week",
    "PRE_PREG_BMI": "pre_preg_bmi",
    "FPG": LabResult.ItemCode.FPG,
    "TG": LabResult.ItemCode.TG,
    "母亲年龄": "age",
    "孕次": "pregnancy_count",
    "产次": "birth_count",
    "孕前BMI(kg/m2)": "pre_preg_bmi",
    "收缩压": "systolic_bp",
    "舒张压": "diastolic_bp",
}

DEFAULT_FULL_REQUIRED = ["MOTHER_AGE", "GESTATIONAL_WEEK", "PRE_PREG_BMI", "FPG"]
DEFAULT_DEGRADED_REQUIRED = ["MOTHER_AGE", "GESTATIONAL_WEEK", "PRE_PREG_BMI"]
THRESHOLD_TRACE_CODES = ["FPG", "OGTT_1H", "OGTT_2H", "TG"]


def assessment_no():
    return f"RA{timezone.now():%Y%m%d%H%M%S%f}"


def active_rule_config():
    return RuleConfig.objects.filter(code="RISK_FLOW_V1", is_active=True).first() or RuleConfig.objects.filter(is_active=True).first()


def rule_only_result(reason, missing_fields=None):
    missing_fields = missing_fields or []
    return {
        "clinical_tips": [
            "本次未生成模型概率，请按规则评估结果处理。",
            "补齐缺失字段、确认异常值或处理模型状态后，可重新发起评估。",
        ],
        "missing_fields": missing_fields,
        "supplement_suggestions": [
            "确认模型依赖、特征结构、阈值配置和生产版本状态。",
            "补齐早孕期基础信息和关键检验字段。",
        ],
        "risk_probability": None,
        "risk_level": None,
        "degradation_reason": reason,
    }


def _float_value(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _group_stats(values):
    numbers = [value for value in (_float_value(item) for item in values) if value is not None]
    if not numbers:
        return {}
    return {
        "mean": sum(numbers) / len(numbers),
        "std": statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
        "max": max(numbers),
        "range": max(numbers) - min(numbers),
    }


def _tyg_index(fpg, tg):
    fpg = _float_value(fpg)
    tg = _float_value(tg)
    if fpg is None or tg is None or fpg <= 0 or tg <= 0:
        return None
    return math.log((tg * 88.57) * (fpg * 18.0182) / 2)


def latest_lab_value(record, item_code):
    value = latest_standard_lab_value(record, item_code)
    return _float_value(value)


def _lab_feature_label(item_code):
    try:
        return LabResult.ItemCode(item_code).label
    except ValueError:
        return str(item_code)


def _put_lab_feature(payload, lab_values, feature_name, item_code, value):
    if value is None:
        return
    label = _lab_feature_label(item_code)
    lab_values[label] = value
    payload[feature_name] = value
    payload[label] = value


def _put_if_present(payload, key, value):
    value = _float_value(value)
    if value is not None:
        payload[key] = value


def build_model_payload(record):
    payload = {}
    _put_if_present(payload, "MOTHER_AGE", record.age)
    _put_if_present(payload, "GESTATIONAL_WEEK", record.gestational_week)
    _put_if_present(payload, "PRE_PREG_BMI", record.pre_preg_bmi)
    _put_if_present(payload, "母亲年龄", record.age)
    _put_if_present(payload, "孕次", record.pregnancy_count)
    _put_if_present(payload, "产次", record.birth_count)
    _put_if_present(payload, "孕前BMI(kg/m2)", record.pre_preg_bmi)
    _put_if_present(payload, "收缩压", record.systolic_bp)
    _put_if_present(payload, "舒张压", record.diastolic_bp)

    lab_values = {}
    for feature_name, item_code in MODEL_LAB_FEATURE_CODES.items():
        value = latest_lab_value(record, item_code)
        _put_lab_feature(payload, lab_values, feature_name, item_code, value)

    fpg = lab_values.get("空腹血糖")
    tg = lab_values.get("甘油三酯")
    if fpg is not None:
        payload["FPG"] = fpg
    if tg is not None:
        payload["TG"] = tg

    basic_stats = _group_stats([record.age, record.pregnancy_count, record.birth_count])
    metabolism_stats = _group_stats(
        [
            payload.get("FPG"),
            record.pre_preg_bmi,
            payload.get("TG"),
            lab_values.get("总胆固醇"),
        ]
    )
    liver_stats = _group_stats(
        [
            lab_values.get("γ-谷氨酰转肽酶"),
            lab_values.get("胆碱脂酶"),
            lab_values.get("总胆红素"),
        ]
    )
    for prefix, stats in (
        ("基础信息组_", basic_stats),
        ("代谢综合征组_", metabolism_stats),
        ("肝脏核心组_", liver_stats),
    ):
        for key, value in stats.items():
            payload[f"{prefix}{key}"] = value

    bmi = _float_value(record.pre_preg_bmi)
    age = _float_value(record.age)
    if bmi is not None and fpg is not None:
        payload["孕前BMI×空腹血糖"] = bmi * fpg
    if age is not None and bmi is not None:
        payload["年龄×孕前BMI"] = age * bmi
    if fpg is not None and tg is not None and bmi is not None:
        payload["(空腹血糖+甘油三酯)×孕前BMI"] = (fpg + tg) * bmi
    tyg = _tyg_index(fpg, tg)
    if tyg is not None:
        payload["TYG指数"] = tyg
    return payload


def feature_order_for(model_version, default_required):
    if not model_version:
        return list(default_required)
    schema = model_version.feature_schema_json or {}
    return list(schema.get("feature_order") or schema.get("required") or default_required)


def degraded_minimal_features(rule_config, degraded_version=None):
    if degraded_version:
        schema = degraded_version.feature_schema_json or {}
        configured = schema.get("minimal_required") or schema.get("feature_order")
        if configured:
            return list(configured)
    config = rule_config.config_json if rule_config else {}
    return list(config.get("degraded_minimal_fields") or DEFAULT_DEGRADED_REQUIRED)


def field_completeness(record, required_features):
    payload = build_model_payload(record)
    missing = [field for field in required_features if field not in payload or payload[field] in (None, "")]
    return {
        "complete": not missing,
        "missing_fields": missing,
        "used_fields": [field for field in required_features if field in payload and field not in missing],
        "payload": payload,
    }


def risk_threshold_snapshot(record):
    return threshold_snapshot_for_codes(
        THRESHOLD_TRACE_CODES,
        category=ThresholdConfig.ThresholdCategory.LAB_ABNORMAL,
        department=getattr(record, "department", None),
    )


def _trace_defaults(record, rule_config, pre_exclusion_record=None, abnormal_summary=None, trace_request_id=None):
    return {
        "rule_config": rule_config,
        "pre_exclusion_record": pre_exclusion_record,
        "abnormal_summary": abnormal_summary or {},
        "threshold_snapshot": risk_threshold_snapshot(record),
        "trace_request_id": trace_request_id or uuid.uuid4().hex,
    }


def save_rule_only(record, reason, missing_fields=None, trace=None, **trace_defaults):
    missing_fields = missing_fields or []
    result = rule_only_result(reason, missing_fields)
    return RiskAssessment.objects.create(
        maternal_record=record,
        assessment_no=assessment_no(),
        engine_type=RiskAssessment.EngineType.RULE_ONLY,
        rule_config=trace_defaults.get("rule_config"),
        pre_exclusion_record=trace_defaults.get("pre_exclusion_record"),
        result_json=result,
        data_completeness_json={"complete": False, "missing_fields": missing_fields},
        threshold_snapshot_json=trace_defaults.get("threshold_snapshot") or {},
        missing_fields_json=missing_fields,
        abnormal_confirmation_json=trace_defaults.get("abnormal_summary") or {},
        model_trace_json=trace or {"reason": reason},
        trace_request_id=trace_defaults.get("trace_request_id") or "",
        degradation_reason=reason,
    )


def _save_excluded(record, pre_exclusion_record, rule_config, trace_request_id):
    return RiskAssessment.objects.create(
        maternal_record=record,
        assessment_no=assessment_no(),
        engine_type=RiskAssessment.EngineType.EXCLUDED,
        rule_config=rule_config,
        pre_exclusion_record=pre_exclusion_record,
        result_json={
            "clinical_tips": ["该孕妇已标记孕前糖尿病，本次不调用GDM风险模型。"],
            "risk_probability": None,
            "risk_level": None,
        },
        threshold_snapshot_json=risk_threshold_snapshot(record),
        model_trace_json={"reason": "PRE_GESTATIONAL_DIABETES"},
        trace_request_id=trace_request_id,
        degradation_reason="孕前糖尿病，不进入GDM模型",
    )


def assess_maternal_record(record):
    trace_request_id = uuid.uuid4().hex
    rule_config = active_rule_config()
    if record.diabetes_before_pregnancy:
        pre_exclusion = PreExclusionRecord.objects.create(
            maternal_record=record,
            decision=PreExclusionRecord.Decision.EXCLUDED,
            reason="已标记孕前糖尿病，不进入GDM风险模型。",
        )
        return _save_excluded(record, pre_exclusion, rule_config, trace_request_id)

    pre_exclusion = PreExclusionRecord.objects.create(
        maternal_record=record,
        decision=PreExclusionRecord.Decision.NOT_EXCLUDED,
        reason="未发现孕前糖尿病标记。",
    )
    trace_defaults = _trace_defaults(record, rule_config, pre_exclusion, trace_request_id=trace_request_id)

    abnormal_summary = abnormal_confirmation_summary(record)
    trace_defaults["abnormal_summary"] = abnormal_summary
    if abnormal_summary["has_pending_abnormal"]:
        return save_rule_only(
            record,
            "存在待确认异常检验结果",
            trace={"reason": "PENDING_ABNORMAL_CONFIRMATION", **abnormal_summary},
            **trace_defaults,
        )

    full_version = ModelRegistry.current_production(ModelVersion.ModelType.FULL)
    full_required = feature_order_for(full_version, DEFAULT_FULL_REQUIRED)
    full_completeness = field_completeness(record, full_required)
    if not full_completeness["complete"]:
        degraded_version = ModelRegistry.current_production(ModelVersion.ModelType.DEGRADED)
        degraded_required = degraded_minimal_features(rule_config, degraded_version=degraded_version)
        degraded_completeness = field_completeness(record, degraded_required)
    else:
        degraded_version = None
        degraded_completeness = None
    if not full_version:
        if not full_completeness["complete"]:
            return save_rule_only(
                record,
                "必填字段缺失",
                missing_fields=full_completeness["missing_fields"],
                trace={"reason": "MISSING_REQUIRED_FIELDS", "full_model_version_id": None},
                **trace_defaults,
            )
        return save_rule_only(record, "未启用生产模型", trace={"reason": "NO_PRODUCTION_MODEL"}, **trace_defaults)
    if full_completeness["complete"]:
        try:
            output = PKLModelExecutor.predict(full_version, full_completeness["payload"])
        except ModelExecutionError as exc:
            return save_rule_only(
                record,
                str(exc),
                trace={"model_version_id": full_version.pk, "version_code": full_version.version_code, "reason": str(exc)},
                **trace_defaults,
            )
        assessment = RiskAssessment.objects.create(
            maternal_record=record,
            assessment_no=assessment_no(),
            engine_type=RiskAssessment.EngineType.FULL_MODEL,
            model_version=full_version,
            full_model_version=full_version,
            rule_config=rule_config,
            pre_exclusion_record=pre_exclusion,
            risk_probability=output["risk_probability"],
            risk_level=output["risk_level"],
            result_json=output,
            data_completeness_json={key: value for key, value in full_completeness.items() if key != "payload"},
            threshold_snapshot_json=trace_defaults["threshold_snapshot"],
            used_fields_json=full_completeness["used_fields"],
            missing_fields_json=[],
            abnormal_confirmation_json=abnormal_summary,
            model_trace_json={
                "model_version_id": full_version.pk,
                "version_code": full_version.version_code,
                "feature_count": len(full_required),
            },
            trace_request_id=trace_request_id,
        )
        _ensure_followup_if_needed(record, assessment)
        return assessment

    degraded_version = ModelRegistry.current_production(ModelVersion.ModelType.DEGRADED)
    degraded_required = degraded_minimal_features(rule_config, degraded_version=degraded_version)
    degraded_completeness = field_completeness(record, degraded_required)
    if degraded_version and degraded_completeness["complete"]:
        try:
            output = PKLModelExecutor.predict(degraded_version, degraded_completeness["payload"])
            assessment = RiskAssessment.objects.create(
                maternal_record=record,
                assessment_no=assessment_no(),
                engine_type=RiskAssessment.EngineType.DEGRADED_MODEL,
                model_version=degraded_version,
                full_model_version=full_version,
                degraded_model_version=degraded_version,
                rule_config=rule_config,
                pre_exclusion_record=pre_exclusion,
                risk_probability=output["risk_probability"],
                risk_level=output["risk_level"],
                result_json=output,
                data_completeness_json={
                    "full_model": {key: value for key, value in full_completeness.items() if key != "payload"},
                    "degraded_model": {key: value for key, value in degraded_completeness.items() if key != "payload"},
                },
                threshold_snapshot_json=trace_defaults["threshold_snapshot"],
                used_fields_json=degraded_completeness["used_fields"],
                missing_fields_json=full_completeness["missing_fields"],
                abnormal_confirmation_json=abnormal_summary,
                model_trace_json={
                    "full_model_version_id": full_version.pk,
                    "degraded_model_version_id": degraded_version.pk,
                    "version_code": degraded_version.version_code,
                    "reason": "FULL_MODEL_FIELDS_MISSING",
                },
                trace_request_id=trace_request_id,
                degradation_reason="完整模型字段缺失，已使用降级模型。",
            )
            _ensure_followup_if_needed(record, assessment)
            return assessment
        except ModelExecutionError as exc:
            return save_rule_only(
                record,
                str(exc),
                missing_fields=full_completeness["missing_fields"],
                trace={"reason": str(exc), "degraded_model_version_id": degraded_version.pk},
                **trace_defaults,
            )

    rule_missing = full_completeness["missing_fields"]
    if degraded_version and degraded_completeness["missing_fields"]:
        rule_missing = sorted(set(rule_missing + degraded_completeness["missing_fields"]))
    return save_rule_only(
        record,
        "必填字段缺失",
        missing_fields=rule_missing,
        trace={
            "reason": "MISSING_REQUIRED_FIELDS",
            "full_model_version_id": full_version.pk,
            "degraded_model_version_id": degraded_version.pk if degraded_version else None,
            "degraded_model_available": bool(degraded_version),
        },
        **trace_defaults,
    )


def _ensure_followup_if_needed(record, assessment):
    if assessment.risk_level in {RiskAssessment.RiskLevel.MEDIUM, RiskAssessment.RiskLevel.HIGH}:
        from followups.services import ensure_risk_followup

        ensure_risk_followup(record, assessment=assessment, risk_level=assessment.risk_level)
