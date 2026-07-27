import numpy as np
import pandas as pd
import pytest

import json

import market_dashboard.modules.research_agent as research_agent
import run_research_agent as research_runner
from market_dashboard.modules.research_agent import append_research_history, publish_research_result, recent_rejected_holdout_trials, run_research_loop, update_paper_ledger


def test_research_data_gate_requires_current_complete_real_ohlc():
    index = pd.date_range("2024-01-02", "2025-01-31", freq="B")
    close = pd.Series(np.linspace(100, 120, len(index)), index=index)
    columns = {}
    for symbol in ("TEST", "SPY"):
        columns.update({
            ("Open", symbol): close,
            ("High", symbol): close + 1,
            ("Low", symbol): close - 1,
            ("Close", symbol): close,
            ("Volume", symbol): 1_000_000,
        })
    data = pd.DataFrame(columns, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    status = {
        "source": "Yahoo Finance",
        "is_demo": False,
        "loaded_tickers": ["TEST", "SPY"],
    }

    research_runner.validate_research_data(
        data, status, ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4
    )

    with pytest.raises(RuntimeError, match="missing required symbols"):
        research_runner.validate_research_data(
            data, {**status, "loaded_tickers": ["TEST"]},
            ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4,
        )
    with pytest.raises(RuntimeError, match="recognized real-data provider"):
        research_runner.validate_research_data(
            data, {**status, "is_demo": True},
            ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4,
        )
    with pytest.raises(RuntimeError, match="latest bar is stale"):
        research_runner.validate_research_data(
            data, status, ["TEST", "SPY"], "2024-01-01", "2025-03-01", 200, 4
        )
    bad = data.copy()
    bad.loc[index[-1], ("High", "TEST")] = 1
    with pytest.raises(RuntimeError, match="invalid OHLC"):
        research_runner.validate_research_data(
            bad, status, ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4
        )


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
    assert result["development_diagnostics"][0]["signal_reason"] == "development and internal validation passed"
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


def test_research_loop_selects_best_executable_plan_not_best_signal_score(monkeypatch):
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
            "score": 10.0 if candidate["strategy"] == "signal_best" else 5.0,
        }

    def fake_execution(frame, universe, candidate, **kwargs):
        expectancy = 0.002 if candidate["strategy"] == "signal_best" else 0.01
        metric = {
            "trades": 100,
            "win_rate": 0.6,
            "expectancy": expectancy,
            "profit_factor": 1.3,
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
            {"style": "SWING_20D", "strategy": "signal_best"},
            {"style": "SWING_20D", "strategy": "plan_best"},
        ],
        folds=4,
        warmup=200,
    )

    assert result["styles"]["SWING_20D"]["strategy"] == "plan_best"
    assert final_exposures == ["plan_best"]
    assert next(row for row in result["development_diagnostics"] if row["strategy"] == "plan_best")["selected"]

    final_exposures.clear()
    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[
            {"style": "SWING_20D", "strategy": "signal_best"},
            {"style": "SWING_20D", "strategy": "plan_best"},
        ],
        folds=4,
        warmup=200,
        excluded_holdout_trials={("SWING_20D", "plan_best")},
    )

    assert result["styles"]["SWING_20D"]["strategy"] == "signal_best"
    assert final_exposures == ["signal_best"]


def test_development_reject_does_not_masquerade_as_final_holdout(monkeypatch):
    index = pd.date_range("2024-01-01", periods=360, freq="B")
    data = pd.DataFrame({("Close", "TEST"): np.arange(360) + 100}, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    metric = {
        "trades": 100,
        "win_rate": 0.4,
        "expectancy": -0.01,
        "profit_factor": 0.8,
        "max_drawdown": -0.1,
        "total_return": -0.2,
    }
    monkeypatch.setattr(research_agent, "evaluate_candidate", lambda frame, universe, candidate, **kwargs: {
        **candidate,
        "development": {**metric, "positive_fold_ratio": 0.0},
        "final": metric,
        "folds": [metric],
        "score": 1.0,
    })
    monkeypatch.setattr(research_agent, "_latest_candidates", lambda *args: [])

    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[{"style": "SWING_5D", "strategy": "reject_me"}],
        folds=4,
        warmup=200,
    )
    metrics = result["styles"]["SWING_5D"]["metrics"]

    assert metrics["holdout_exposed"] is False
    assert metrics["final_holdout"] == {}
    assert metrics["development_validation"]["expectancy"] == -0.01


