import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace

import json

import market_dashboard.modules.research_agent as research_agent
import run_research_agent as research_runner
from market_dashboard.modules.research_agent import append_research_history, publish_research_result, recent_rejected_holdout_trials, run_research_loop, update_paper_ledger


def test_runner_records_holdout_result_when_postprocessing_fails(monkeypatch):
    result = {
        "created_at": "2026-07-29T00:00:00Z",
        "entries": [],
        "shadow_entries": [],
    }
    recorded = []
    runner_kwargs = {}
    monkeypatch.setattr(research_runner, "load_market_data", lambda *args, **kwargs: (
        pd.DataFrame({"Close": [100]}),
        {"source": "Yahoo Finance", "is_demo": False},
    ))
    monkeypatch.setattr(research_runner, "validate_research_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(research_runner, "research_data_provenance", lambda *args, **kwargs: {"dataset_sha256": "test"})
    monkeypatch.setattr(research_runner, "recent_rejected_holdout_trials", lambda: set())
    def fake_research_loop(*args, **kwargs):
        runner_kwargs.update(kwargs)
        return result
    monkeypatch.setattr(research_runner, "run_research_loop", fake_research_loop)
    monkeypatch.setattr(research_runner, "publish_research_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(research_runner, "refresh_news", lambda: "")
    monkeypatch.setattr(research_runner, "apply_news_snapshot", lambda *args, **kwargs: None)
    def fail_ledger(*args, **kwargs):
        raise RuntimeError("ledger failed")
    monkeypatch.setattr(research_runner, "update_paper_ledger", fail_ledger)
    monkeypatch.setattr(research_runner, "append_research_history", recorded.append)

    with pytest.raises(RuntimeError, match="ledger failed"):
        research_runner.run_once(SimpleNamespace(
            symbols="TEST",
            years=1,
            folds=4,
            warmup=20,
            cost_bps=10,
        ))

    assert recorded == [result]
    assert ("SWING_20D", "low_vol_trend") in runner_kwargs["excluded_holdout_trials"]


def test_preflight_only_validates_data_without_evaluating_or_writing(monkeypatch):
    monkeypatch.setattr(research_runner, "load_market_data", lambda *args, **kwargs: (
        pd.DataFrame({"Close": [100]}),
        {"source": "Yahoo Finance", "is_demo": False},
    ))
    monkeypatch.setattr(research_runner, "validate_research_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(research_runner, "research_data_provenance", lambda *args, **kwargs: {
        "dataset_sha256": "validated-snapshot",
    })
    monkeypatch.setattr(research_runner, "run_research_loop", lambda *args, **kwargs: pytest.fail("preflight evaluated a strategy"))
    monkeypatch.setattr(research_runner, "publish_research_result", lambda *args, **kwargs: pytest.fail("preflight wrote a result"))

    result = research_runner.run_once(SimpleNamespace(
        symbols="TEST",
        years=1,
        folds=4,
        warmup=20,
        cost_bps=10,
        preflight_only=True,
    ))

    assert result == {
        "status": "preflight_only",
        "data_provenance": {"dataset_sha256": "validated-snapshot"},
    }


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
    with pytest.raises(RuntimeError, match="incomplete current session"):
        research_runner.validate_research_data(
            data, status, ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4,
            now=pd.Timestamp("2025-01-31T20:00:00Z").to_pydatetime(),
        )
    research_runner.validate_research_data(
        data, status, ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4,
        now=pd.Timestamp("2025-01-31T22:00:00Z").to_pydatetime(),
    )
    rounding_noise = data.copy()
    rounding_noise.loc[index[-1], ("Low", "TEST")] = (
        rounding_noise.loc[index[-1], ("Close", "TEST")] + 1e-14
    )
    research_runner.validate_research_data(
        rounding_noise, status, ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4
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
    nonfinite = data.copy()
    nonfinite.loc[index[-1], ("High", "TEST")] = np.inf
    with pytest.raises(RuntimeError, match="invalid OHLC"):
        research_runner.validate_research_data(
            nonfinite, status, ["TEST", "SPY"], "2024-01-01", "2025-02-01", 200, 4
        )


def test_research_end_date_excludes_an_open_new_york_session():
    before_close = pd.Timestamp("2026-07-29T19:00:00Z").to_pydatetime()
    after_close = pd.Timestamp("2026-07-29T21:00:00Z").to_pydatetime()

    assert str(research_runner.research_end_date(before_close)) == "2026-07-29"
    assert str(research_runner.research_end_date(after_close)) == "2026-07-30"


def test_research_data_provenance_fingerprints_exact_ohlc_values():
    index = pd.date_range("2026-01-05", periods=2, freq="B")
    data = pd.DataFrame({
        (field, symbol): [100, 101]
        for symbol in ("TEST", "SPY")
        for field in ("Open", "High", "Low", "Close")
    }, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    status = {"source": "Yahoo Finance", "loaded_tickers": ["TEST", "SPY"], "is_demo": False}

    first = research_runner.research_data_provenance(data, status, ["TEST", "SPY"])
    second = research_runner.research_data_provenance(data, status, ["TEST", "SPY"])
    changed = data.copy()
    changed.loc[index[-1], ("Close", "TEST")] = 102

    assert first["dataset_sha256"] == second["dataset_sha256"]
    assert first["dataset_sha256"] != research_runner.research_data_provenance(
        changed, status, ["TEST", "SPY"]
    )["dataset_sha256"]
    assert first["coverage"]["TEST"] == {
        "first": "2026-01-05",
        "last": "2026-01-06",
        "rows": 2,
    }


def test_research_metrics_include_starting_capital_and_reject_nonfinite_returns():
    metrics = research_agent._metrics(pd.Series([-0.2]), [-0.2])

    assert np.isclose(metrics["max_drawdown"], -0.2)
    assert np.isclose(metrics["total_return"], -0.2)
    with pytest.raises(ValueError, match="non-finite return"):
        research_agent._metrics(pd.Series([np.nan]), [0.01])
    with pytest.raises(ValueError, match="non-finite return"):
        research_agent._metrics(pd.Series([0.01]), [np.inf])


def test_realized_drawdown_respects_fixed_portfolio_slots():
    returns = research_agent._realized_portfolio_returns([
        ("2026-01-05", 0.10),
        ("2026-01-05", -0.05),
        ("2026-01-06", -0.10),
    ], 20)

    assert np.isclose(returns.iloc[0], 0.0025)
    assert np.isclose(returns.iloc[1], -0.005)
    assert np.isclose(research_agent._metrics(returns, [0.10, -0.05, -0.10])["max_drawdown"], -0.005)


def test_execution_plan_acceptance_enforces_drawdown():
    metric = {
        "trades": 30,
        "expectancy": 0.01,
        "profit_factor": 1.5,
        "positive_fold_ratio": 1.0,
        "positive_symbol_ratio": 1.0,
        "max_drawdown": -0.20,
    }

    accepted, reason = research_agent._accept_execution_plan(
        {"development": metric, "final": metric},
        research_agent.DEFAULT_GATES,
    )

    assert accepted is False
    assert "drawdown" in reason


def test_production_strategy_signals_are_prefix_invariant():
    index = pd.date_range("2024-01-01", periods=400, freq="B")
    price = pd.Series(
        100 + np.linspace(0, 60, len(index)) + np.sin(np.arange(len(index)) / 5),
        index=index,
    )
    breadth = pd.Series(np.linspace(0.4, 0.8, len(index)), index=index)
    benchmark = price * 1.01
    cutoff = 350

    for name, factory in research_agent.STRATEGIES.items():
        strategy = factory(holding_period=20, position_type="fixed", fee_pct=0)
        full = strategy.generate_signals(
            price,
            research_agent._indicators(price, breadth, benchmark),
        )
        prefix = strategy.generate_signals(
            price.iloc[:cutoff],
            research_agent._indicators(
                price.iloc[:cutoff],
                breadth.iloc[:cutoff],
                benchmark.iloc[:cutoff],
            ),
        )
        pd.testing.assert_series_equal(
            full.iloc[:cutoff],
            prefix,
            check_names=False,
            obj=name,
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
    expected_holdout_start = research_agent._folds(len(index), 4, 200)[-1][0]
    assert result["holdout"]["start"] == str(index[expected_holdout_start].date())
    assert result["holdout"]["end"] == str(index[-1].date())
    assert len(result["holdout"]["id"]) == 16
    assert result["research_protocol"]["engine_version"] == research_agent.EXECUTION_PLAN_VERSION

    model_path = tmp_path / "bot_model_pack.json"
    agent_path = tmp_path / "research_agent.json"
    pack = publish_research_result(result, model_pack_path=model_path, agent_result_path=agent_path)
    assert pack["styles"]["SWING_5D"]["strategy"] == "ma_crossover"
    assert json.loads(agent_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_execution_folds_do_not_count_only_fast_losses_near_boundary(monkeypatch):
    index = pd.date_range("2024-01-01", periods=80, freq="B")
    close = pd.Series(100.0, index=index)
    lows = pd.Series(99.0, index=index)
    for _, end in research_agent._folds(len(index), 4, 20):
        lows.iloc[end - 4] = 94.0
    data = pd.DataFrame({
        ("Open", "TEST"): close,
        ("High", "TEST"): 101.0,
        ("Low", "TEST"): lows,
        ("Close", "TEST"): close,
        ("Volume", "TEST"): 1_000_000,
    }, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns)

    class LateFoldSignal:
        def __init__(self, **kwargs):
            pass

        def generate_signals(self, price, indicators):
            signals = pd.Series(0.0, index=price.index)
            for _, end in research_agent._folds(len(price), 4, 20):
                signals.iloc[end - 5] = 1.0
            return signals

    monkeypatch.setitem(research_agent.STRATEGIES, "late_fold", LateFoldSignal)

    evaluation = research_agent.evaluate_execution_plan(
        data,
        ["TEST"],
        {"style": "SWING_20D", "strategy": "late_fold"},
        folds=4,
        warmup=20,
        cost_bps_per_side=0,
    )

    assert sum(fold["trades"] for fold in evaluation["folds"]) == 0

    class LateCloseSignal(research_agent.TrendMomentumStrategy):
        def generate_signals(self, price, indicators):
            signals = pd.Series(0.0, index=price.index)
            signals.iloc[-1] = 1.0
            return signals

    monkeypatch.setitem(research_agent.STRATEGIES, "late_close", LateCloseSignal)
    signal_evaluation = research_agent.evaluate_candidate(
        data,
        ["TEST"],
        {"style": "SWING_5D", "strategy": "late_close"},
        folds=4,
        warmup=20,
        cost_bps_per_side=100,
    )

    assert all(fold["total_return"] == 0 for fold in signal_evaluation["folds"])


def test_research_loop_requires_a_separate_final_holdout():
    with np.testing.assert_raises_regex(ValueError, "at least four folds"):
        run_research_loop(pd.DataFrame(), ["TEST"], folds=3)


def test_research_loop_uses_one_shared_complete_ohlc_calendar(monkeypatch):
    index = pd.date_range("2024-01-01", periods=260, freq="B")
    close = pd.Series(np.linspace(100, 130, len(index)), index=index)
    data = pd.DataFrame({
        (field, symbol): close
        for symbol in ("AAA", "BBB")
        for field in ("Open", "High", "Low", "Close")
    })
    missing_date = index[-15]
    data.loc[missing_date, pd.IndexSlice[:, "BBB"]] = np.nan
    seen_dates = {}

    def fake_evaluate(frame, universe, candidate, **kwargs):
        seen_dates.update({
            symbol: tuple(research_agent.get_ticker_frame(frame, symbol)["Close"].dropna().index)
            for symbol in universe
        })
        metric = {
            "trades": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
        }
        return {
            **candidate,
            "development": {**metric, "positive_fold_ratio": 0.0},
            "final": metric,
            "folds": [metric],
            "score": 0.0,
        }

    monkeypatch.setattr(research_agent, "evaluate_candidate", fake_evaluate)
    result = run_research_loop(
        data,
        ["AAA", "BBB"],
        candidates=[{"style": "SWING_20D", "strategy": "low_vol_trend"}],
        folds=4,
        warmup=200,
    )

    common_dates = index[index != missing_date]
    final_start = research_agent._folds(len(common_dates), 4, 200)[-1][0]
    assert seen_dates["AAA"] == seen_dates["BBB"]
    assert missing_date not in seen_dates["AAA"]
    assert result["holdout"]["start"] == str(common_dates[final_start].date())


def test_benchmark_strategy_calendar_excludes_missing_spy_bar(monkeypatch):
    index = pd.date_range("2024-01-01", periods=260, freq="B")
    close = pd.Series(np.linspace(100, 130, len(index)), index=index)
    data = pd.DataFrame({
        (field, symbol): close
        for symbol in ("AAA", "SPY")
        for field in ("Open", "High", "Low", "Close")
    })
    missing_date = index[-60]
    data.loc[missing_date, pd.IndexSlice[:, "SPY"]] = np.nan
    seen_dates = []

    def fake_evaluate(frame, universe, candidate, **kwargs):
        seen_dates.extend(frame.index)
        metric = {
            "trades": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
        }
        return {
            **candidate,
            "development": {**metric, "positive_fold_ratio": 0.0},
            "final": metric,
            "folds": [metric],
            "score": 0.0,
        }

    monkeypatch.setattr(research_agent, "evaluate_candidate", fake_evaluate)
    run_research_loop(
        data,
        ["AAA"],
        candidates=[{"style": "SWING_20D", "strategy": "benchmark_confirmed_trend"}],
        folds=4,
        warmup=200,
    )

    assert missing_date not in seen_dates


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
            "max_drawdown": -0.1,
        },
        "final": {
            "trades": 30,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "positive_symbol_ratio": 1.0,
            "max_drawdown": -0.1,
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
            "max_drawdown": -0.1,
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
            "max_drawdown": -0.1,
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
    assert result["research_protocol"]["excluded_holdout_trials"] == [{"style": "SWING_20D", "strategy": "plan_best"}]

    final_exposures.clear()
    monkeypatch.setattr(research_agent, "_execution_score", lambda evaluation: 1)
    result = run_research_loop(
        data,
        ["TEST"],
        candidates=[
            {"style": "SWING_20D", "strategy": "trend_momentum"},
            {"style": "SWING_20D", "strategy": "low_vol_trend"},
        ],
        folds=4,
        warmup=200,
    )

    assert result["styles"]["SWING_20D"]["strategy"] == "low_vol_trend"
    assert final_exposures == ["low_vol_trend"]


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
            "max_drawdown": -0.1,
        },
        "final": {
            "trades": 30,
            "win_rate": 0.6,
            "expectancy": 0.01,
            "profit_factor": 1.5,
            "positive_symbol_ratio": 1.0,
            "max_drawdown": -0.1,
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
        "data_provenance": {"source": "Yahoo Finance"},
        "holdout": {"id": "trial-window"},
        "research_protocol": {"engine_version": "daily-bars-test"},
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
    assert records[-1]["holdout"]["id"] == "trial-window"
    assert records[-1]["data_provenance"]["source"] == "Yahoo Finance"


def test_research_history_retains_unexpired_cooldown_beyond_monitoring_cap(tmp_path):
    path = tmp_path / "history.jsonl"
    rejection = {
        "created_at": "2026-07-01T00:00:00Z",
        "styles": {
            "SWING_20D": {
                "strategy": "low_vol_trend",
                "acceptance": {"status": "reject", "reason": "holdout failed"},
                "metrics": {"holdout_exposed": True},
            },
        },
    }
    monitoring = {
        "styles": {
            "SWING_20D": {
                "strategy": "low_vol_trend",
                "acceptance": {"status": "reject", "reason": "cooldown"},
                "metrics": {"holdout_exposed": False},
            },
        },
    }

    append_research_history(rejection, path=path, max_records=2)
    append_research_history({**monitoring, "created_at": "2026-07-02T00:00:00Z"}, path=path, max_records=2)
    append_research_history({**monitoring, "created_at": "2026-07-03T00:00:00Z"}, path=path, max_records=2)

    assert ("SWING_20D", "low_vol_trend") in recent_rejected_holdout_trials(
        path=path,
        now=pd.Timestamp("2026-07-03", tz="UTC").to_pydatetime(),
    )


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

    assert trials == {
        (style, "recent_reject")
        for style in research_agent.STYLE_CONFIG
    }


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
    assert ("SWING_5D", "low_vol_trend") in trials
    assert ("OVERNIGHT_1D", "macd_trend") in trials
    assert ("SWING_20D", "rsi_mean_reversion") not in trials


def test_every_production_strategy_declares_a_family():
    assert set(research_agent.STRATEGIES) == set(research_agent.STRATEGY_FAMILIES)


def test_default_research_lane_is_frozen_low_volatility_trend():
    assert research_agent.DEFAULT_CANDIDATES == [
        {"style": "SWING_20D", "strategy": "low_vol_trend"}
    ]
    assert len(research_agent.WATCHLIST_CANDIDATES) > len(research_agent.DEFAULT_CANDIDATES)


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
            "news_action": "pass",
        }],
    }
    path = tmp_path / "paper.json"

    assert update_paper_ledger(result, data.iloc[:1], path=path)["closed_trades"] == 0
    summary = update_paper_ledger({**result, "created_at": "2026-01-06T22:00:00Z"}, data, path=path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert summary["closed_trades"] == 1
    assert ledger["closed"][0]["entry"] == 100
    assert ledger["closed"][0]["exit_reason"] == "stop"
    assert ledger["closed"][0]["return"] < 0


def test_paper_position_keeps_its_original_cost_assumption(tmp_path):
    dates = pd.date_range("2026-01-05", periods=2, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100, 100],
        ("High", "TEST"): [101, 106],
        ("Low", "TEST"): [99, 98],
        ("Close", "TEST"): [100, 103],
    }, index=dates)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    entry = {
        "symbol": "TEST",
        "side": "LONG",
        "style": "SWING_20D",
        "strategy": "low_vol_trend",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 99,
        "target": 105,
        "max_hold": 20,
        "news_action": "pass",
    }
    path = tmp_path / "paper.json"

    update_paper_ledger(
        {"created_at": "2026-01-05T22:00:00Z", "entries": [entry]},
        data.iloc[:1],
        path=path,
        cost_bps_per_side=10,
        cancel_withdrawn=False,
    )
    update_paper_ledger(
        {"created_at": "2026-01-06T22:00:00Z", "entries": [entry]},
        data,
        path=path,
        cost_bps_per_side=100,
        cancel_withdrawn=False,
    )
    closed = json.loads(path.read_text(encoding="utf-8"))["closed"][0]

    assert closed["cost_bps_per_side"] == 10
    assert closed["return"] == closed["exit"] / closed["entry"] - 1 - 0.002


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
        "news_action": "pass",
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
        "news_action": "pass",
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
        "news_action": "pass",
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
        "news_action": "pass",
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


def test_actionable_paper_evidence_requires_news_pass(tmp_path):
    date = pd.date_range("2026-01-05", periods=1, freq="B")
    data = pd.DataFrame({
        ("Open", "TEST"): [100],
        ("High", "TEST"): [101],
        ("Low", "TEST"): [99],
        ("Close", "TEST"): [100],
    }, index=date)
    entry = {
        "symbol": "TEST",
        "side": "LONG",
        "style": "SWING_20D",
        "strategy": "low_vol_trend",
        "signal_date": "2026-01-05",
        "entry": 100,
        "stop": 95,
        "target": 110,
        "max_hold": 20,
        "news_version": "news-v1",
        "news_action": "pass",
    }
    path = tmp_path / "paper.json"

    update_paper_ledger({"created_at": "2026-01-05T22:00:00Z", "entries": [entry]}, data, path=path)
    update_paper_ledger({
        "created_at": "2026-01-06T22:00:00Z",
        "entries": [{**entry, "news_action": "reduce"}],
    }, data, path=path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    assert ledger["positions"] == []
    assert ledger["cancelled"][0]["reason"] == "research or news gate withdrew pending entry"
    assert research_agent._paper_plan_id(entry, 10) != research_agent._paper_plan_id(
        {**entry, "news_action": "reduce"},
        10,
    )


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
                "signal_date": str((pd.Timestamp("2024-12-31") + pd.Timedelta(days=index * 4)).date()),
                "entry_date": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=index * 4)).date()),
                "exit_date": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=index * 4)).date()),
                "entry": 100,
                "exit": 101.2,
                "cost_bps_per_side": 10,
                "return": 0.01,
            }
            for index in range(30)
        ] + [
            {
                "symbol": "ORDER",
                "style": "SWING_20D",
                "signal_date": signal_date,
                "plan_id": "out-of-order",
                "entry_date": exit_date,
                "exit_date": exit_date,
                "entry": 100,
                "exit": 100 * (1 + trade_return + 0.002),
                "cost_bps_per_side": 10,
                "return": trade_return,
            }
            for signal_date, exit_date, trade_return in (
                ("2024-12-31", "2025-01-03", -0.2),
                ("2024-12-30", "2025-01-01", -0.2),
                ("2024-12-29", "2025-01-02", 0.3),
            )
        ] + [
            {
                "symbol": "LOSS",
                "style": "SWING_20D",
                "signal_date": "2025-01-01",
                "plan_id": "initial-loss",
                "entry_date": "2025-01-02",
                "exit_date": "2025-01-02",
                "entry": 100,
                "exit": 80.2,
                "cost_bps_per_side": 10,
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


def test_paper_drawdown_uses_equal_weight_exit_date_cohorts(tmp_path):
    path = tmp_path / "paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [
            {
                "symbol": symbol,
                "style": "SWING_20D",
                "plan_id": "same-day",
                "signal_date": "2025-01-01",
                "entry_date": "2025-01-02",
                "exit_date": "2025-01-02",
                "entry": 100,
                "exit": 100 * (1 + trade_return + 0.002),
                "cost_bps_per_side": 10,
                "return": trade_return,
            }
            for symbol, trade_return in (("WIN", 0.4), ("LOSS", -0.4))
        ],
    }), encoding="utf-8")

    summary = update_paper_ledger(
        {"created_at": "2026-01-05T22:00:00Z", "entries": []},
        pd.DataFrame(),
        path=path,
    )

    assert np.isclose(summary["by_plan"]["same-day"]["max_drawdown"], 0)


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
                "signal_date": str((start - pd.Timedelta(days=1) + pd.Timedelta(days=index * 4)).date()),
                "plan_id": "one-symbol",
                "entry_date": str((start + pd.Timedelta(days=index * 4)).date()),
                "exit_date": str((start + pd.Timedelta(days=index * 4)).date()),
                "entry": 100,
                "exit": 101.2,
                "cost_bps_per_side": 10,
                "return": 0.01,
            }
            for index in range(30)
        ] + [
            {
                "symbol": f"TEST{index % 5}",
                "style": "SWING_20D",
                "signal_date": str((start - pd.Timedelta(days=1) + pd.Timedelta(days=index)).date()),
                "plan_id": "short-burst",
                "entry_date": str((start + pd.Timedelta(days=index)).date()),
                "exit_date": str((start + pd.Timedelta(days=index)).date()),
                "entry": 100,
                "exit": 101.2,
                "cost_bps_per_side": 10,
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


def test_paper_gate_rejects_nonfinite_closed_evidence(tmp_path):
    path = tmp_path / "paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [{
            "symbol": "TEST",
            "style": "SWING_20D",
            "plan_id": "invalid",
            "signal_date": "2025-01-01",
            "exit_date": "2025-01-02",
            "return": float("inf"),
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="finite returns"):
        update_paper_ledger(
            {"created_at": "2026-01-05T22:00:00Z", "entries": []},
            pd.DataFrame(),
            path=path,
        )


def test_paper_gate_rejects_duplicate_closed_evidence(tmp_path):
    path = tmp_path / "paper.json"
    closed = [
        {
            "symbol": f"TEST{index}",
            "style": "SWING_20D",
            "plan_id": "duplicated",
            "signal_date": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=index * 30)).date()),
            "exit_date": str((pd.Timestamp("2025-01-02") + pd.Timedelta(days=index * 30)).date()),
            "return": 0.01,
        }
        for index in range(5)
    ]
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": closed * 6,
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        update_paper_ledger(
            {"created_at": "2026-01-05T22:00:00Z", "entries": []},
            pd.DataFrame(),
            path=path,
        )


