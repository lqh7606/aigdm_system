from django.contrib import admin

from accounts.admin_permissions import RecordScopedAdminMixin

from .models import PreExclusionRecord, RiskAssessment


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "maternal_record"
    list_display = ("assessment_no", "maternal_record", "engine_type", "risk_level", "risk_probability", "model_version", "created_at")
    list_filter = ("engine_type", "risk_level", "assessment_status")
    search_fields = ("assessment_no", "maternal_record__record_no", "maternal_record__name", "degradation_reason")
    readonly_fields = ("created_at",)


@admin.register(PreExclusionRecord)
class PreExclusionRecordAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "maternal_record"
    list_display = ("maternal_record", "decision", "reason", "created_at")
    list_filter = ("decision",)
    search_fields = ("maternal_record__record_no", "maternal_record__name", "reason")
