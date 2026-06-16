import hashlib
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from accounts.permissions import allowed_record_update_fields_for_user
from accounts.permissions import visible_records_for_user as scoped_visible_records_for_user
from audit.models import AuditLog
from audit.services import write_audit_log

from .models import FieldSource, MaternalRecord, MergeRecord, RecordDeletionRequest


REQUIRED_RISK_FIELDS = ["age", "gestational_week", "pre_preg_bmi"]
EDITABLE_RECORD_FIELDS = [
    "name",
    "age",
    "last_menstrual_period",
    "expected_delivery_date",
    "height_cm",
    "pre_preg_weight_kg",
    "current_weight_kg",
    "gestational_week",
    "pregnancy_count",
    "birth_count",
    "multiple_pregnancy",
    "fetal_count",
    "systolic_bp",
    "diastolic_bp",
    "diabetes_before_pregnancy",
]


def visible_records_for_user(user, purpose="clinical"):
    return scoped_visible_records_for_user(user, purpose=purpose)


def mask_id_card(value):
    if not value:
        return ""
    text = str(value).strip()
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"


def mask_phone(value):
    if not value:
        return ""
    text = str(value).strip()
    if len(text) < 7:
        return "*" * len(text)
    return f"{text[:3]}****{text[-4:]}"


def hash_identity(value):
    if not value:
        return ""
    return hashlib.sha256(str(value).strip().upper().encode("utf-8")).hexdigest()


def calculate_bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg:
        return None
    try:
        height_m = Decimal(str(height_cm)) / Decimal("100")
        weight = Decimal(str(weight_kg))
        if height_m <= 0:
            return None
        return (weight / (height_m * height_m)).quantize(Decimal("0.01"))
    except (InvalidOperation, ZeroDivisionError):
        return None


def _serialize_record_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def record_snapshot(record):
    return {
        "id": record.pk,
        "record_no": record.record_no,
        "name": record.name,
        "id_card_masked": record.id_card_masked,
        "phone_masked": record.phone_masked,
        "age": record.age,
        "expected_delivery_date": _serialize_record_value(record.expected_delivery_date),
        "current_weight_kg": _serialize_record_value(record.current_weight_kg),
        "systolic_bp": record.systolic_bp,
        "diastolic_bp": record.diastolic_bp,
        "height_cm": _serialize_record_value(record.height_cm),
        "pre_preg_weight_kg": _serialize_record_value(record.pre_preg_weight_kg),
        "pre_preg_bmi": _serialize_record_value(record.pre_preg_bmi),
        "gestational_week": _serialize_record_value(record.gestational_week),
        "last_menstrual_period": _serialize_record_value(record.last_menstrual_period),
        "pregnancy_count": record.pregnancy_count,
        "birth_count": record.birth_count,
        "multiple_pregnancy": record.multiple_pregnancy,
        "fetal_count": record.fetal_count,
        "diabetes_before_pregnancy": record.diabetes_before_pregnancy,
        "status": record.status,
        "source_type": record.source_type,
        "department_id": record.department_id,
        "primary_doctor_id": record.primary_doctor_id,
    }


def completeness_for_risk(record):
    missing = []
    for field in REQUIRED_RISK_FIELDS:
        if getattr(record, field) in (None, ""):
            missing.append(field)
    return {"complete": not missing, "missing_fields": missing}


def find_duplicate_records(id_card=None, phone=None, name=None):
    queryset = MaternalRecord.objects.filter(status=MaternalRecord.Status.ACTIVE)
    identity_hash = hash_identity(id_card)
    if identity_hash:
        return queryset.filter(id_card_hash=identity_hash)
    if phone and name:
        return queryset.filter(phone_masked=mask_phone(phone), name=name)
    return MaternalRecord.objects.none()


