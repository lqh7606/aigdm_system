from django.utils import timezone
from django.db.models.functions import Coalesce

from followups.models import FollowupChain, FollowupTask, SystemReminder
from system_config.models import ThresholdConfig
from system_config.thresholds import convert_to_standard_unit, resolve_threshold

from .models import LabResult, OGTTOutcome


def threshold_category_for_item(item_code):
    if item_code in {LabResult.ItemCode.OGTT_1H, LabResult.ItemCode.OGTT_2H}:
        return ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS
    return ThresholdConfig.ThresholdCategory.LAB_ABNORMAL


def normalize_lab_value(item_code, value, unit="mmol/L", department=None, category=None):
    category = category or threshold_category_for_item(item_code)
    threshold = resolve_threshold(item_code, category=category, department=department)
    standard_unit = threshold["unit"] or unit or "mmol/L"
    standard_value, standard_unit = convert_to_standard_unit(item_code, value, unit, standard_unit)
    return standard_value, standard_unit, threshold


def is_abnormal(item_code, value, unit="mmol/L", department=None):
    threshold = resolve_threshold(
        item_code,
        category=threshold_category_for_item(item_code),
        department=department,
    )
    if threshold["value"] is None:
        return False
    standard_value, _, _ = normalize_lab_value(
        item_code,
        value,
        unit=unit,
        department=department,
        category=threshold_category_for_item(item_code),
    )
    return standard_value >= threshold["value"]


def create_lab_result(
    record,
    item_code,
    value,
    unit="mmol/L",
    source_type="MANUAL",
    source_ref="",
    source_task=None,
    import_batch=None,
):
    item_name = LabResult.ItemCode(item_code).label if item_code in LabResult.ItemCode.values else item_code
    department = getattr(record, "department", None)
    standard_value, standard_unit, threshold = normalize_lab_value(item_code, value, unit=unit, department=department)
    abnormal = threshold["value"] is not None and standard_value >= threshold["value"]
    result = LabResult.objects.create(
        maternal_record=record,
        item_code=item_code,
        item_name=item_name,
        value=standard_value,
        unit=standard_unit,
        raw_value=str(value),
        raw_unit=unit or standard_unit,
        standard_value=standard_value,
        standard_unit=standard_unit,
        source_type=source_type,
        source_ref=source_ref,
        source_task=source_task,
        import_batch=import_batch,
        is_abnormal=abnormal,
        threshold_config=threshold["config"],
        threshold_snapshot_json=threshold["snapshot"],
        sampled_at=timezone.now(),
        reported_at=timezone.now(),
    )
    if not result.is_abnormal:
        result.confirmation_status = LabResult.ConfirmationStatus.CONFIRMED
        result.confirmed_at = timezone.now()
        result.save(update_fields=["confirmation_status", "confirmed_at", "updated_at"])
    return result


def confirm_lab_result(result, user=None, rejected=False):
    result.confirmation_status = (
        LabResult.ConfirmationStatus.REJECTED if rejected else LabResult.ConfirmationStatus.CONFIRMED
    )
    result.confirmed_by = user if getattr(user, "is_authenticated", False) else None
    result.confirmed_at = timezone.now()
    result.save(update_fields=["confirmation_status", "confirmed_by", "confirmed_at", "updated_at"])
    return result


def abnormal_confirmation_summary(record):
    pending = record.lab_results.filter(
        is_abnormal=True,
        confirmation_status=LabResult.ConfirmationStatus.PENDING,
    )
    return {
        "has_pending_abnormal": pending.exists(),
        "pending_count": pending.count(),
        "pending_result_ids": list(pending.values_list("pk", flat=True)),
    }


def latest_lab_result(record, item_code):
    return (
        record.lab_results.filter(item_code=item_code)
        .annotate(effective_at=Coalesce("reported_at", "sampled_at", "created_at"))
        .order_by("-effective_at", "-created_at", "-pk")
        .first()
    )


def latest_standard_lab_value(record, item_code):
    result = latest_lab_result(record, item_code)
    if not result:
        return None
    return result.standard_value if result.standard_value is not None else result.value


def _threshold_for_ogtt(record, item_code):
    return resolve_threshold(
        item_code,
        category=ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS,
        department=getattr(record, "department", None),
    )


