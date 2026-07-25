import numpy as np
import pandas as pd

import json

import market_dashboard.modules.research_agent as research_agent
from market_dashboard.modules.research_agent import publish_research_result, run_research_loop, update_paper_ledger


def test_research_loop_accepts_consistent_out_of_sample_trend(tmp_path):
    index = pd.date_range("2024-01-01", periods=360, freq="B")
    close = pd.Series(np.linspace(50, 140, len(index)), index=index)
    data = pd.DataFrame({
        ("Open", "TEST"): close * 0.999,
        ("High", "TEST"): close * 1.01,
        ("Low", "TEST"): close * 0.99,
        ("Close", "TEST"): close,
        ("Volume", "TEST"): 1_000_000,
    })
    data.columns = pd.MultiIndex.from_tuples(data.columns)

    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[{"style": "SWING_5D", "strategy": "ma_crossover"}],
        folds=4,
        warmup=200,
        gates={"min_development_trades": 6, "min_final_trades": 2},
    )

    assert result["styles"]["SWING_5D"]["acceptance"]["status"] == "pass"
    assert result["entries"][0]["entry"] > result["entries"][0]["stop"]
    assert result["entries"][0]["target"] > result["entries"][0]["entry"]

    model_path = tmp_path / "bot_model_pack.json"
    agent_path = tmp_path / "research_agent.json"
    pack = publish_research_result(result, model_pack_path=model_path, agent_result_path=agent_path)
    assert pack["styles"]["SWING_5D"]["strategy"] == "ma_crossover"
    assert json.loads(agent_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_research_loop_requires_a_separate_final_holdout():
    with np.testing.assert_raises_regex(ValueError, "at least four folds"):
        run_research_loop(pd.DataFrame(), ["TEST"], folds=3)


def test_research_loop_skips_high_score_candidate_that_fails_development_gates(monkeypatch):
    index = pd.date_range("2024-01-01", periods=360, freq="B")
    data = pd.DataFrame({("Close", "TEST"): np.arange(360) + 100}, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    final_exposures = []

    def fake_evaluate(frame, universe, candidate, **kwargs):
        final_exposures.append(candidate["strategy"]) if len(frame) == len(data) else None
        passing = candidate["strategy"] == "good"
        metric = {
            "trades": 100,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "max_drawdown": -0.1 if passing else -0.2,
            "total_return": 0.2,
        }
        development = {**metric, "positive_fold_ratio": 1.0}
        return {**candidate, "development": development, "final": metric, "folds": [metric], "score": 5.0 if passing else 10.0}

    monkeypatch.setattr(research_agent, "evaluate_candidate", fake_evaluate)
    monkeypatch.setattr(research_agent, "_latest_candidates", lambda *args: [])
    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[
            {"style": "SWING_20D", "strategy": "bad"},
            {"style": "SWING_20D", "strategy": "good"},
        ],
        folds=4,
        warmup=200,
    )

    assert result["styles"]["SWING_20D"]["strategy"] == "good"
    assert final_exposures == ["good"]


def test_paper_ledger_waits_for_future_bar_and_uses_stop_first(tmp_path):
    dates = pd.date_range("2026-01-05", periods=2, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100, 101],
        ("High", "TEST"): [101, 106],
        ("Low", "TEST"): [99, 98],
        ("Close", "TEST"): [100, 103],
    }, index=dates)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    result = {
        "created_at": "2026-01-05T22:00:00Z",
        "entries": [{
            "symbol": "TEST",
            "side": "LONG",
            "style": "SWING_20D",
            "strategy": "trend_momentum",
            "signal_date": "2026-01-05",
            "entry": 100,
            "stop": 99,
            "target": 105,
            "max_hold": 20,
            "status": "PENDING_NEWS_AND_LIVE_GATES",
        }],
    }
    path = tmp_path / "paper.json"

    assert update_paper_ledger(result, data.iloc[:1], path=path)["closed_trades"] == 0
    summary = update_paper_ledger(result, data, path=path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert summary["closed_trades"] == 1
    assert ledger["closed"][0]["entry"] == 101
    assert ledger["closed"][0]["exit_reason"] == "stop"
    assert ledger["closed"][0]["return"] < 0
