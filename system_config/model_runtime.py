import time
from pathlib import Path

from django.conf import settings

from .model_lifecycle import absolute_artifact_path, probability_to_level
from .models import ModelVersion


class ModelExecutionError(Exception):
    pass


class ModelRegistry:
    _cached_versions = {}
    _cached_at = {}

    @classmethod
    def current_production(cls, model_type=ModelVersion.ModelType.FULL):
        ttl = getattr(settings, "MODEL_REGISTRY_TTL_SECONDS", 5)
        cached = cls._cached_versions.get(model_type)
        cached_at = cls._cached_at.get(model_type, 0)
        if cached and time.monotonic() - cached_at < ttl:
            return cached
        cls._cached_versions[model_type] = (
            ModelVersion.objects.filter(status=ModelVersion.Status.PRODUCTION, model_type=model_type)
            .order_by("-activated_at")
            .first()
        )
        cls._cached_at[model_type] = time.monotonic()
        return cls._cached_versions[model_type]

    @classmethod
    def invalidate(cls):
        cls._cached_versions = {}
        cls._cached_at = {}


class PKLModelExecutor:
    _model_cache = {}

    @classmethod
    def invalidate(cls, model_version_id=None):
        if model_version_id is None:
            cls._model_cache = {}
            return
        cls._model_cache.pop(model_version_id, None)

    @classmethod
    def _load(cls, model_version):
        cached = cls._model_cache.get(model_version.pk)
        if cached:
            return cached

        artifact = absolute_artifact_path(model_version)
        if not Path(artifact).exists():
            raise ModelExecutionError("GDM-503-002: 模型文件不存在。")

        try:
            import joblib

            model = joblib.load(artifact)
        except Exception as exc:
            raise ModelExecutionError(f"GDM-503-003: 模型加载失败：{exc}") from exc

        cls._model_cache[model_version.pk] = model
        return model

    @classmethod
    def predict(cls, model_version, feature_payload):
        model = cls._load(model_version)
        feature_order = model_version.feature_schema_json.get("feature_order") or []
        if not feature_order:
            raise ModelExecutionError("GDM-503-005: 模型特征顺序未配置。")
        try:
            import numpy as np

            missing = [field for field in feature_order if field not in feature_payload or feature_payload[field] in (None, "")]
            if missing:
                raise ModelExecutionError(f"GDM-503-006: 模型输入字段缺失：{', '.join(missing)}")
            vector = [float(feature_payload[field]) for field in feature_order]
            if not hasattr(model, "predict_proba"):
                raise ModelExecutionError("GDM-503-005: 模型未提供 predict_proba()。")
            probability = float(model.predict_proba(np.array([vector], dtype=float))[0][-1])
        except ModelExecutionError:
            raise
        except Exception as exc:
            raise ModelExecutionError(f"GDM-503-005: 模型输出异常：{exc}") from exc

        return {
            "risk_probability": probability,
            "risk_level": probability_to_level(probability),
            "factors": feature_order[:5],
        }

