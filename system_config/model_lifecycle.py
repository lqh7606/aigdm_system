import hashlib
import importlib.util
import json
import re
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
MAX_VERSION_CODE_LENGTH = 120


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


def _safe_version_fragment(value, default="model"):
    fragment = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_-")
    return fragment or default


def normalize_version_code(value):
    version_code = _safe_version_fragment(value, default="")
    if not version_code:
        raise ModelLifecycleError("模型版本编码不能为空。")
    return version_code[:MAX_VERSION_CODE_LENGTH]


def _default_upload_version_code(uploaded_name, model_type):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    name_fragment = _safe_version_fragment(Path(uploaded_name or "model").stem)
    model_type_fragment = _safe_version_fragment(str(model_type).lower())
    return normalize_version_code(f"{timestamp}_{model_type_fragment}_{name_fragment}")


def _unique_upload_version_code(uploaded_name, model_type, requested_version_code=None):
    if requested_version_code:
        version_code = normalize_version_code(requested_version_code)
        release_root = Path(settings.MODEL_DIR) / "releases" / version_code
        if ModelVersion.objects.filter(version_code=version_code).exists() or release_root.exists():
            raise ModelLifecycleError(f"模型版本编码已存在：{version_code}")
        return version_code

    base_code = _default_upload_version_code(uploaded_name, model_type)
    for index in range(1, 1000):
        suffix = "" if index == 1 else f"_{index}"
        candidate = normalize_version_code(f"{base_code[:MAX_VERSION_CODE_LENGTH - len(suffix)]}{suffix}")
        release_root = Path(settings.MODEL_DIR) / "releases" / candidate
        if not ModelVersion.objects.filter(version_code=candidate).exists() and not release_root.exists():
            return candidate
    raise ModelLifecycleError("无法生成唯一的模型版本编码。")


def _write_uploaded_file(uploaded_file, artifact):
    with Path(artifact).open("wb") as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)


def create_release_from_uploaded_file(uploaded_file, model_type, version_code=None, display_name=None):
    original_name = getattr(uploaded_file, "name", "") or "model.pkl"
    if Path(original_name).suffix.lower() != ".pkl":
        raise ModelLifecycleError("仅支持上传 .pkl 模型文件。")

    model_type = model_type or ModelVersion.ModelType.FULL
    if model_type not in dict(ModelVersion.ModelType.choices):
        raise ModelLifecycleError("模型类型不合法。")

    version_code = _unique_upload_version_code(original_name, model_type, requested_version_code=version_code)
    display_name = display_name or Path(original_name).stem or version_code
    root = Path(settings.MODEL_DIR)
    release_root = root / "releases" / version_code
    release_root.mkdir(parents=True, exist_ok=False)
    artifact = release_root / "model.pkl"
    _write_uploaded_file(uploaded_file, artifact)

    checksum = sha256_file(artifact)
    (release_root / "sha256.txt").write_text(f"{checksum}  model.pkl\n", encoding="utf-8")
    feature_schema = {
        "version": "1.0",
        "model_type": model_type,
        "feature_order": [],
        "feature_source": "pending_model_introspection",
        "requires_manual_confirmation": True,
        "note": "系统会从上传的PKL模型元数据自动推断特征顺序。",
    }
    input_schema = {
        "type": "object",
        "required": [],
        "properties": {},
        "note": "由上传模型的特征顺序自动生成。",
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
        "model_family": ModelVersion.ModelFamily.UNKNOWN,
        "model_type": model_type,
        "sha256": checksum,
        "source_filename": original_name,
        "uploaded_at": timezone.now().isoformat(),
        "immutable_release": True,
    }
    write_json(release_root / "feature_schema.json", feature_schema)
    write_json(release_root / "input_schema.json", input_schema)
    write_json(release_root / "output_schema.json", output_schema)
    write_json(release_root / "manifest.json", manifest)

    model_version = ModelVersion.objects.create(
        version_code=version_code,
        display_name=display_name,
        model_type=model_type,
        artifact_format=ModelVersion.ArtifactFormat.PKL,
        model_family=ModelVersion.ModelFamily.UNKNOWN,
        artifact_path=relative_to_model_dir(artifact),
        sha256=checksum,
        status=ModelVersion.Status.DRAFT,
        manifest_json=manifest,
        feature_schema_json=feature_schema,
        input_schema_json=input_schema,
        output_schema_json=output_schema,
        status_message="已上传到不可变发布目录，尚未验证。",
    )
    return validate_model_version(model_version)


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


