"""Run the bounded research loop and publish its latest decision."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_dashboard.modules.data import DATA_SOURCE_AUTO, load_market_data
from market_dashboard.modules.research_agent import BENCHMARK_SYMBOL, DEFAULT_SHADOW_LEDGER_PATH, append_research_history, publish_research_result, recent_rejected_holdout_trials, run_research_loop, update_paper_ledger


DEFAULT_UNIVERSE = "AAPL,MSFT,NVDA,AMZN,GOOGL,META,AVGO,TSLA,JPM,BAC,XOM,CVX,LLY,JNJ,PFE,UNH,WMT,COST,HD,PG"
NEWS_SNAPSHOT_PATH = Path(__file__).resolve().parent / "execution_dashboard" / "data" / "market_research_snapshot.json"
WATCH_LOCK_PATH = Path(__file__).resolve().parent / "execution_dashboard" / "data" / "research_agent.lock"


def acquire_watch_lock(path=WATCH_LOCK_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def refresh_news():
    try:
        result = subprocess.run(
            ["node", str(Path(__file__).resolve().parent / "execution_dashboard" / "server.js"), "--refresh-agent-news"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"News gate unavailable: {error}"


def apply_news_snapshot(result):
    try:
        snapshot = json.loads(NEWS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        symbols = snapshot["symbols"]
        news_version = ":".join(filter(None, [
            snapshot.get("research_version", "news-unversioned"),
            snapshot.get("ai_status", "ai-unavailable"),
            snapshot.get("ai_model", ""),
        ]))
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        symbols = {}
        news_version = "news-unavailable"
    result["news_version"] = news_version
    for entry in result["entries"]:
        news = symbols.get(entry["symbol"], {})
        action = news.get("action", "news_unavailable")
        entry.update({
            "news_action": action,
            "news_status": news.get("news_status", "news_unavailable"),
            "news": news.get("news", []),
            "news_reasons": news.get("reasons", ["news unavailable"]),
            "news_version": news_version,
            "status": {
                "pass": "PAPER_CANDIDATE",
                "reduce": "PAPER_CANDIDATE_REDUCED",
                "reject": "REJECTED_BY_NEWS",
            }.get(action, "PAPER_CANDIDATE_REDUCED_NEWS_UNAVAILABLE"),
        })


def run_once(args):
    universe = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    if not universe or args.years <= 0 or args.folds < 4 or args.warmup < 20 or args.cost_bps < 0:
        raise ValueError("symbols, positive years, at least 4 folds, warmup >= 20, and non-negative costs required")
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=round(args.years * 365.25))
    data, status = load_market_data(
        [*universe, BENCHMARK_SYMBOL],
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
        excluded_holdout_trials=recent_rejected_holdout_trials(),
    )
    publish_research_result(result)
    news_status = refresh_news()
    apply_news_snapshot(result)
    result["paper_evidence"] = update_paper_ledger(result, data, cost_bps_per_side=args.cost_bps)
    result["shadow_evidence"] = update_paper_ledger(
        {"created_at": result["created_at"], "entries": result["shadow_entries"]},
        data,
        path=DEFAULT_SHADOW_LEDGER_PATH,
        cost_bps_per_side=args.cost_bps,
        cancel_withdrawn=False,
    )
    publish_research_result(result)
    append_research_history(result)
    passed = [style for style, row in result["styles"].items() if row["acceptance"]["status"] == "pass"]
    print(f"{result['created_at']} evaluated {result['evaluated_candidates']} candidates from {status.get('source', 'market data')}")
    print(f"Passed styles: {', '.join(passed) if passed else 'none; execution remains blocked'}")
    print(f"Paper evidence: {result['paper_evidence']['status']} ({result['paper_evidence']['current_closed_trades']} current-plan closed trades)")
    print(f"Shadow evidence: {result['shadow_evidence']['closed_trades']} closed development-qualified observations")
    print(news_status)
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
    watch_lock = acquire_watch_lock() if args.watch_minutes > 0 else None
    if args.watch_minutes > 0 and watch_lock is None:
        print("Research watcher already running; duplicate exited.")
        return

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