def create_or_update_record_from_payload(payload, source_type=MaternalRecord.SourceType.MANUAL, source_ref=""):
    record_no = payload.get("record_no") or f"GDM{timezone.now():%Y%m%d%H%M%S}"
    id_card = payload.get("id_card") or ""
    phone = payload.get("phone") or ""
    height = payload.get("height_cm")
    weight = payload.get("pre_preg_weight_kg")
    bmi = payload.get("pre_preg_bmi") or calculate_bmi(height, weight)
    record, _ = MaternalRecord.objects.update_or_create(
        record_no=record_no,
        defaults={
            "name": payload.get("name") or "未命名孕妇",
            "id_card_masked": mask_id_card(id_card),
            "id_card_hash": hash_identity(id_card),
            "phone_masked": mask_phone(phone),
            "age": payload.get("age") or None,
            "height_cm": height or None,
            "pre_preg_weight_kg": weight or None,
            "current_weight_kg": payload.get("current_weight_kg") or None,
            "systolic_bp": payload.get("systolic_bp") or None,
            "diastolic_bp": payload.get("diastolic_bp") or None,
            "pre_preg_bmi": bmi or None,
            "gestational_week": payload.get("gestational_week") or None,
            "last_menstrual_period": payload.get("last_menstrual_period") or None,
            "expected_delivery_date": payload.get("expected_delivery_date") or None,
            "pregnancy_count": payload.get("pregnancy_count") or None,
            "birth_count": payload.get("birth_count") or None,
            "multiple_pregnancy": bool(payload.get("multiple_pregnancy")),
            "fetal_count": payload.get("fetal_count") or 1,
            "diabetes_before_pregnancy": bool(payload.get("diabetes_before_pregnancy")),
            "source_type": source_type,
        },
    )
    for field_name, value in payload.items():
        if value not in (None, ""):
            FieldSource.objects.create(
                maternal_record=record,
                field_name=field_name,
                source_type=source_type,
                source_ref=source_ref,
                raw_value=str(value),
            )
    return record


def update_record_basic_info(record, payload, user=None):
    allowed_fields = allowed_record_update_fields_for_user(user)
    editable_fields = EDITABLE_RECORD_FIELDS if allowed_fields is None else [field for field in EDITABLE_RECORD_FIELDS if field in allowed_fields]
    before = record_snapshot(record)
    for field_name in editable_fields:
        if field_name in {"multiple_pregnancy", "diabetes_before_pregnancy"}:
            setattr(record, field_name, payload.get(field_name) == "on")
            continue
        value = payload.get(field_name)
        if value == "":
            value = None
        setattr(record, field_name, value)

    id_card = (payload.get("id_card") or "").strip()
    if id_card and allowed_fields is None:
        record.id_card_masked = mask_id_card(id_card)
        record.id_card_hash = hash_identity(id_card)

    phone = (payload.get("phone") or "").strip()
    if phone and (allowed_fields is None or "phone" in allowed_fields):
        record.phone_masked = mask_phone(phone)

    if allowed_fields is None or {"height_cm", "pre_preg_weight_kg"} & set(editable_fields):
        record.pre_preg_bmi = calculate_bmi(record.height_cm, record.pre_preg_weight_kg)
    update_fields = [
        *editable_fields,
        "updated_at",
    ]
    if allowed_fields is None:
        update_fields.extend(["id_card_masked", "id_card_hash"])
    if allowed_fields is None or "phone" in allowed_fields:
        update_fields.append("phone_masked")
    if allowed_fields is None or {"height_cm", "pre_preg_weight_kg"} & set(editable_fields):
        update_fields.append("pre_preg_bmi")
    record.save(
        update_fields=list(dict.fromkeys(update_fields))
    )
    after = record_snapshot(record)
    changes = {key: {"before": before.get(key), "after": after.get(key)} for key in after if before.get(key) != after.get(key)}
    for field_name, change in changes.items():
        if field_name in {"updated_at"}:
            continue
        FieldSource.objects.create(
            maternal_record=record,
            field_name=field_name,
            source_type=MaternalRecord.SourceType.MANUAL_CORRECTION,
            source_system="AIGDM",
            source_record_id=str(record.pk),
            source_ref="manual_update",
            raw_value=str(change.get("after") or ""),
            normalized_value=str(change.get("after") or ""),
            updated_by=user if getattr(user, "is_authenticated", False) else None,
        )
    return before, after, changes


