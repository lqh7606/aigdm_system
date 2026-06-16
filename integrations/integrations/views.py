from django.http import HttpResponse
from django.shortcuts import redirect, render

from accounts.permissions import PermissionAction, require_action_or_response
from audit.models import AuditLog
from audit.services import write_audit_log
from common.api import error, ok, parse_json_body

from .models import ImportBatch, IntegrationSource, IntegrationTask
from .services import (
    build_import_template_csv,
    build_import_template_xlsx,
    get_active_import_template,
    get_or_create_mock_source,
    import_lab_rows,
    import_rows,
    normalize_import_kind,
    parse_csv_text,
    parse_uploaded_file,
    run_mock_pull,
)


def integration_home(request):
    denied = require_action_or_response(request, PermissionAction.VIEW_INTEGRATIONS)
    if denied:
        return denied
    get_or_create_mock_source()
    return render(
        request,
        "integrations/home.html",
        {
            "sources": IntegrationSource.objects.all(),
            "tasks": IntegrationTask.objects.select_related("source")[:20],
            "batches": ImportBatch.objects.select_related("source")[:20],
            "maternal_template": get_active_import_template(ImportBatch.ImportKind.MATERNAL_RECORD),
            "lab_template": get_active_import_template(ImportBatch.ImportKind.LAB_RESULT),
        },
    )


def run_mock_pull_view(request):
    denied = require_action_or_response(request, PermissionAction.RUN_INTEGRATION_TASK)
    if denied:
        return denied
    source = get_or_create_mock_source()
    task = run_mock_pull(source)
    write_audit_log(request, AuditLog.Action.IMPORT, "IntegrationTask", task.pk, "执行 HIS/EMR 拉取任务")
    return redirect("integrations:home")


def upload_import_file(request):
    if request.method != "POST":
        return redirect("integrations:home")
    denied = require_action_or_response(request, PermissionAction.UPLOAD_EXCEL_IMPORT)
    if denied:
        return denied
    uploaded_file = request.FILES.get("import_file")
    if not uploaded_file:
        return redirect("integrations:home")

    import_kind = normalize_import_kind(request.POST.get("import_kind"))
    try:
        rows = parse_uploaded_file(uploaded_file)
    except (UnicodeDecodeError, ValueError) as exc:
        batch = ImportBatch.objects.create(
            import_kind=import_kind,
            file_name=uploaded_file.name,
            status=ImportBatch.Status.FAILED,
            total_rows=0,
            failed_rows=1,
            error_json=[
                {
                    "row": 1,
                    "rule": "FILE-PARSE",
                    "message": f"文件解析失败：{exc}",
                }
            ],
        )
        write_audit_log(request, AuditLog.Action.IMPORT, "ImportBatch", batch.pk, f"导入文件解析失败：{uploaded_file.name}")
        return redirect("integrations:home")
    if import_kind == ImportBatch.ImportKind.LAB_RESULT:
        batch = import_lab_rows(uploaded_file.name, rows)
    else:
        batch = import_rows(uploaded_file.name, rows)
    write_audit_log(request, AuditLog.Action.IMPORT, "ImportBatch", batch.pk, f"导入文件：{uploaded_file.name}")
    return redirect("integrations:home")


def download_import_template(request):
    denied = require_action_or_response(request, PermissionAction.VIEW_INTEGRATIONS)
    if denied:
        return denied
    import_kind = normalize_import_kind(request.GET.get("kind"))
    template = get_active_import_template(import_kind)
    base_name = "aigdm_lab_import_template" if import_kind == ImportBatch.ImportKind.LAB_RESULT else "aigdm_record_import_template"

    if request.GET.get("format", "").lower() == "csv":
        response = HttpResponse(build_import_template_csv(template), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{base_name}.csv"'
        return response

    try:
        content = build_import_template_xlsx(template)
    except ImportError:
        response = HttpResponse(build_import_template_csv(template), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{base_name}.csv"'
        return response

    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{base_name}.xlsx"'
    return response


def import_precheck_api(request):
    if request.method != "POST":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    denied = require_action_or_response(request, PermissionAction.UPLOAD_EXCEL_IMPORT)
    if denied:
        return denied
    payload = parse_json_body(request)
    rows = payload.get("rows")
    if rows is None and payload.get("csv_text"):
        rows = parse_csv_text(payload["csv_text"])
    if not isinstance(rows, list):
        return error("请提交 rows 数组或 csv_text 文本。")

    import_kind = normalize_import_kind(payload.get("import_kind"))
    file_name = payload.get("file_name", "api导入.csv")
    batch = import_lab_rows(file_name, rows) if import_kind == ImportBatch.ImportKind.LAB_RESULT else import_rows(file_name, rows)
    return ok(
        {
            "批次ID": batch.pk,
            "导入类型": batch.get_import_kind_display(),
            "状态": batch.get_status_display(),
            "总行数": batch.total_rows,
            "成功行数": batch.success_rows,
            "失败行数": batch.failed_rows,
            "覆盖行数": batch.overwritten_rows,
            "错误明细": batch.error_json,
        },
        status=201,
    )


def integration_tasks_api(request):
    if request.method == "GET":
        denied = require_action_or_response(request, PermissionAction.VIEW_INTEGRATIONS)
        if denied:
            return denied
        return ok(
            [
                {
                    "id": item.pk,
                    "接入源": item.source.name,
                    "状态": item.get_status_display(),
                    "读取数量": item.pulled_count,
                    "错误信息": item.error_message,
                }
                for item in IntegrationTask.objects.select_related("source")[:100]
            ]
        )
    if request.method == "POST":
        denied = require_action_or_response(request, PermissionAction.RUN_INTEGRATION_TASK)
        if denied:
            return denied
        source = get_or_create_mock_source()
        task = run_mock_pull(source)
        return ok({"任务ID": task.pk, "状态": task.get_status_display(), "读取数量": task.pulled_count}, status=201)
    return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