def test_holdout_reject_is_shadow_only(monkeypatch):
    index = pd.date_range("2024-01-01", periods=360, freq="B")
    data = pd.DataFrame({("Close", "TEST"): np.arange(360) + 100}, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)

    def fake_evaluate(frame, universe, candidate, **kwargs):
        passing = len(frame) < len(data)
        development = {
            "trades": 100,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "max_drawdown": -0.1,
            "total_return": 0.2,
            "positive_fold_ratio": 1.0,
        }
        final = {
            **development,
            "expectancy": 0.01 if passing else -0.01,
            "profit_factor": 1.5 if passing else 0.8,
        }
        return {**candidate, "development": development, "final": final, "folds": [final], "score": 10.0}

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
    monkeypatch.setattr(research_agent, "_latest_candidates", lambda frame, universe, selected: [
        {
            "symbol": "TEST",
            "style": style,
            "strategy": row["strategy"],
            "signal_date": "2026-01-05",
            "entry": 100,
            "stop": 95,
            "target": 110,
        }
        for style, row in selected.items()
    ])

    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[{"style": "SWING_20D", "strategy": "candidate"}],
        folds=4,
        warmup=200,
    )

    assert result["entries"] == []
    assert result["shadow_entries"][0]["status"] == "SHADOW_PAPER_ONLY"
    assert result["styles"]["SWING_20D"]["acceptance"]["status"] == "reject"


def test_research_history_is_deduplicated_and_bounded(tmp_path):
    path = tmp_path / "history.jsonl"
    result = {
        "created_at": "2026-07-25T00:00:00Z",
        "research_notes": {"what_worked": [], "what_failed": ["none passed"]},
        "paper_evidence": {"status": "warming_up"},
        "entries": [],
        "styles": {"SWING_20D": {"strategy": "trend_momentum", "acceptance": {"status": "reject", "reason": "holdout failed"}, "metrics": {"holdout_exposed": True}}},
    }

    append_research_history(result, path=path, max_records=2)
    append_research_history(result, path=path, max_records=2)
    append_research_history({**result, "created_at": "2026-07-26T00:00:00Z"}, path=path, max_records=2)
    append_research_history({**result, "created_at": "2026-07-27T00:00:00Z"}, path=path, max_records=2)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert [row["created_at"] for row in records] == ["2026-07-26T00:00:00Z", "2026-07-27T00:00:00Z"]
    assert records[-1]["styles"]["SWING_20D"]["holdout_exposed"] is True
    assert records[-1]["styles"]["SWING_20D"]["family"] == "trend"


