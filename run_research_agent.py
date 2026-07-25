"""Run the bounded research loop and publish its latest decision."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

from market_dashboard.modules.data import DATA_SOURCE_AUTO, load_market_data
from market_dashboard.modules.research_agent import publish_research_result, run_research_loop, update_paper_ledger


DEFAULT_UNIVERSE = "AAPL,MSFT,NVDA,AMZN,GOOGL,JPM,XOM,LLY,JNJ,PFE"


def run_once(args):
    universe = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    if not universe or args.years <= 0 or args.folds < 4 or args.warmup < 20 or args.cost_bps < 0:
        raise ValueError("symbols, positive years, at least 4 folds, warmup >= 20, and non-negative costs required")
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=round(args.years * 365.25))
    data, status = load_market_data(
        universe,
        start,
        end,
        "1d",
        allow_demo_fallback=False,
        source=DATA_SOURCE_AUTO,
    )
    if data is None or data.empty:
        raise RuntimeError(status.get("message", "real market data unavailable"))
    if status.get("is_demo"):
        raise RuntimeError("refusing to publish research from demo data")

    result = run_research_loop(
        data,
        universe,
        folds=args.folds,
        warmup=args.warmup,
        cost_bps_per_side=args.cost_bps,
    )
    result["paper_evidence"] = update_paper_ledger(result, data, cost_bps_per_side=args.cost_bps)
    publish_research_result(result)
    passed = [style for style, row in result["styles"].items() if row["acceptance"]["status"] == "pass"]
    print(f"{result['created_at']} evaluated {result['evaluated_candidates']} candidates from {status.get('source', 'market data')}")
    print(f"Passed styles: {', '.join(passed) if passed else 'none; execution remains blocked'}")
    print(f"Paper evidence: {result['paper_evidence']['status']} ({result['paper_evidence']['closed_trades']} closed trades)")
    print(json.dumps(result["entries"], indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="Walk-forward test strategies and publish only final-holdout passes.")
    parser.add_argument("--symbols", default=DEFAULT_UNIVERSE, help="Comma-separated ticker universe")
    parser.add_argument("--years", type=float, default=8, help="Daily history to request")
    parser.add_argument("--folds", type=int, default=5, help="Chronological folds; the last stays untouched until selection")
    parser.add_argument("--warmup", type=int, default=200, help="Indicator warmup rows")
    parser.add_argument("--cost-bps", type=float, default=10, help="Estimated cost per entry/exit side")
    parser.add_argument("--watch-minutes", type=float, default=0, help="Repeat interval; 0 runs once")
    args = parser.parse_args()
    if args.watch_minutes < 0:
        parser.error("--watch-minutes cannot be negative")

    while True:
        try:
            run_once(args)
        except Exception as error:
            if args.watch_minutes <= 0:
                raise
            print(f"{datetime.now(timezone.utc).isoformat()} research run skipped: {error}")
        if args.watch_minutes <= 0:
            return
        time.sleep(args.watch_minutes * 60)


if __name__ == "__main__":
    main()
