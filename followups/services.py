from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import FollowupChain, FollowupTask, InterventionRecord, SystemReminder


RISK_FOLLOWUP_LABELS = {
    "MEDIUM": "中危",
    "HIGH": "高危",
}

ACTIVE_CHAIN_STATUSES = [
    FollowupChain.Status.PENDING,
    FollowupChain.Status.BOOKED,
    FollowupChain.Status.IN_PROGRESS,
    FollowupChain.Status.WAIT_DOCTOR_CONFIRM,
    FollowupChain.Status.CONTINUE_TRACKING,
    FollowupChain.Status.PLANNED_NEXT,
    FollowupChain.Status.WAIT_ACTIVATE,
    FollowupChain.Status.OVERDUE,
    FollowupChain.Status.ACTIVE,
]

TERMINAL_CHAIN_STATUSES = [
    FollowupChain.Status.CLOSED,
    FollowupChain.Status.TRANSFER_COMPLETED,
    FollowupChain.Status.LOST_CONFIRMED,
    FollowupChain.Status.CANCELLED,
]


def _append_assessment(chain, assessment):
    if not assessment:
        return
    ids = list(chain.last_assessment_ids_json or [])
    if assessment.pk not in ids:
        ids.append(assessment.pk)
        chain.last_assessment_ids_json = ids
        chain.risk_assessment = chain.risk_assessment or assessment
        chain.save(update_fields=["last_assessment_ids_json", "risk_assessment", "updated_at"])


def active_chain_for_record(record):
    return (
        FollowupChain.objects.filter(dedup_active_record=record)
        .filter(status__in=ACTIVE_CHAIN_STATUSES)
        .order_by("-updated_at")
        .first()
    ) or (
        FollowupChain.objects.filter(maternal_record=record, status__in=ACTIVE_CHAIN_STATUSES)
        .order_by("-updated_at")
        .first()
    )


@transaction.atomic
def ensure_risk_followup(record, assessment=None, risk_level="HIGH", reason=None):
    risk_label = RISK_FOLLOWUP_LABELS.get(str(risk_level or "").upper(), "高危")
    reason = reason or f"{risk_label}风险评估"
    locked_record = type(record).objects.select_for_update().get(pk=record.pk)
    active = active_chain_for_record(locked_record)
    if active:
        _append_assessment(active, assessment)
        return active, False

    try:
        chain = FollowupChain.objects.create(
            maternal_record=locked_record,
            dedup_active_record=locked_record,
            risk_assessment=assessment,
            status=FollowupChain.Status.WAIT_ACTIVATE,
            reason=reason,
            next_followup_at=timezone.now() + timezone.timedelta(days=7),
            last_assessment_ids_json=[assessment.pk] if assessment else [],
        )
    except IntegrityError:
        active = active_chain_for_record(locked_record)
        if active:
            _append_assessment(active, assessment)
            return active, False
        raise

    task = FollowupTask.objects.create(
        chain=chain,
        task_name=f"{risk_label}孕妇首次随访",
        task_type="FIRST_FOLLOWUP",
        due_at=chain.next_followup_at,
    )
    SystemReminder.objects.create(
        task=task,
        reminder_type=SystemReminder.ReminderType.DUE,
        remind_at=timezone.now() + timezone.timedelta(days=1),
        message=f"{locked_record.name} 需要完成{risk_label}孕妇首次随访。",
    )
    InterventionRecord.objects.create(
        chain=chain,
        intervention_type=InterventionRecord.InterventionType.EDUCATION,
        content=f"系统已生成{risk_label}随访链，请护士完成首次随访并记录干预措施。",
    )
    return chain, True


def ensure_high_risk_followup(record, assessment=None, reason="高危风险评估"):
    return ensure_risk_followup(record, assessment=assessment, risk_level="HIGH", reason=reason)


def complete_followup_task(task, result_text, user=None):
    task.status = FollowupTask.Status.DONE
    task.result_text = result_text
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "result_text", "finished_at", "updated_at"])
    chain = task.chain
    if chain.status not in TERMINAL_CHAIN_STATUSES:
        chain.status = FollowupChain.Status.WAIT_DOCTOR_CONFIRM
        chain.save(update_fields=["status", "updated_at"])
    InterventionRecord.objects.create(
        chain=chain,
        intervention_type=InterventionRecord.InterventionType.EDUCATION,
        content=result_text,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    return task


def cancel_followup_task(task, reason="", user=None):
    if task.status == FollowupTask.Status.CANCELLED:
        raise ValueError("该随访任务已取消。")
    if task.status == FollowupTask.Status.DONE:
        raise ValueError("已完成的随访任务不能删除。")
    reason = (reason or "").strip() or "页面删除，任务已取消。"
    task.status = FollowupTask.Status.CANCELLED
    task.result_text = reason
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "result_text", "finished_at", "updated_at"])
    task.reminders.filter(status=SystemReminder.Status.PENDING).update(
        status=SystemReminder.Status.CANCELLED,
        handled_by=user if getattr(user, "is_authenticated", False) else None,
        handled_at=timezone.now(),
    )
    InterventionRecord.objects.create(
        chain=task.chain,
        intervention_type=InterventionRecord.InterventionType.EDUCATION,
        content=f"随访任务已取消：{reason}",
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    return task


def confirm_followup_outcome(task, decision="CLOSE", comment="", next_followup_at=None, user=None):
    chain = task.chain
    decision = decision or "CLOSE"
    comment = (comment or "").strip()
    task_note = f"{task.result_text}\n\n医生确认：{comment or decision}".strip()
    task.result_text = task_note
    task.save(update_fields=["result_text", "updated_at"])

    if decision == "CONTINUE":
        chain.status = FollowupChain.Status.CONTINUE_TRACKING
        chain.next_followup_at = next_followup_at or chain.next_followup_at
        chain.save(update_fields=["status", "next_followup_at", "updated_at"])
    elif decision == "PLAN_NEXT":
        chain.status = FollowupChain.Status.PLANNED_NEXT
        chain.next_followup_at = next_followup_at or chain.next_followup_at
        chain.save(update_fields=["status", "next_followup_at", "updated_at"])
    elif decision == "TRANSFER":
        close_followup_chain(chain, FollowupChain.Status.TRANSFER_COMPLETED)
    elif decision == "LOST":
        close_followup_chain(chain, FollowupChain.Status.LOST_CONFIRMED)
    else:
        close_followup_chain(chain, FollowupChain.Status.CLOSED)

    InterventionRecord.objects.create(
        chain=chain,
        intervention_type=InterventionRecord.InterventionType.EDUCATION,
        content=f"医生确认随访结局：{comment or decision}",
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    return task


def close_followup_chain(chain, status=FollowupChain.Status.CLOSED):
    if status not in TERMINAL_CHAIN_STATUSES:
        raise ValueError("status must be terminal")
    chain.status = status
    chain.dedup_active_record = None
    chain.closed_at = timezone.now()
    chain.save(update_fields=["status", "dedup_active_record", "closed_at", "updated_at"])
    return chain
