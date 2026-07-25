import numpy as np
import pandas as pd

import json

import market_dashboard.modules.research_agent as research_agent
import run_research_agent as research_runner
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
    assert result["styles"]["SWING_5D"]["metrics"]["execution_plan"]["final"]["trades"] >= 2
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
    monkeypatch.setattr(research_agent, "evaluate_execution_plan", lambda *args, **kwargs: {
        "development": {
            "trades": 100,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "positive_fold_ratio": 1.0,
            "positive_symbol_ratio": 1.0,
        },
        "final": {
            "trades": 30,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "positive_symbol_ratio": 1.0,
        },
        "folds": [],
        "by_symbol": {},
    })
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


def test_research_loop_skips_candidate_with_untradeable_development_bracket(monkeypatch):
    index = pd.date_range("2024-01-01", periods=360, freq="B")
    data = pd.DataFrame({("Close", "TEST"): np.arange(360) + 100}, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    final_exposures = []

    def fake_evaluate(frame, universe, candidate, **kwargs):
        if len(frame) == len(data):
            final_exposures.append(candidate["strategy"])
        metric = {
            "trades": 100,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "max_drawdown": -0.1,
            "total_return": 0.2,
        }
        return {
            **candidate,
            "development": {**metric, "positive_fold_ratio": 1.0},
            "final": metric,
            "folds": [metric],
            "score": 10.0 if candidate["strategy"] == "untradeable" else 5.0,
        }

    def fake_execution(frame, universe, candidate, **kwargs):
        passing = candidate["strategy"] == "tradeable"
        metric = {
            "trades": 100,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5 if passing else 1.0,
            "positive_fold_ratio": 1.0,
            "positive_symbol_ratio": 1.0,
        }
        return {"development": metric, "final": metric, "folds": [], "by_symbol": {}}

    monkeypatch.setattr(research_agent, "evaluate_candidate", fake_evaluate)
    monkeypatch.setattr(research_agent, "evaluate_execution_plan", fake_execution)
    monkeypatch.setattr(research_agent, "_latest_candidates", lambda *args: [])
    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[
            {"style": "SWING_20D", "strategy": "untradeable"},
            {"style": "SWING_20D", "strategy": "tradeable"},
        ],
        folds=4,
        warmup=200,
    )

    assert result["styles"]["SWING_20D"]["strategy"] == "tradeable"
    assert final_exposures == ["tradeable"]


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
    assert ledger["closed"][0]["entry"] == 100
    assert ledger["closed"][0]["exit_reason"] == "stop"
    assert ledger["closed"][0]["return"] < 0


def test_paper_ledger_does_not_assume_fill_bar_target_sequence(tmp_path):
    dates = pd.date_range("2026-01-05", periods=2, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100, 101],
        ("High", "TEST"): [101, 106],
        ("Low", "TEST"): [99, 99.5],
        ("Close", "TEST"): [100, 103],
    }, index=dates)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    entry = {
        "symbol": "TEST",
        "side": "LONG",
        "style": "SWING_20D",
        "strategy": "trend_momentum",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 95,
        "target": 105,
        "max_hold": 20,
        "status": "PAPER_CANDIDATE",
    }
    path = tmp_path / "paper.json"

    update_paper_ledger({"created_at": "2026-01-05T22:00:00Z", "entries": [entry]}, data.iloc[:1], path=path)
    summary = update_paper_ledger({"created_at": "2026-01-06T22:00:00Z", "entries": [entry]}, data, path=path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert summary["closed_trades"] == 0
    assert ledger["positions"][0]["entry_date"] == "2026-01-06"


def test_paper_ledger_records_opening_gap_below_stop(tmp_path):
    dates = pd.date_range("2026-01-05", periods=2, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100, 90],
        ("High", "TEST"): [101, 92],
        ("Low", "TEST"): [99, 89],
        ("Close", "TEST"): [100, 91],
    }, index=dates)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    entry = {
        "symbol": "TEST",
        "side": "LONG",
        "style": "SWING_20D",
        "strategy": "trend_momentum",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 95,
        "target": 110,
        "max_hold": 20,
        "status": "PAPER_CANDIDATE",
    }
    path = tmp_path / "paper.json"

    update_paper_ledger({"created_at": "2026-01-05T22:00:00Z", "entries": [entry]}, data.iloc[:1], path=path)
    summary = update_paper_ledger({"created_at": "2026-01-06T22:00:00Z", "entries": [entry]}, data, path=path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert summary["closed_trades"] == 1
    assert ledger["closed"][0]["exit_reason"] == "gap_stop"
    assert ledger["closed"][0]["return"] == -0.002


def test_paper_ledger_does_not_overlap_persistent_signal(tmp_path):
    dates = pd.date_range("2026-01-05", periods=2, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100, 102],
        ("High", "TEST"): [101, 103],
        ("Low", "TEST"): [99, 101],
        ("Close", "TEST"): [100, 102],
    }, index=dates)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    entry = {
        "symbol": "TEST",
        "side": "LONG",
        "style": "SWING_20D",
        "strategy": "trend_momentum",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 90,
        "target": 120,
        "max_hold": 20,
        "status": "PAPER_CANDIDATE",
    }
    path = tmp_path / "paper.json"
    update_paper_ledger({"created_at": "2026-01-05T22:00:00Z", "entries": [entry]}, data.iloc[:1], path=path)
    update_paper_ledger(
        {"created_at": "2026-01-06T22:00:00Z", "entries": [{**entry, "signal_date": "2026-01-06"}]},
        data,
        path=path,
    )

    positions = json.loads(path.read_text(encoding="utf-8"))["positions"]
    assert len(positions) == 1
    assert positions[0]["signal_date"] == "2026-01-05"