def create_deletion_request(record, reason, user=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("删除原因不能为空。")
    if record.deletion_requests.filter(status=RecordDeletionRequest.Status.PENDING).exists():
        raise ValueError("该档案已有待审批的删除申请。")
    return RecordDeletionRequest.objects.create(
        record=record,
        record_snapshot=record_snapshot(record),
        requested_by=user if getattr(user, "is_authenticated", False) else None,
        reason=reason,
    )


def approve_deletion_request(deletion_request, action, reviewer=None, comment="", request=None):
    if deletion_request.status != RecordDeletionRequest.Status.PENDING:
        raise ValueError("只能审批待审批的删除申请。")
    if action not in RecordDeletionRequest.ApprovalAction.values:
        raise ValueError("审批通过时必须选择归档或物理删除。")

    record = deletion_request.record
    deletion_request.status = RecordDeletionRequest.Status.APPROVED
    deletion_request.approval_action = action
    deletion_request.approval_comment = comment or deletion_request.get_approval_action_display()
    deletion_request.reviewed_by = reviewer if getattr(reviewer, "is_authenticated", False) else None
    deletion_request.reviewed_at = timezone.now()
    if record and not deletion_request.record_snapshot:
        deletion_request.record_snapshot = record_snapshot(record)
    deletion_request.save(update_fields=["status", "approval_action", "approval_comment", "reviewed_by", "reviewed_at", "record_snapshot"])

    if record and action == RecordDeletionRequest.ApprovalAction.ARCHIVE:
        record.status = MaternalRecord.Status.ARCHIVED
        record.save(update_fields=["status", "updated_at"])
    elif record and action == RecordDeletionRequest.ApprovalAction.DELETE:
        record.delete()

    write_audit_log(
        request,
        AuditLog.Action.DELETE_APPROVE,
        "RecordDeletionRequest",
        deletion_request.pk,
        f"批准档案删除申请：{deletion_request.record_snapshot.get('record_no', deletion_request.record_id)}",
        metadata={
            "approval_action": action,
            "approval_comment": deletion_request.approval_comment,
            "record_snapshot": deletion_request.record_snapshot,
        },
    )
    return deletion_request


def reject_deletion_request(deletion_request, reviewer=None, comment="", request=None):
    if deletion_request.status != RecordDeletionRequest.Status.PENDING:
        raise ValueError("只能驳回待审批的删除申请。")
    deletion_request.status = RecordDeletionRequest.Status.REJECTED
    deletion_request.approval_comment = comment or "驳回删除申请"
    deletion_request.reviewed_by = reviewer if getattr(reviewer, "is_authenticated", False) else None
    deletion_request.reviewed_at = timezone.now()
    deletion_request.save(update_fields=["status", "approval_comment", "reviewed_by", "reviewed_at"])
    write_audit_log(
        request,
        AuditLog.Action.DELETE_REJECT,
        "RecordDeletionRequest",
        deletion_request.pk,
        f"驳回档案删除申请：{deletion_request.record_snapshot.get('record_no', deletion_request.record_id)}",
        metadata={"approval_comment": deletion_request.approval_comment, "record_snapshot": deletion_request.record_snapshot},
    )
    return deletion_request


def merge_records(source_record, target_record, reason, user=None):
    if source_record.pk == target_record.pk:
        raise ValueError("来源档案和目标档案不能相同。")
    merge = MergeRecord.objects.create(
        source_record=source_record,
        target_record=target_record,
        reason=reason,
        status=MergeRecord.Status.APPROVED,
        approved_by=user if getattr(user, "is_authenticated", False) else None,
        approved_at=timezone.now(),
    )
    source_record.status = MaternalRecord.Status.MERGED
    source_record.merged_into = target_record
    source_record.save(update_fields=["status", "merged_into", "updated_at"])
    source_record.lab_results.update(maternal_record=target_record)
    source_record.risk_assessments.update(maternal_record=target_record)
    source_record.followup_chains.update(maternal_record=target_record)
    return merge


