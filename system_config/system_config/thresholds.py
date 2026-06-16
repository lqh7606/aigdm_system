from decimal import Decimal, InvalidOperation

from .models import ThresholdConfig


DEFAULT_THRESHOLDS = {
    "FPG": {"value": Decimal("5.100"), "unit": "mmol/L", "category": ThresholdConfig.ThresholdCategory.LAB_ABNORMAL},
    "OGTT_1H": {"value": Decimal("10.000"), "unit": "mmol/L", "category": ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS},
    "OGTT_2H": {"value": Decimal("8.500"), "unit": "mmol/L", "category": ThresholdConfig.ThresholdCategory.OGTT_DIAGNOSIS},
    "TG": {"value": Decimal("1.700"), "unit": "mmol/L", "category": ThresholdConfig.ThresholdCategory.LAB_ABNORMAL},
}

GLUCOSE_CODES = {"FPG", "OGTT_1H", "OGTT_2H"}
LIPID_CODES = {"TG"}


def decimal_value(value):
    if value in (None, ""):
        raise ValueError("value is required")
    try:
        return Decimal(str(value)).quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal value") from exc


def _normalized_unit(unit):
    return str(unit or "mmol/L").strip() or "mmol/L"


def convert_to_standard_unit(item_code, value, source_unit=None, target_unit="mmol/L"):
    source_unit = _normalized_unit(source_unit)
    target_unit = _normalized_unit(target_unit)
    value = decimal_value(value)
    if source_unit.lower() == target_unit.lower():
        return value, target_unit
    source = source_unit.lower()
    target = target_unit.lower()
    if target == "mmol/l" and source == "mg/dl":
        if item_code in GLUCOSE_CODES:
            return (value / Decimal("18.0182")).quantize(Decimal("0.001")), target_unit
        if item_code in LIPID_CODES:
            return (value / Decimal("88.57")).quantize(Decimal("0.001")), target_unit
    raise ValueError(f"unsupported unit conversion: {source_unit} -> {target_unit}")


def active_threshold_config(code, category=None, department=None):
    queryset = ThresholdConfig.objects.filter(code=code, is_active=True)
    if category:
        queryset = queryset.filter(category=category)
    if department is not None:
        department_config = (
            queryset.filter(scope_type=ThresholdConfig.ScopeType.DEPARTMENT, department=department)
            .order_by("-active_from", "-updated_at")
            .first()
        )
        if department_config:
            return department_config
    return (
        queryset.filter(scope_type=ThresholdConfig.ScopeType.GLOBAL)
        .order_by("-active_from", "-updated_at")
        .first()
    )


def resolve_threshold(code, category=None, department=None):
    config = active_threshold_config(code, category=category, department=department)
    if config:
        return {
            "config": config,
            "value": Decimal(str(config.value)).quantize(Decimal("0.001")),
            "unit": config.unit or "mmol/L",
            "snapshot": config.snapshot(),
            "source": "CONFIG",
        }
    fallback = DEFAULT_THRESHOLDS.get(code)
    if not fallback:
        return {"config": None, "value": None, "unit": None, "snapshot": {}, "source": "NONE"}
    return {
        "config": None,
        "value": fallback["value"],
        "unit": fallback["unit"],
        "snapshot": {
            "id": None,
            "code": code,
            "category": category or fallback["category"],
            "version": "fallback",
            "value": str(fallback["value"]),
            "unit": fallback["unit"],
            "source": "DEFAULT_FALLBACK",
        },
        "source": "DEFAULT_FALLBACK",
    }


def threshold_snapshot_for_codes(codes, category=None, department=None):
    snapshot = {}
    for code in codes:
        snapshot[code] = resolve_threshold(code, category=category, department=department)["snapshot"]
    return snapshot
