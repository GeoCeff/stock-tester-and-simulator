import json
import math

import pytest

from market_dashboard.modules.bot_model_pack import (
    DASHBOARD_STYLES,
    DEFAULT_MODEL_PACK_PATH,
    build_model_pack,
    write_model_pack,
)


def walk(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    else:
        yield value


def test_build_model_pack_exports_dashboard_contract(tmp_path):
    pack = build_model_pack(
        {
            "SWING_5D": {
                "enabled": True,
                "holding_period": 5,
                "min_probability": 0.58,
                "stop_atr": 2.0,
                "target_r": 2.0,
                "risk_pct": 0.005,
                "metrics": {"test_trades": 43, "test_profit_factor": float("inf")},
                "acceptance": {"status": "pass", "reason": "walk-forward passed"},
            }
        },
        ["msft", "AAPL"],
        created_at="2026-06-21T00:00:00Z",
    )

    assert pack["schema_version"] == 1
    assert pack["model_version"] == "backtester-walkforward-v1"
    assert set(pack["styles"]) == set(DASHBOARD_STYLES)
    assert pack["styles"]["SWING_5D"]["metrics"]["test_trades"] == 43
    assert pack["styles"]["SWING_5D"]["metrics"]["test_profit_factor"] is None
    assert pack["styles"]["SWING_5D"]["acceptance"]["status"] == "pass"
    assert pack["universe"] == ["AAPL", "MSFT"]
    assert not any(isinstance(value, float) and not math.isfinite(value) for value in walk(pack))

    path = tmp_path / "bot_model_pack.json"
    write_model_pack(pack, path)
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_build_model_pack_rejects_unknown_styles():
    with pytest.raises(ValueError):
        build_model_pack({"MOONSHOT": {}}, ["AAPL"])


def test_default_model_pack_path_targets_execution_dashboard():
    assert DEFAULT_MODEL_PACK_PATH.parts[-3:] == (
        "execution_dashboard",
        "data",
        "bot_model_pack.json",
    )
