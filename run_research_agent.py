"""Run the bounded research loop and publish its latest decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, time as clock_time, timedelta, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_dashboard.modules.data import DATA_SOURCE_AUTO, DATA_SOURCE_STOOQ, DATA_SOURCE_YAHOO, get_ticker_frame, load_market_data
from market_dashboard.modules.research_agent import BENCHMARK_SYMBOL, DEFAULT_AGENT_RESULT_PATH, DEFAULT_CANDIDATES, DEFAULT_SHADOW_LEDGER_PATH, append_research_history, publish_research_result, recent_rejected_holdout_trials, run_research_loop, update_paper_ledger


DEFAULT_UNIVERSE = "AAPL,MSFT,NVDA,AMZN,GOOGL,META,AVGO,TSLA,JPM,BAC,XOM,CVX,LLY,JNJ,PFE,UNH,WMT,COST,HD,PG"
NEWS_SNAPSHOT_PATH = Path(__file__).resolve().parent / "execution_dashboard" / "data" / "market_research_snapshot.json"
WATCH_LOCK_PATH = Path(__file__).resolve().parent / "execution_dashboard" / "data" / "research_agent.lock"
RESEARCH_SNAPSHOT_DIR = Path(__file__).resolve().parent / "execution_dashboard" / "data" / "research_snapshots"
NEWS_SNAPSHOT_MAX_AGE = timedelta(minutes=30)
MIN_HISTORY_COVERAGE = 0.90
MAX_LATEST_BAR_AGE_DAYS = 7
MARKET_DATA_READY_TIME = clock_time(16, 15)


def research_end_date(now=None):
    """Return the provider-exclusive end date for completed New York sessions."""
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return now.date() if now.time() < MARKET_DATA_READY_TIME else now.date() + timedelta(days=1)


def validate_research_data(data, status, symbols, start, end, warmup, folds, *, now=None):
    """Fail closed unless the research frame has current, complete real OHLC data."""
    if status.get("is_demo") or status.get("source") not in {DATA_SOURCE_YAHOO, DATA_SOURCE_STOOQ}:
        raise RuntimeError("refusing research without a recognized real-data provider")
    missing = sorted(set(symbols) - set(status.get("loaded_tickers", [])))
    if missing:
        raise RuntimeError(f"market data missing required symbols: {', '.join(missing)}")
    if not isinstance(data.index, pd.DatetimeIndex) or not data.index.is_monotonic_increasing or data.index.has_duplicates:
        raise RuntimeError("market data requires a unique chronological DatetimeIndex")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if data.index.max() >= end:
        raise RuntimeError("market data contains a future bar")
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    if pd.Timestamp(data.index.max()).date() >= now.date() and now.time() < MARKET_DATA_READY_TIME:
        raise RuntimeError("market data contains an incomplete current session")
    minimum_rows = warmup + folds * 10
    minimum_span = (end - start).days * MIN_HISTORY_COVERAGE
    latest_cutoff = end - pd.Timedelta(days=MAX_LATEST_BAR_AGE_DAYS + 1)
    for symbol in symbols:
        frame = get_ticker_frame(data, symbol)
        ohlc = frame[["Open", "High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(ohlc) < minimum_rows:
            raise RuntimeError(f"{symbol} has fewer than {minimum_rows} complete OHLC bars")
        if ohlc.index.max() < latest_cutoff:
            raise RuntimeError(f"{symbol} latest bar is stale")
        if (ohlc.index.max() - ohlc.index.min()).days < minimum_span:
            raise RuntimeError(f"{symbol} does not cover 90% of the requested history")
        price_tolerance = ohlc.abs().max(axis=1).clip(lower=1) * 1e-12
        if (
            not np.isfinite(ohlc.to_numpy()).all()
            or (ohlc <= 0).any().any()
            or (ohlc["High"] + price_tolerance < ohlc[["Open", "Close"]].max(axis=1)).any()
            or (ohlc["Low"] - price_tolerance > ohlc[["Open", "Close"]].min(axis=1)).any()
        ):
            raise RuntimeError(f"{symbol} has invalid OHLC prices")


def _canonical_ohlc_csv(data, symbol):
    frame = get_ticker_frame(data, symbol)[["Open", "High", "Low", "Close"]].dropna().sort_index()
    return frame, frame.to_csv(date_format="%Y-%m-%d", float_format="%.10g").encode("utf-8")


def research_data_provenance(data, status, symbols):
    """Describe and fingerprint the exact validated OHLC snapshot used by a run."""
    provider_package = {
        DATA_SOURCE_YAHOO: "yfinance",
        DATA_SOURCE_STOOQ: "requests",
    }.get(status.get("source"))
    digest = hashlib.sha256()
    coverage = {}
    for symbol in sorted(symbols):
        frame, csv_bytes = _canonical_ohlc_csv(data, symbol)
        digest.update(symbol.encode("utf-8"))
        digest.update(csv_bytes)
        coverage[symbol] = {
            "first": str(frame.index.min().date()),
            "last": str(frame.index.max().date()),
            "rows": int(len(frame)),
        }
    return {
        **{
            key: status.get(key)
            for key in (
                "source",
                "requested_source",
                "provider_attempts",
                "date_start",
                "date_end",
                "row_count",
                "loaded_tickers",
                "unavailable_tickers",
                "is_demo",
            )
        },
        "dataset_sha256": digest.hexdigest(),
        "coverage": coverage,
        "provider_client": f"{provider_package} {package_version(provider_package)}" if provider_package else "unavailable",
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
    }


def verify_research_snapshot(path, symbols, expected_sha256):
    """Fail closed unless an archive contains the exact canonical run inputs."""
    digest = hashlib.sha256()
    expected_entries = {f"{quote(symbol, safe='')}.csv" for symbol in symbols}
    try:
        with zipfile.ZipFile(path) as archive:
            if set(archive.namelist()) != expected_entries or len(archive.namelist()) != len(expected_entries):
                raise RuntimeError("research snapshot has unexpected or duplicate entries")
            for symbol in sorted(symbols):
                digest.update(symbol.encode("utf-8"))
                digest.update(archive.read(f"{quote(symbol, safe='')}.csv"))
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise RuntimeError(f"research snapshot is unreadable: {error}") from error
    if digest.hexdigest() != expected_sha256:
        raise RuntimeError("research snapshot hash does not match validated market data")


def persist_research_snapshot(data, symbols, provenance, directory=RESEARCH_SNAPSHOT_DIR):
    """Write one immutable, deduplicated archive for the exact validated OHLC data."""
    directory.mkdir(parents=True, exist_ok=True)
    dataset_hash = provenance["dataset_sha256"]
    path = directory / f"{dataset_hash}.zip"
    if path.exists():
        verify_research_snapshot(path, symbols, dataset_hash)
    else:
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for symbol in sorted(symbols):
                    _, csv_bytes = _canonical_ohlc_csv(data, symbol)
                    info = zipfile.ZipInfo(f"{quote(symbol, safe='')}.csv")
                    info.date_time = (1980, 1, 1, 0, 0, 0)
                    archive.writestr(info, csv_bytes)
            verify_research_snapshot(temporary_path, symbols, dataset_hash)
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                verify_research_snapshot(path, symbols, dataset_hash)
        finally:
            temporary_path.unlink(missing_ok=True)
    try:
        recorded_path = path.relative_to(Path(__file__).resolve().parent)
    except ValueError:
        recorded_path = path
    return {
        **provenance,
        "snapshot_format": "ohlc-csv-zip-v1",
        "snapshot_path": recorded_path.as_posix(),
    }


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


def has_new_common_bar(provenance, path=DEFAULT_AGENT_RESULT_PATH):
    """Return true only when the fixed universe has newer common coverage."""
    coverage = provenance.get("coverage", {})
    if not coverage:
        return True
    try:
        previous = json.loads(Path(path).read_text(encoding="utf-8"))["data_provenance"]["coverage"]
        if set(previous) != set(coverage):
            return True
        return min(row["last"] for row in coverage.values()) > min(row["last"] for row in previous.values())
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return True


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


def apply_news_snapshot(result, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        snapshot = json.loads(NEWS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        symbols = snapshot["symbols"]
        if not isinstance(symbols, dict):
            raise TypeError("news symbols must be an object")
        created_at = datetime.fromisoformat(snapshot["created_at"].replace("Z", "+00:00"))
        if created_at > now + timedelta(minutes=5) or now - created_at > NEWS_SNAPSHOT_MAX_AGE:
            raise ValueError("news snapshot is stale")
        news_created_at = snapshot["created_at"]
        news_version = ":".join(filter(None, [
            snapshot.get("research_version", "news-unversioned"),
            snapshot.get("ai_status", "ai-unavailable"),
            snapshot.get("ai_model", ""),
        ]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        symbols = {}
        news_created_at = ""
        news_version = "news-unavailable"
    result["news_version"] = news_version
    result["news_created_at"] = news_created_at
    for entry in result["entries"]:
        news = symbols.get(entry["symbol"], {})
        candidate = news.get("candidate") if isinstance(news, dict) else None
        candidate_fields = ("symbol", "style", "strategy", "signal_date", "entry", "stop", "target")
        if not isinstance(candidate, dict) or any(candidate.get(field) != entry.get(field) for field in candidate_fields):
            news = {}
        action = news.get("action", "news_unavailable")
        if action not in {"pass", "reduce", "reject"} or action == "pass" and news.get("news_status") != "ok":
            action = "news_unavailable"
        entry.update({
            "news_action": action,
            "news_status": news.get("news_status", "news_unavailable"),
            "news": news.get("news", []),
            "news_reasons": news.get("reasons", ["news unavailable"]),
            "news_version": news_version,
            "news_created_at": news_created_at,
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
    end = research_end_date()
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
    validate_research_data(data, status, [*universe, BENCHMARK_SYMBOL], start, end, args.warmup, args.folds)
    provenance = research_data_provenance(data, status, [*universe, BENCHMARK_SYMBOL])
    if getattr(args, "preflight_only", False):
        print(json.dumps(provenance, indent=2, sort_keys=True))
        return {"status": "preflight_only", "data_provenance": provenance}
    if not has_new_common_bar(provenance):
        print("No newer common completed-session coverage; evidence unchanged.")
        return {"status": "unchanged_data", "data_provenance": provenance}
    provenance = persist_research_snapshot(data, [*universe, BENCHMARK_SYMBOL], provenance)

    result = run_research_loop(
        data,
        universe,
        folds=args.folds,
        warmup=args.warmup,
        cost_bps_per_side=args.cost_bps,
        # ponytail: monitoring never spends another holdout; add a separately
        # predeclared authorization path only when genuinely new data exists.
        excluded_holdout_trials={
            *recent_rejected_holdout_trials(),
            *((candidate["style"], candidate["strategy"]) for candidate in DEFAULT_CANDIDATES),
        },
    )
    result["data_provenance"] = provenance
    try:
        publish_research_result(result)
        news_status = refresh_news()
        apply_news_snapshot(result)
        result["paper_evidence"] = update_paper_ledger(result, data, cost_bps_per_side=args.cost_bps)
        result["shadow_evidence"] = update_paper_ledger(
            {"created_at": result["created_at"], "universe": result["universe"], "entries": result["shadow_entries"]},
            data,
            path=DEFAULT_SHADOW_LEDGER_PATH,
            cost_bps_per_side=args.cost_bps,
            cancel_withdrawn=False,
        )
        publish_research_result(result)
    finally:
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
    parser.add_argument("--preflight-only", action="store_true", help="validate and fingerprint real data without evaluating strategies or writing evidence")
    parser.add_argument("--watch-minutes", type=float, default=0, help="Repeat interval; 0 runs once")
    args = parser.parse_args()
    if args.watch_minutes < 0:
        parser.error("--watch-minutes cannot be negative")
    watch_lock = acquire_watch_lock()
    if watch_lock is None:
        print("Research agent already running; duplicate exited.")
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