def test_recent_rejected_holdout_trials_ignores_passes_and_expired_trials(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text("\n".join([
        json.dumps({
            "created_at": "2026-07-20T00:00:00Z",
            "styles": {
                "SWING_20D": {
                    "strategy": "recent_reject",
                    "status": "reject",
                    "holdout_exposed": True,
                },
                "SWING_5D": {
                    "strategy": "active_pass",
                    "status": "pass",
                    "holdout_exposed": True,
                },
            },
        }),
        json.dumps({
            "created_at": "2026-01-01T00:00:00Z",
            "styles": {
                "OVERNIGHT_1D": {
                    "strategy": "old_reject",
                    "status": "reject",
                    "holdout_exposed": True,
                },
            },
        }),
    ]) + "\n", encoding="utf-8")

    trials = recent_rejected_holdout_trials(
        path=path,
        now=pd.Timestamp("2026-07-25", tz="UTC").to_pydatetime(),
    )

    assert trials == {("SWING_20D", "recent_reject")}


def test_recent_rejected_holdout_trials_blocks_the_strategy_family(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(json.dumps({
        "created_at": "2026-07-20T00:00:00Z",
        "styles": {
            "SWING_20D": {
                "strategy": "trend_momentum",
                "status": "reject",
                "holdout_exposed": True,
            },
        },
    }) + "\n", encoding="utf-8")

    trials = recent_rejected_holdout_trials(
        path=path,
        now=pd.Timestamp("2026-07-25", tz="UTC").to_pydatetime(),
    )

    assert ("SWING_20D", "trend_momentum") in trials
    assert ("SWING_20D", "benchmark_confirmed_trend") in trials
    assert ("SWING_20D", "rsi_mean_reversion") not in trials


def test_every_production_strategy_declares_a_family():
    assert set(research_agent.STRATEGIES) == set(research_agent.STRATEGY_FAMILIES)


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

    shadow_path = tmp_path / "shadow.json"
    update_paper_ledger({"created_at": "2026-01-05T22:00:00Z", "entries": [entry]}, data, path=shadow_path)
    update_paper_ledger(
        {"created_at": "2026-01-06T22:00:00Z", "entries": []},
        data,
        path=shadow_path,
        cancel_withdrawn=False,
    )
    assert len(json.loads(shadow_path.read_text(encoding="utf-8"))["positions"]) == 1


def test_news_snapshot_marks_reduced_candidate(monkeypatch, tmp_path):
    path = tmp_path / "news.json"
    entry = {
        "symbol": "TEST",
        "style": "SWING_20D",
        "strategy": "low_vol_trend",
        "signal_date": "2026-07-27",
        "entry": 100,
        "stop": 95,
        "target": 110,
    }
    path.write_text(json.dumps({"created_at": "2026-07-27T10:00:00Z", "research_version": "test-news-v1", "ai_status": "openai_unavailable", "symbols": {"TEST": {
        "action": "reduce",
        "news_status": "ok",
        "news": [{"title": "Negative headline"}],
        "reasons": ["negative headline risk"],
        "candidate": entry,
    }}}), encoding="utf-8")
    monkeypatch.setattr(research_runner, "NEWS_SNAPSHOT_PATH", path)
    result = {"entries": [entry.copy()]}

    research_runner.apply_news_snapshot(result, now=pd.Timestamp("2026-07-27T10:05:00Z").to_pydatetime())

    assert result["entries"][0]["status"] == "PAPER_CANDIDATE_REDUCED"
    assert result["entries"][0]["news_action"] == "reduce"
    assert result["entries"][0]["news_version"] == "test-news-v1:openai_unavailable"
    assert result["entries"][0]["news_created_at"] == "2026-07-27T10:00:00Z"


def test_news_snapshot_cannot_approve_a_stale_or_different_plan(monkeypatch, tmp_path):
    path = tmp_path / "news.json"
    candidate = {
        "symbol": "TEST",
        "style": "SWING_20D",
        "strategy": "low_vol_trend",
        "signal_date": "2026-07-27",
        "entry": 100,
        "stop": 95,
        "target": 110,
    }
    snapshot = {
        "created_at": "2026-07-27T09:00:00Z",
        "symbols": {"TEST": {"action": "pass", "candidate": candidate}},
    }
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(research_runner, "NEWS_SNAPSHOT_PATH", path)
    now = pd.Timestamp("2026-07-27T10:00:00Z").to_pydatetime()

    stale = {"entries": [candidate.copy()]}
    research_runner.apply_news_snapshot(stale, now=now)
    snapshot["created_at"] = "2026-07-27T10:00:00Z"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    mismatched = {"entries": [{**candidate, "target": 111}]}
    research_runner.apply_news_snapshot(mismatched, now=now)
    unavailable = {"entries": [candidate.copy()]}
    research_runner.apply_news_snapshot(unavailable, now=now)

    assert stale["entries"][0]["news_action"] == "news_unavailable"
    assert mismatched["entries"][0]["news_action"] == "news_unavailable"
    assert unavailable["entries"][0]["news_action"] == "news_unavailable"


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
                "symbol": f"TEST{index % 5}",
                "style": "SWING_20D",
                "strategy": "old_strategy",
                "plan_id": "old-plan",
                "signal_date": "2025-01-01",
                "exit_date": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=index * 4)).date()),
                "return": 0.01,
            }
            for index in range(30)
        ] + [
            {
                "symbol": "ORDER",
                "style": "SWING_20D",
                "signal_date": "2025-01-01",
                "plan_id": "out-of-order",
                "exit_date": exit_date,
                "return": trade_return,
            }
            for exit_date, trade_return in (
                ("2025-01-03", -0.2),
                ("2025-01-01", -0.2),
                ("2025-01-02", 0.3),
            )
        ] + [
            {
                "symbol": "LOSS",
                "style": "SWING_20D",
                "signal_date": "2025-01-01",
                "plan_id": "initial-loss",
                "exit_date": "2025-01-02",
                "return": -0.2,
            }
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
    assert np.isclose(summary["by_plan"]["out-of-order"]["max_drawdown"], -0.2)
    assert np.isclose(summary["by_plan"]["initial-loss"]["max_drawdown"], -0.2)


def test_paper_gate_rejects_symbol_or_time_concentration(tmp_path):
    path = tmp_path / "paper.json"
    start = pd.Timestamp("2025-01-01")
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [
            {
                "symbol": "ONLY",
                "style": "SWING_20D",
                "signal_date": "2025-01-01",
                "plan_id": "one-symbol",
                "exit_date": str((start + pd.Timedelta(days=index * 4)).date()),
                "return": 0.01,
            }
            for index in range(30)
        ] + [
            {
                "symbol": f"TEST{index % 5}",
                "style": "SWING_20D",
                "signal_date": "2025-01-01",
                "plan_id": "short-burst",
                "exit_date": str((start + pd.Timedelta(days=index)).date()),
                "return": 0.01,
            }
            for index in range(30)
        ],
    }), encoding="utf-8")

    summary = update_paper_ledger(
        {"created_at": "2026-01-05T22:00:00Z", "entries": []},
        pd.DataFrame(),
        path=path,
    )

    assert summary["by_plan"]["one-symbol"]["status"] == "warming_up"
    assert summary["by_plan"]["short-burst"]["status"] == "warming_up"
    assert summary["by_plan"]["one-symbol"]["symbols"] == 1
    assert summary["by_plan"]["short-burst"]["evidence_span_days"] == 29


