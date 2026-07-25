import numpy as np
import pandas as pd

import json

from market_dashboard.modules.research_agent import publish_research_result, run_research_loop


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
