from django.contrib import admin

from accounts.admin_permissions import RecordScopedAdminMixin

from .models import FollowupChain, FollowupTask, InterventionRecord, SystemReminder


class FollowupTaskInline(admin.TabularInline):
    model = FollowupTask
    extra = 0


@admin.register(FollowupChain)
class FollowupChainAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "maternal_record"
    list_display = ("maternal_record", "status", "reason", "activated_at", "closed_at", "created_at")
    list_filter = ("status",)
    search_fields = ("maternal_record__record_no", "maternal_record__name", "reason")
    inlines = [FollowupTaskInline]


@admin.register(FollowupTask)
class FollowupTaskAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "chain__maternal_record"
    list_display = ("task_name", "chain", "status", "due_at", "assigned_to")
    list_filter = ("status",)
    search_fields = ("task_name", "chain__maternal_record__name")


@admin.register(InterventionRecord)
class InterventionRecordAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "chain__maternal_record"
    list_display = ("chain", "intervention_type", "created_by", "created_at")
    list_filter = ("intervention_type",)


@admin.register(SystemReminder)
class SystemReminderAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "task__chain__maternal_record"
    list_display = ("task", "remind_at", "status", "message")
    list_filter = ("status",)
