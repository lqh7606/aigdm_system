from django.contrib import admin

from accounts.admin_permissions import RecordScopedAdminMixin

from .models import LabResult, OGTTOutcome


@admin.register(LabResult)
class LabResultAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "maternal_record"
    list_display = ("maternal_record", "item_name", "value", "unit", "is_abnormal", "confirmation_status", "reported_at")
    list_filter = ("item_code", "is_abnormal", "confirmation_status", "source_type")
    search_fields = ("maternal_record__record_no", "maternal_record__name", "item_name")


@admin.register(OGTTOutcome)
class OGTTOutcomeAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "maternal_record"
    list_display = ("maternal_record", "fasting_value", "one_hour_value", "two_hour_value", "outcome", "calculated_at")
    list_filter = ("outcome",)
    search_fields = ("maternal_record__record_no", "maternal_record__name")