def calculate_ogtt_outcome(record, source_type="SYSTEM", source_ref=""):
    values = {}
    thresholds = {}
    triggered = []
    threshold_ids = []
    for code in ("FPG", "OGTT_1H", "OGTT_2H"):
        latest = latest_lab_result(record, code)
        if latest:
            values[code] = latest.standard_value if latest.standard_value is not None else latest.value
        threshold = _threshold_for_ogtt(record, code)
        thresholds[code] = threshold
        if threshold["config"]:
            threshold_ids.append(threshold["config"].pk)

    complete = all(code in values for code in ("FPG", "OGTT_1H", "OGTT_2H"))
    if not complete:
        outcome_value = OGTTOutcome.Outcome.INCOMPLETE
    else:
        for code in ("FPG", "OGTT_1H", "OGTT_2H"):
            threshold_value = thresholds[code]["value"]
            if threshold_value is not None and values[code] >= threshold_value:
                triggered.append(
                    {
                        "item_code": code,
                        "value": str(values[code]),
                        "threshold": str(threshold_value),
                        "unit": thresholds[code]["unit"],
                    }
                )
        outcome_value = OGTTOutcome.Outcome.GDM if triggered else OGTTOutcome.Outcome.NORMAL

    outcome, _ = OGTTOutcome.objects.update_or_create(
        maternal_record=record,
        defaults={
            "fasting_value": values.get("FPG"),
            "one_hour_value": values.get("OGTT_1H"),
            "two_hour_value": values.get("OGTT_2H"),
            "outcome": outcome_value,
            "confirmation_status": OGTTOutcome.ConfirmationStatus.PENDING,
            "threshold_json": {code: data["snapshot"] for code, data in thresholds.items()},
            "threshold_config_ids_json": threshold_ids,
            "triggered_thresholds_json": triggered,
            "source_type": source_type,
            "source_ref": source_ref,
        },
    )
    create_doctor_confirmation_reminder(outcome)
    return outcome


def confirm_ogtt_outcome(outcome, user=None, rejected=False):
    outcome.confirmation_status = (
        OGTTOutcome.ConfirmationStatus.REJECTED if rejected else OGTTOutcome.ConfirmationStatus.CONFIRMED
    )
    outcome.confirmed_by = user if getattr(user, "is_authenticated", False) else None
    outcome.confirmed_at = timezone.now()
    outcome.save(update_fields=["confirmation_status", "confirmed_by", "confirmed_at", "calculated_at"])
    if not rejected:
        create_doctor_confirmation_reminder(outcome)
    return outcome


def create_doctor_confirmation_reminder(outcome):
    record = outcome.maternal_record
    chain = (
        FollowupChain.objects.filter(
            maternal_record=record,
            status__in=[
                FollowupChain.Status.PENDING,
                FollowupChain.Status.BOOKED,
                FollowupChain.Status.IN_PROGRESS,
                FollowupChain.Status.WAIT_DOCTOR_CONFIRM,
                FollowupChain.Status.CONTINUE_TRACKING,
                FollowupChain.Status.PLANNED_NEXT,
                FollowupChain.Status.WAIT_ACTIVATE,
                FollowupChain.Status.OVERDUE,
                FollowupChain.Status.ACTIVE,
            ],
        )
        .order_by("-updated_at")
        .first()
    )
    if not chain:
        return None
    chain.status = FollowupChain.Status.WAIT_DOCTOR_CONFIRM
    chain.last_ogtt_outcome = outcome
    chain.save(update_fields=["status", "last_ogtt_outcome", "updated_at"])
    task, _ = FollowupTask.objects.get_or_create(
        chain=chain,
        task_type="OGTT_CONFIRM",
        status=FollowupTask.Status.WAIT_DOCTOR_CONFIRM,
        defaults={
            "task_name": "OGTT结局医生确认",
            "due_at": timezone.now() + timezone.timedelta(days=1),
        },
    )
    reminder, _ = SystemReminder.objects.get_or_create(
        task=task,
        reminder_type=SystemReminder.ReminderType.DOCTOR_CONFIRM,
        status=SystemReminder.Status.PENDING,
        defaults={
            "remind_at": timezone.now(),
            "message": f"{record.name} 的OGTT结局需要医生确认。",
        },
    )
    return reminder