def _candidate_models(model):
    candidates = []
    seen = set()

    def add(candidate):
        if candidate is None or isinstance(candidate, str):
            return
        candidate_id = id(candidate)
        if candidate_id in seen:
            return
        seen.add(candidate_id)
        candidates.append(candidate)

    add(model)
    steps = getattr(model, "steps", None)
    if steps:
        for _, step_model in reversed(steps):
            add(step_model)
    return candidates


def _booster_for(model):
    getter = getattr(model, "get_booster", None)
    if not callable(getter):
        return None
    try:
        return getter()
    except Exception:
        return None


def infer_feature_order(model):
    for candidate in _candidate_models(model):
        feature_names = getattr(candidate, "feature_names_in_", None)
        if feature_names is not None:
            return [str(item) for item in feature_names]
        booster = _booster_for(candidate)
        if booster is not None and getattr(booster, "feature_names", None):
            return [str(item) for item in booster.feature_names]
    return []


def detect_model_family(model):
    for candidate in _candidate_models(model):
        module_name = candidate.__class__.__module__.lower()
        if "xgboost" in module_name or _booster_for(candidate) is not None:
            return ModelVersion.ModelFamily.XGBOOST
        if "sklearn" in module_name or "scikit" in module_name:
            return ModelVersion.ModelFamily.SKLEARN
    if hasattr(model, "predict_proba"):
        return ModelVersion.ModelFamily.SKLEARN
    return ModelVersion.ModelFamily.UNKNOWN


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
        manifest = read_json_if_exists(release_root / "manifest.json", model_version.manifest_json)

        import joblib

        started = time.monotonic()
        model = joblib.load(artifact)
        report["checks"]["load_seconds"] = round(time.monotonic() - started, 3)

        detected_family = detect_model_family(model)
        if detected_family != ModelVersion.ModelFamily.UNKNOWN:
            model_version.model_family = detected_family
            deps, missing = dependency_report(model_version)
            if missing:
                raise ModelValidationError(f"缺少Python依赖：{', '.join(missing)}")
            model_version.dependency_status_json = deps
            report["checks"]["dependencies"] = deps
        report["checks"]["model_family"] = model_version.model_family

        configured_feature_order = feature_schema.get("feature_order") or []
        feature_order = configured_feature_order or infer_feature_order(model)
        if not feature_order:
            raise ModelValidationError("无法从结构文件或模型元数据获得特征顺序，请使用保留特征名的模型或提供特征结构文件。")
        feature_schema["feature_order"] = feature_order
        feature_schema["feature_source"] = (feature_schema.get("feature_source") or "schema") if configured_feature_order else "model_metadata"
        report["checks"]["feature_count"] = len(feature_order)
        input_schema["type"] = input_schema.get("type") or "object"
        input_schema["required"] = input_schema.get("required") or feature_order
        properties = input_schema.setdefault("properties", {})
        for field in feature_order:
            properties.setdefault(field, {"type": "number"})
        manifest["model_family"] = model_version.model_family
        manifest["feature_count"] = len(feature_order)

        probe = validate_output(model, feature_order)
        report["checks"]["probe_output"] = probe
        report["finished_at"] = timezone.now().isoformat()

        model_version.status = ModelVersion.Status.STAGED
        model_version.status_message = "验证通过，可启用该模型版本。"
        model_version.feature_schema_json = feature_schema
        model_version.input_schema_json = input_schema
        model_version.output_schema_json = output_schema
        model_version.manifest_json = manifest
        model_version.validation_report_json = report
        model_version.dependency_status_json = deps
        model_version.save(
            update_fields=[
                "status",
                "status_message",
                "feature_schema_json",
                "input_schema_json",
                "output_schema_json",
                "manifest_json",
                "model_family",
                "validation_report_json",
                "dependency_status_json",
                "updated_at",
            ]
        )
        write_json(release_root / "feature_schema.json", feature_schema)
        write_json(release_root / "input_schema.json", input_schema)
        write_json(release_root / "output_schema.json", output_schema)
        write_json(release_root / "manifest.json", manifest)
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

    current_versions = list(
        ModelVersion.objects.select_for_update()
        .filter(model_type=locked.model_type, status=ModelVersion.Status.PRODUCTION)
        .exclude(pk=locked.pk)
        .order_by("-activated_at", "-updated_at", "-pk")
    )
    if current_versions:
        for current in current_versions:
            current.retire()
        locked.predecessor = current_versions[0]
        locked.save(update_fields=["predecessor", "updated_at"])

    locked.activate()
    from .model_runtime import ModelRegistry, PKLModelExecutor

    ModelRegistry.invalidate()
    PKLModelExecutor.invalidate()
    return locked

