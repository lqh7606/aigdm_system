import hashlib
import importlib.util
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ModelVersion


DEFAULT_SOURCE_MODEL = (
    "E:/个人项目/本科阶段/2023妇产科数据分析/妊娠期糖尿病/2025-6-15 二次大修/"
    "3-data_with_group_new_feature630/results_all_models/results_all_models/scheme_1/models/xgboost/"
    "ctgan55-tvae2_balanced_data_merged_ctgan_epochs450.pkl"
)
DEFAULT_VERSION_CODE = "20250701_xgboost_ctgan55_tvae2"
DEFAULT_RELEASE_DIR = "releases/20250701_xgboost_ctgan55_tvae2"


class ModelLifecycleError(Exception):
    pass


class ModelValidationError(ModelLifecycleError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json_if_exists(path, default):
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8-sig"))


def relative_to_model_dir(path):
    model_dir = Path(settings.MODEL_DIR).resolve()
    return str(Path(path).resolve().relative_to(model_dir)).replace("\\", "/")


def absolute_artifact_path(model_version):
    return Path(settings.MODEL_DIR) / model_version.artifact_path


def create_release_from_source(
    source_path=DEFAULT_SOURCE_MODEL,
    version_code=DEFAULT_VERSION_CODE,
    display_name="初始XGBoost GDM模型",
    release_dir=DEFAULT_RELEASE_DIR,
):
    existing_version = ModelVersion.objects.filter(version_code=version_code).first()
    if existing_version:
        return existing_version, absolute_artifact_path(existing_version)

    source = Path(source_path)
    if not source.exists():
        raise ModelLifecycleError(f"源模型文件不存在：{source}")

    root = Path(settings.MODEL_DIR)
    release_root = root / release_dir
    release_root.mkdir(parents=True, exist_ok=True)
    artifact = release_root / "model.pkl"
    source_checksum = sha256_file(source)
    if artifact.exists():
        artifact_checksum = sha256_file(artifact)
        if artifact_checksum != source_checksum:
            raise ModelLifecycleError(f"发布目录中已存在校验和不同的模型文件：{artifact}")
    else:
        shutil.copy2(source, artifact)
    checksum = sha256_file(artifact)
    (release_root / "sha256.txt").write_text(f"{checksum}  model.pkl\n", encoding="utf-8")

    feature_schema = {
        "version": "1.0",
        "model_type": "FULL",
        "feature_order": [],
        "feature_source": "pending_model_introspection",
        "requires_manual_confirmation": True,
        "note": "可用时从模型对象推断特征顺序，正式临床使用前需人工确认。",
    }
    input_schema = {
        "type": "object",
        "required": [],
        "properties": {},
        "note": "正式临床使用前需由算法交付包补齐。",
    }
    output_schema = {
        "risk_probability": "number[0,1]",
        "risk_level": "LOW|MEDIUM|HIGH",
        "factors": "string[]",
    }
    manifest = {
        "version_code": version_code,
        "display_name": display_name,
        "artifact_file": "model.pkl",
        "artifact_format": "PKL",
        "model_family": "XGBOOST",
        "sha256": checksum,
        "source_path": str(source),
        "copied_at": timezone.now().isoformat(),
        "immutable_release": True,
    }
    write_json(release_root / "feature_schema.json", feature_schema)
    write_json(release_root / "input_schema.json", input_schema)
    write_json(release_root / "output_schema.json", output_schema)
    write_json(release_root / "manifest.json", manifest)

    model_version = ModelVersion.objects.create(
        version_code=version_code,
        display_name=display_name,
        model_type=ModelVersion.ModelType.FULL,
        artifact_format=ModelVersion.ArtifactFormat.PKL,
        model_family=ModelVersion.ModelFamily.XGBOOST,
        artifact_path=relative_to_model_dir(artifact),
        sha256=checksum,
        status=ModelVersion.Status.DRAFT,
        manifest_json=manifest,
        feature_schema_json=feature_schema,
        input_schema_json=input_schema,
        output_schema_json=output_schema,
        status_message="已复制到不可变发布目录，尚未验证。",
    )
    return model_version, artifact


def dependency_report(model_version):
    required = ["joblib"]
    if model_version.model_family == ModelVersion.ModelFamily.XGBOOST:
        required.append("xgboost")
    report = {name: bool(importlib.util.find_spec(name)) for name in required}
    missing = [name for name, available in report.items() if not available]
    return report, missing


def infer_feature_order(model):
    feature_names = getattr(model, "feature_names_in_", None)
    if feature_names is not None:
        return [str(item) for item in feature_names]
    booster = getattr(model, "get_booster", lambda: None)()
    if booster is not None and getattr(booster, "feature_names", None):
        return [str(item) for item in booster.feature_names]
    return []


def probability_to_level(probability):
    if probability >= 0.7:
        return "HIGH"
    if probability >= 0.4:
        return "MEDIUM"
    return "LOW"


def validate_output(model, feature_order):
    import numpy as np

    if not hasattr(model, "predict_proba"):
        raise ModelValidationError("模型未提供 predict_proba()。")
    sample = np.zeros((1, len(feature_order)), dtype=float)
    output = model.predict_proba(sample)
    probability = float(output[0][-1])
    if not 0 <= probability <= 1:
        raise ModelValidationError(f"模型返回的概率不合法：{probability}")
    return {
        "risk_probability": probability,
        "risk_level": probability_to_level(probability),
        "factors": feature_order[:5],
    }


def validate_model_version(model_version):
    artifact = absolute_artifact_path(model_version)
    release_root = artifact.parent
    report = {
        "artifact_path": str(artifact),
        "started_at": timezone.now().isoformat(),
        "checks": {},
    }
    model_version.status = ModelVersion.Status.VALIDATING
    model_version.status_message = "模型验证已开始。"
    model_version.save(update_fields=["status", "status_message", "updated_at"])

    try:
        if not artifact.exists():
            raise ModelValidationError(f"模型文件不存在：{artifact}")
        actual_sha = sha256_file(artifact)
        if actual_sha != model_version.sha256:
            raise ModelValidationError("数据库记录与模型文件的SHA256不一致。")
        report["checks"]["sha256"] = "ok"

        deps, missing = dependency_report(model_version)
        model_version.dependency_status_json = deps
        if missing:
            raise ModelValidationError(f"缺少Python依赖：{', '.join(missing)}")
        report["checks"]["dependencies"] = deps

        feature_schema = read_json_if_exists(release_root / "feature_schema.json", model_version.feature_schema_json)
        input_schema = read_json_if_exists(release_root / "input_schema.json", model_version.input_schema_json)
        output_schema = read_json_if_exists(release_root / "output_schema.json", model_version.output_schema_json)

        import joblib

        started = time.monotonic()
        model = joblib.load(artifact)
        report["checks"]["load_seconds"] = round(time.monotonic() - started, 3)

        feature_order = feature_schema.get("feature_order") or infer_feature_order(model)
        if not feature_order:
            raise ModelValidationError("无法从结构文件或模型元数据获得特征顺序。")
        feature_schema["feature_order"] = feature_order
        feature_schema["feature_source"] = feature_schema.get("feature_source") or "model_metadata"
        report["checks"]["feature_count"] = len(feature_order)

        probe = validate_output(model, feature_order)
        report["checks"]["probe_output"] = probe
        report["finished_at"] = timezone.now().isoformat()

        model_version.status = ModelVersion.Status.STAGED
        model_version.status_message = "验证通过，可启用该模型版本。"
        model_version.feature_schema_json = feature_schema
        model_version.input_schema_json = input_schema
        model_version.output_schema_json = output_schema
        model_version.validation_report_json = report
        model_version.dependency_status_json = deps
        model_version.save(
            update_fields=[
                "status",
                "status_message",
                "feature_schema_json",
                "input_schema_json",
                "output_schema_json",
                "validation_report_json",
                "dependency_status_json",
                "updated_at",
            ]
        )
        write_json(release_root / "feature_schema.json", feature_schema)
        return model_version
    except Exception as exc:
        report["finished_at"] = timezone.now().isoformat()
        report["error"] = str(exc)
        model_version.status = ModelVersion.Status.FAILED
        model_version.status_message = str(exc)
        model_version.validation_report_json = report
        model_version.save(
            update_fields=[
                "status",
                "status_message",
                "validation_report_json",
                "dependency_status_json",
                "updated_at",
            ]
        )
        raise


@transaction.atomic
def activate_model_version(model_version):
    locked = ModelVersion.objects.select_for_update().get(pk=model_version.pk)
    if locked.status not in {ModelVersion.Status.STAGED, ModelVersion.Status.RETIRED}:
        raise ModelLifecycleError("只能启用待启用或已停用且验证通过的模型版本。")

    current = (
        ModelVersion.objects.select_for_update()
        .filter(model_type=locked.model_type, status=ModelVersion.Status.PRODUCTION)
        .exclude(pk=locked.pk)
        .first()
    )
    if current:
        current.retire()
        locked.predecessor = current
        locked.save(update_fields=["predecessor", "updated_at"])

    locked.activate()
    return locked

