from django.shortcuts import render

from common.api import ok
from followups.models import FollowupTask
from integrations.models import IntegrationTask
from labs.models import LabResult, OGTTOutcome
from maternal_records.models import MaternalRecord
from maternal_records.services import completeness_for_risk, visible_records_for_user
from risk.models import RiskAssessment
from system_config.models import ModelVersion, SystemNotice


def home(request):
    visible_records = visible_records_for_user(request.user).exclude(status=MaternalRecord.Status.ARCHIVED)
    visible_record_list = list(visible_records)
    complete_records = sum(1 for record in visible_record_list if completeness_for_risk(record)["complete"])
    record_count = len(visible_record_list)
    pending_abnormal = LabResult.objects.filter(
        maternal_record__in=visible_records,
        is_abnormal=True,
        confirmation_status=LabResult.ConfirmationStatus.PENDING,
    ).count()
    pending_followups = FollowupTask.objects.filter(
        chain__maternal_record__in=visible_records,
        status=FollowupTask.Status.PENDING,
    ).count()
    completed_followups = FollowupTask.objects.filter(chain__maternal_record__in=visible_records, status=FollowupTask.Status.DONE).count()
    total_followups = FollowupTask.objects.filter(chain__maternal_record__in=visible_records).count()
    overdue_followups = FollowupTask.objects.filter(chain__maternal_record__in=visible_records, status=FollowupTask.Status.OVERDUE).count()
    ogtt_returned = OGTTOutcome.objects.filter(maternal_record__in=visible_records).exclude(outcome=OGTTOutcome.Outcome.INCOMPLETE).count()
    latest_task = IntegrationTask.objects.select_related("source").first()
    notices = SystemNotice.objects.filter(is_active=True)[:5]
    return render(
        request,
        "dashboard/home.html",
        {
            "record_count": record_count,
            "field_completion_rate": round(complete_records / record_count * 100, 1) if record_count else 0,
            "pending_abnormal": pending_abnormal,
            "pending_followups": pending_followups,
            "followup_completion_rate": round(completed_followups / total_followups * 100, 1) if total_followups else 0,
            "overdue_followups": overdue_followups,
            "ogtt_return_rate": round(ogtt_returned / record_count * 100, 1) if record_count else 0,
            "high_risk_count": RiskAssessment.objects.filter(maternal_record__in=visible_records, risk_level=RiskAssessment.RiskLevel.HIGH).count(),
            "model_count": ModelVersion.objects.count(),
            "production_model": ModelVersion.objects.filter(status=ModelVersion.Status.PRODUCTION).first(),
            "staged_count": ModelVersion.objects.filter(status=ModelVersion.Status.STAGED).count(),
            "failed_count": ModelVersion.objects.filter(status=ModelVersion.Status.FAILED).count(),
            "assessment_count": RiskAssessment.objects.count(),
            "latest_task": latest_task,
            "notices": notices,
        },
    )


def metrics_api(request):
    visible_records = visible_records_for_user(request.user)
    visible_record_list = list(visible_records)
    record_count = len(visible_record_list)
    complete_records = sum(1 for record in visible_record_list if completeness_for_risk(record)["complete"])
    total_followups = FollowupTask.objects.filter(chain__maternal_record__in=visible_records).count()
    completed_followups = FollowupTask.objects.filter(chain__maternal_record__in=visible_records, status=FollowupTask.Status.DONE).count()
    ogtt_returned = OGTTOutcome.objects.filter(maternal_record__in=visible_records).exclude(outcome=OGTTOutcome.Outcome.INCOMPLETE).count()
    return ok(
        {
            "档案总数": record_count,
            "字段完整率": round(complete_records / record_count * 100, 1) if record_count else 0,
            "待确认异常": LabResult.objects.filter(
                maternal_record__in=visible_records,
                is_abnormal=True,
                confirmation_status=LabResult.ConfirmationStatus.PENDING,
            ).count(),
            "待随访": FollowupTask.objects.filter(chain__maternal_record__in=visible_records, status=FollowupTask.Status.PENDING).count(),
            "随访完成率": round(completed_followups / total_followups * 100, 1) if total_followups else 0,
            "逾期任务": FollowupTask.objects.filter(chain__maternal_record__in=visible_records, status=FollowupTask.Status.OVERDUE).count(),
            "OGTT结局回收率": round(ogtt_returned / record_count * 100, 1) if record_count else 0,
            "高危评估": RiskAssessment.objects.filter(maternal_record__in=visible_records, risk_level=RiskAssessment.RiskLevel.HIGH).count(),
            "生产模型": ModelVersion.objects.filter(status=ModelVersion.Status.PRODUCTION).first().version_code
            if ModelVersion.objects.filter(status=ModelVersion.Status.PRODUCTION).exists()
            else None,
        }
    )

