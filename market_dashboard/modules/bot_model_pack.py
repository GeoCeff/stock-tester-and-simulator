"""Dashboard model-pack export helpers."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path


DASHBOARD_STYLES = ("DAY_TRADE", "OVERNIGHT_1D", "SWING_5D", "SWING_20D")
DEFAULT_MODEL_PACK_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "bot_model_pack.json"
)


def _clean(value):
    if hasattr(value, "item"):
        return _clean(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


def _style_result(results, style):
    if hasattr(results, "get"):
        return results.get(style, {})
    return getattr(results, style, {})


def build_model_pack(results, universe, created_at=None):
    """Build the JSON artifact consumed by the execution dashboard."""
    if hasattr(results, "keys"):
        unknown = set(results.keys()) - set(DASHBOARD_STYLES)
        if unknown:
            raise ValueError(f"unsupported dashboard style(s): {', '.join(sorted(unknown))}")
    timestamp = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    styles = {}
    for style in DASHBOARD_STYLES:
        raw = _style_result(results, style) or {}
        metrics = raw.get("metrics", raw) if hasattr(raw, "get") else {}
        acceptance = raw.get("acceptance", {}) if hasattr(raw, "get") else {}
        styles[style] = {
            "enabled": bool(raw.get("enabled", False)) if hasattr(raw, "get") else False,
            "strategy": str(raw.get("strategy", "")) if hasattr(raw, "get") else "",
            "holding_period": int(raw.get("holding_period", 0) or 0) if hasattr(raw, "get") else 0,
            "min_probability": float(raw.get("min_probability", raw.get("minProb", 0.0)) or 0.0) if hasattr(raw, "get") else 0.0,
            "stop_atr": float(raw.get("stop_atr", raw.get("stopAtr", 0.0)) or 0.0) if hasattr(raw, "get") else 0.0,
            "target_r": float(raw.get("target_r", raw.get("targetR", 0.0)) or 0.0) if hasattr(raw, "get") else 0.0,
            "risk_pct": float(raw.get("risk_pct", raw.get("riskPct", 0.0)) or 0.0) if hasattr(raw, "get") else 0.0,
            "metrics": metrics,
            "acceptance": {
                "status": acceptance.get("status", "reject") if hasattr(acceptance, "get") else "reject",
                "reason": acceptance.get("reason", "not evaluated") if hasattr(acceptance, "get") else "not evaluated",
            },
        }
    return _clean({
        "schema_version": 1,
        "created_at": timestamp,
        "source_project": "stock-backtester",
        "model_version": "backtester-walkforward-v1",
        "universe": sorted({str(symbol).upper() for symbol in universe if str(symbol).strip()}),
        "styles": styles,
        "symbol_overrides": {},
    })


def write_model_pack(pack, path=None):
    """Write directly to the execution dashboard unless another path is supplied."""
    path = Path(path or DEFAULT_MODEL_PACK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(_clean(pack), indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