def test_paper_ledger_cancels_withdrawn_unfilled_signal(tmp_path):
    date = pd.date_range("2026-01-05", periods=1, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100],
        ("High", "TEST"): [101],
        ("Low", "TEST"): [99],
        ("Close", "TEST"): [100],
    }, index=date)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    entry = {
        "symbol": "TEST",
        "side": "LONG",
        "style": "SWING_20D",
        "strategy": "trend_momentum",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 90,
        "target": 120,
        "max_hold": 20,
        "status": "PAPER_CANDIDATE",
    }
    path = tmp_path / "paper.json"
    update_paper_ledger({"created_at": "2026-01-05T22:00:00Z", "entries": [entry]}, data, path=path)
    update_paper_ledger({"created_at": "2026-01-06T22:00:00Z", "entries": []}, data, path=path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert ledger["positions"] == []
    assert ledger["cancelled"][0]["reason"] == "research or news gate withdrew pending entry"


def test_news_snapshot_marks_reduced_candidate(monkeypatch, tmp_path):
    path = tmp_path / "news.json"
    path.write_text(json.dumps({"research_version": "test-news-v1", "ai_status": "openai_unavailable", "symbols": {"TEST": {
        "action": "reduce",
        "news_status": "ok",
        "news": [{"title": "Negative headline"}],
        "reasons": ["negative headline risk"],
    }}}), encoding="utf-8")
    monkeypatch.setattr(research_runner, "NEWS_SNAPSHOT_PATH", path)
    result = {"entries": [{"symbol": "TEST"}]}

    research_runner.apply_news_snapshot(result)

    assert result["entries"][0]["status"] == "PAPER_CANDIDATE_REDUCED"
    assert result["entries"][0]["news_action"] == "reduce"
    assert result["entries"][0]["news_version"] == "test-news-v1:openai_unavailable"


def test_watch_lock_allows_only_one_writer(tmp_path):
    path = tmp_path / "watch.lock"
    first = research_runner.acquire_watch_lock(path)
    try:
        assert first is not None
        assert research_runner.acquire_watch_lock(path) is None
    finally:
        first.close()
    third = research_runner.acquire_watch_lock(path)
    assert third is not None
    third.close()


def test_old_plan_trades_cannot_validate_current_plan(tmp_path):
    path = tmp_path / "paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [
            {
                "symbol": "TEST",
                "style": "SWING_20D",
                "strategy": "old_strategy",
                "plan_id": "old-plan",
                "signal_date": "2025-01-01",
                "return": 0.01,
            }
            for _ in range(30)
        ],
    }), encoding="utf-8")
    result = {
        "created_at": "2026-01-05T22:00:00Z",
        "entries": [],
        "styles": {
            "SWING_20D": {
                **research_agent.STYLE_CONFIG["SWING_20D"],
                "strategy": "trend_momentum",
                "acceptance": {"status": "pass"},
            },
        },
    }

    summary = update_paper_ledger(result, pd.DataFrame(), path=path)

    assert summary["by_plan"]["old-plan"]["status"] == "validated"
    assert summary["status"] == "warming_up"
    assert summary["current_closed_trades"] == 0