def test_legacy_position_cannot_be_credited_to_current_plan(tmp_path):
    path = tmp_path / "paper.json"
    entry = {
        "symbol": "TEST",
        "style": "SWING_20D",
        "strategy": "low_vol_trend",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 95,
        "target": 110,
        "max_hold": 20,
    }
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [{**entry, "entry": None, "limit_entry": 100, "entry_date": None}],
        "closed": [],
        "cancelled": [],
    }), encoding="utf-8")

    update_paper_ledger(
        {"created_at": "2026-01-05T22:00:00Z", "entries": [entry]},
        pd.DataFrame(),
        path=path,
    )
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert len(ledger["positions"]) == 1
    assert ledger["positions"][0].get("plan_id")
    assert ledger["cancelled"][0].get("plan_id") is None
    assert ledger["cancelled"][0]["reason"] == "research or news gate withdrew pending entry"


def test_paper_plan_identity_changes_with_execution_engine(monkeypatch):
    row = {
        "style": "SWING_20D",
        "strategy": "low_vol_trend",
        "max_hold": 20,
    }
    original = research_agent._paper_plan_id(row, 10)

    def changed_bracket_exit(bar, entry, stop, target, *, fill_bar=False):
        return None, ""

    monkeypatch.setattr(research_agent, "_bracket_exit", changed_bracket_exit)

    assert research_agent._paper_plan_id(row, 10) != original