def test_paper_gate_rejects_exit_before_signal(tmp_path):
    path = tmp_path / "paper.json"
    start = pd.Timestamp("2025-01-01")
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [
            {
                "symbol": f"TEST{index % 5}",
                "style": "SWING_20D",
                "plan_id": "backdated",
                "signal_date": str((start + pd.Timedelta(days=index * 4 + 1)).date()),
                "exit_date": str((start + pd.Timedelta(days=index * 4)).date()),
                "return": 0.01,
            }
            for index in range(30)
        ],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="chronology"):
        update_paper_ledger(
            {"created_at": "2026-01-05T22:00:00Z", "entries": []},
            pd.DataFrame(),
            path=path,
        )


def test_paper_gate_rejects_exit_after_run_as_of(tmp_path):
    path = tmp_path / "paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [{
            "symbol": "TEST",
            "style": "SWING_20D",
            "plan_id": "future",
            "signal_date": "2026-01-05",
            "exit_date": "2026-01-07",
            "return": 0.01,
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="as-of"):
        update_paper_ledger(
            {"created_at": "2026-01-06T22:00:00Z", "entries": []},
            pd.DataFrame(),
            path=path,
        )


def test_paper_gate_rejects_closed_evidence_without_fill_date(tmp_path):
    path = tmp_path / "paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [{
            "symbol": "TEST",
            "style": "SWING_20D",
            "plan_id": "unfilled",
            "signal_date": "2026-01-05",
            "exit_date": "2026-01-06",
            "return": 0.01,
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="fill"):
        update_paper_ledger(
            {"created_at": "2026-01-06T22:00:00Z", "entries": []},
            pd.DataFrame(),
            path=path,
        )


def test_paper_gate_rejects_return_that_does_not_match_prices(tmp_path):
    path = tmp_path / "paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "positions": [],
        "cancelled": [],
        "closed": [{
            "symbol": "TEST",
            "style": "SWING_20D",
            "plan_id": "tampered",
            "signal_date": "2026-01-05",
            "entry_date": "2026-01-06",
            "exit_date": "2026-01-06",
            "entry": 100,
            "exit": 90,
            "cost_bps_per_side": 10,
            "return": 0.5,
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="reconciled"):
        update_paper_ledger(
            {"created_at": "2026-01-06T22:00:00Z", "entries": []},
            pd.DataFrame(),
            path=path,
        )


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
        "news_action": "pass",
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
    assert research_agent._paper_plan_id({**row, "risk_pct": 0.01}, 10) != original

    def changed_bracket_exit(bar, entry, stop, target, *, fill_bar=False):
        return None, ""

    monkeypatch.setattr(research_agent, "_bracket_exit", changed_bracket_exit)

    assert research_agent._paper_plan_id(row, 10) != original
