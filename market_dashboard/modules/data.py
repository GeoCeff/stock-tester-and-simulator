import math
import pandas as pd
from typing import Optional


PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
MAX_DEMO_POINTS = 1500
DATA_SOURCE_AUTO = "Auto"
DATA_SOURCE_YAHOO = "Yahoo Finance"
DATA_SOURCE_STOOQ = "Stooq"
DATA_SOURCE_DEMO = "Demo dataset"
DEFAULT_DATA_SOURCE = DATA_SOURCE_AUTO
DATA_SOURCE_OPTIONS = [
    DATA_SOURCE_AUTO,
    DATA_SOURCE_YAHOO,
    DATA_SOURCE_STOOQ,
    DATA_SOURCE_DEMO,
]
VALID_INTERVALS = [
    "1m", "2m", "5m", "15m", "30m", "60m", "90m",
    "1h", "1d", "5d", "1wk", "1mo", "3mo",
]
STOOQ_INTERVALS = {"1d"}


def _coerce_tickers(tickers):
    """Return a validated, de-duplicated ticker list."""
    if isinstance(tickers, str):
        raw_tickers = tickers.replace(";", ",").split(",")
    elif isinstance(tickers, (list, tuple, set, pd.Index)):
        raw_tickers = tickers
    else:
        raise ValueError("Tickers must be a string or a list-like value")

    cleaned = []
    for ticker in raw_tickers:
        symbol = str(ticker).strip().upper()
        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    if not cleaned:
        raise ValueError("No tickers provided")

    return cleaned


def normalize_data_source(source: str | None) -> str:
    """Return a supported data-source label."""
    if source is None:
        return DEFAULT_DATA_SOURCE

    text = str(source).strip().lower()
    aliases = {
        "auto": DATA_SOURCE_AUTO,
        "recent": DATA_SOURCE_AUTO,
        "live": DATA_SOURCE_AUTO,
        "yahoo": DATA_SOURCE_YAHOO,
        "yahoo finance": DATA_SOURCE_YAHOO,
        "yf": DATA_SOURCE_YAHOO,
        "stooq": DATA_SOURCE_STOOQ,
        "demo": DATA_SOURCE_DEMO,
        "demo dataset": DATA_SOURCE_DEMO,
        "sample": DATA_SOURCE_DEMO,
    }
    return aliases.get(text, DEFAULT_DATA_SOURCE)


def _validate_download_request(start, end, interval, supported_intervals=None):
    """Validate a provider request and return normalized dates."""
    try:
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format: {e}")

    if start_dt >= end_dt:
        raise ValueError("Start date must be before end date")

    today = pd.Timestamp.now().normalize()
    min_date = pd.Timestamp("1900-01-01")
    max_date = today + pd.DateOffset(days=365)

    if start_dt < min_date or start_dt > max_date:
        raise ValueError(f"Start date must be between {min_date.date()} and {max_date.date()}")

    if end_dt < min_date or end_dt > max_date:
        raise ValueError(f"End date must be between {min_date.date()} and {max_date.date()}")

    if interval not in VALID_INTERVALS:
        raise ValueError(f"Invalid interval. Must be one of: {VALID_INTERVALS}")

    if supported_intervals is not None and interval not in supported_intervals:
        supported = ", ".join(sorted(supported_intervals))
        raise ValueError(f"Selected source supports these intervals here: {supported}")

    return start_dt, end_dt


def _find_level(columns: pd.MultiIndex, candidates) -> Optional[int]:
    candidate_values = {str(value).upper() for value in candidates}
    for level in range(columns.nlevels):
        level_values = {
            str(value).strip().upper()
            for value in columns.get_level_values(level)
        }
        if level_values & candidate_values:
            return level
    return None


def _normalize_columns(data: pd.DataFrame, tickers) -> pd.DataFrame:
    """Normalize yfinance output to (field, ticker) MultiIndex columns."""
    data = data.copy()

    if isinstance(data.columns, pd.MultiIndex):
        price_level = _find_level(data.columns, PRICE_COLUMNS + ["Adj Close"])
        ticker_level = _find_level(data.columns, tickers)

        if price_level is None:
            raise ValueError("Downloaded data did not include recognizable OHLCV columns")

        if ticker_level is None:
            if len(tickers) == 1:
                ticker_values = [tickers[0]] * len(data.columns)
            else:
                raise ValueError("Downloaded data did not include recognizable ticker columns")
        else:
            ticker_values = data.columns.get_level_values(ticker_level)

        data.columns = pd.MultiIndex.from_arrays(
            [
                data.columns.get_level_values(price_level),
                ticker_values,
            ],
            names=["Field", "Ticker"],
        )
    else:
        if len(tickers) != 1:
            raise ValueError("Multi-ticker download returned single-level columns")
        data.columns = pd.MultiIndex.from_product(
            [data.columns, [tickers[0]]],
            names=["Field", "Ticker"],
        )

    canonical_fields = {field.upper(): field for field in PRICE_COLUMNS + ["Adj Close"]}
    normalized_columns = []
    for field, ticker in data.columns:
        field_name = canonical_fields.get(str(field).strip().upper(), str(field).strip())
        ticker_name = str(ticker).strip().upper()
        normalized_columns.append((field_name, ticker_name))

    data.columns = pd.MultiIndex.from_tuples(
        normalized_columns,
        names=["Field", "Ticker"],
    )

    return data


def normalize_market_data(data: pd.DataFrame, tickers) -> pd.DataFrame:
    """Public wrapper for normalizing market data into the app schema."""
    tickers = _coerce_tickers(tickers)
    return _normalize_columns(data, tickers)


def available_tickers(data: pd.DataFrame) -> list[str]:
    """Return sorted tickers available in a normalized market data frame."""
    if data is None or data.empty:
        return []

    if isinstance(data.columns, pd.MultiIndex):
        ticker_level = _find_level(data.columns, PRICE_COLUMNS)
        if ticker_level == 0:
            values = data.columns.get_level_values(1)
        elif ticker_level == 1:
            values = data.columns.get_level_values(0)
        else:
            values = data.columns.get_level_values(-1)
        return sorted({str(value).strip().upper() for value in values if str(value).strip()})

    return []


def tickers_with_valid_close(data: pd.DataFrame, tickers) -> list[str]:
    """Return requested tickers that have at least one usable close price."""
    if data is None or data.empty:
        return []

    requested = _coerce_tickers(tickers)
    loaded = []
    for ticker in requested:
        try:
            ticker_data = get_ticker_frame(data, ticker)
            close = pd.to_numeric(ticker_data["Close"], errors="coerce")
            if not close.dropna().empty:
                loaded.append(ticker)
        except Exception:
            continue

    return loaded


def filter_market_data_tickers(data: pd.DataFrame, tickers) -> pd.DataFrame:
    """Filter normalized market data to the requested ticker list."""
    if data is None or data.empty or not isinstance(data.columns, pd.MultiIndex):
        return data

    requested = set(_coerce_tickers(tickers))
    field_level = _find_level(data.columns, PRICE_COLUMNS)
    if field_level is None:
        return data

    ticker_level = 1 if field_level == 0 else 0
    keep_columns = [
        column for column in data.columns
        if str(column[ticker_level]).strip().upper() in requested
    ]

    return data.loc[:, keep_columns].copy()


def market_data_status(
    data: pd.DataFrame | None,
    tickers,
    source: str,
    is_demo: bool,
    message: str,
    interval: str,
    requested_source: str | None = None,
    provider_attempts: list[str] | None = None,
) -> dict:
    """Build a UI-friendly status payload for downloaded or demo market data."""
    requested = _coerce_tickers(tickers)
    loaded = tickers_with_valid_close(data, requested) if data is not None else []
    unavailable = [ticker for ticker in requested if ticker not in loaded]

    if data is None or data.empty or not loaded:
        state = "unavailable"
    elif is_demo:
        state = "demo"
        unavailable = []
        loaded = requested
    elif unavailable:
        state = "partial"
    else:
        state = "live"

    if data is not None and not data.empty:
        date_start = pd.Timestamp(data.index.min()).strftime("%Y-%m-%d")
        date_end = pd.Timestamp(data.index.max()).strftime("%Y-%m-%d")
        row_count = int(len(data))
    else:
        date_start = "N/A"
        date_end = "N/A"
        row_count = 0

    return {
        "status": state,
        "source": source,
        "is_demo": is_demo,
        "message": message,
        "row_count": row_count,
        "date_start": date_start,
        "date_end": date_end,
        "latest_bar": date_end,
        "interval": interval,
        "requested_source": requested_source or source,
        "provider_attempts": provider_attempts or [source],
        "requested_tickers": requested,
        "loaded_tickers": loaded,
        "unavailable_tickers": unavailable,
    }


def get_ticker_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Return an OHLCV frame for one ticker from normalized data."""
    if data is None or data.empty:
        raise ValueError("No market data provided")

    symbol = str(ticker).strip().upper()
    if not symbol:
        raise ValueError("Ticker is required")

    if not isinstance(data.columns, pd.MultiIndex):
        return data.copy()

    if symbol in {str(value).strip().upper() for value in data.columns.get_level_values(1)}:
        ticker_data = data.xs(symbol, level=1, axis=1)
    elif symbol in {str(value).strip().upper() for value in data.columns.get_level_values(0)}:
        ticker_data = data.xs(symbol, level=0, axis=1)
    else:
        raise ValueError(f"Ticker {symbol} not found in market data")

    return ticker_data.reindex(columns=PRICE_COLUMNS)


def get_close_prices(data: pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Return close prices from a normalized market data frame."""
    if data is None or data.empty:
        raise ValueError("No market data provided")

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close = data.xs("Close", level=0, axis=1)
        elif "Close" in data.columns.get_level_values(1):
            close = data.xs("Close", level=1, axis=1)
        else:
            raise ValueError("Market data does not include a Close column")
        return close.iloc[:, 0] if close.shape[1] == 1 else close

    if "Close" not in data.columns:
        raise ValueError("Market data does not include a Close column")
    return data["Close"]


def validate_ohlcv(data: pd.DataFrame) -> bool:
    """Validate that market data includes the standard OHLCV columns."""
    if data is None or data.empty:
        raise ValueError("Market data is empty")

    if isinstance(data.columns, pd.MultiIndex):
        field_level = _find_level(data.columns, PRICE_COLUMNS)
        if field_level is None:
            raise ValueError("Market data does not include recognizable OHLCV columns")
        available = {str(value).strip() for value in data.columns.get_level_values(field_level)}
    else:
        available = {str(value).strip() for value in data.columns}

    missing = [column for column in PRICE_COLUMNS if column not in available]
    if missing:
        raise ValueError(f"Market data is missing required columns: {missing}")

    return True


def _date_index_for_interval(start, end, interval: str) -> pd.DatetimeIndex:
    """Create a deterministic date index for demo data."""
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)

    if pd.isna(start_dt) or pd.isna(end_dt) or start_dt >= end_dt:
        end_dt = pd.Timestamp.now().normalize()
        start_dt = end_dt - pd.DateOffset(months=6)

    if interval == "1m":
        freq = "min"
    elif interval == "5m":
        freq = "5min"
    elif interval == "15m":
        freq = "15min"
    elif interval in {"1h", "60m"}:
        freq = "h"
    else:
        freq = "B"

    index = pd.date_range(start=start_dt, end=end_dt, freq=freq)
    if len(index) > MAX_DEMO_POINTS:
        step = math.ceil(len(index) / MAX_DEMO_POINTS)
        return index[::step][:MAX_DEMO_POINTS]

    if len(index) >= 30:
        return index

    fallback_end = max(end_dt, start_dt + pd.DateOffset(days=45))
    return pd.date_range(start=start_dt, end=fallback_end, freq=freq)


def demo_market_data(tickers, start=None, end=None, interval: str = "1d") -> pd.DataFrame:
    """Create deterministic OHLCV data so the app works without market data access."""
    tickers = _coerce_tickers(tickers)
    end = end if end is not None else pd.Timestamp.now().normalize()
    start = start if start is not None else pd.to_datetime(end) - pd.DateOffset(months=6)
    index = _date_index_for_interval(start, end, interval)

    series_by_column = {}
    for ticker_idx, ticker in enumerate(tickers):
        base_price = 80.0 + ticker_idx * 18.0
        trend = 0.0015 + ticker_idx * 0.00025
        prices = []

        for step in range(len(index)):
            cycle = math.sin(step / 8 + ticker_idx) * 1.8
            smaller_cycle = math.cos(step / 17 + ticker_idx) * 0.8
            price = base_price * (1 + trend * step) + cycle + smaller_cycle
            prices.append(max(price, 1.0))

        close = pd.Series(prices, index=index)
        open_price = close.shift(1).fillna(close.iloc[0] * 0.995)
        high = pd.concat([open_price, close], axis=1).max(axis=1) * 1.006
        low = pd.concat([open_price, close], axis=1).min(axis=1) * 0.994
        volume = pd.Series(
            [1_000_000 + ticker_idx * 150_000 + (step % 20) * 7_500 for step in range(len(index))],
            index=index,
            dtype=float,
        )

        series_by_column[("Open", ticker)] = open_price.round(2)
        series_by_column[("High", ticker)] = high.round(2)
        series_by_column[("Low", ticker)] = low.round(2)
        series_by_column[("Close", ticker)] = close.round(2)
        series_by_column[("Volume", ticker)] = volume

    data = pd.DataFrame(series_by_column, index=index)
    data.columns = pd.MultiIndex.from_tuples(data.columns, names=["Field", "Ticker"])
    return data.reindex(columns=[(field, ticker) for field in PRICE_COLUMNS for ticker in tickers])


def _successful_market_data_response(data, requested_tickers, source, requested_source, provider_attempts, interval):
    """Return filtered data plus a status object for a successful provider response."""
    loaded_tickers = tickers_with_valid_close(data, requested_tickers)
    if not loaded_tickers:
        return None

    filtered_data = filter_market_data_tickers(data, loaded_tickers)
    unavailable = [ticker for ticker in requested_tickers if ticker not in loaded_tickers]
    message = f"Partial market data loaded from {source}" if unavailable else f"Market data loaded from {source}"
    status = market_data_status(
        filtered_data,
        requested_tickers,
        source=source,
        is_demo=False,
        message=message,
        interval=interval,
        requested_source=requested_source,
        provider_attempts=provider_attempts,
    )
    return filtered_data, status


def _demo_market_data_response(requested_tickers, start, end, interval, requested_source, provider_attempts, message):
    demo_data = demo_market_data(requested_tickers, start, end, interval)
    return demo_data, market_data_status(
        demo_data,
        requested_tickers,
        source=DATA_SOURCE_DEMO,
        is_demo=True,
        message=message,
        interval=interval,
        requested_source=requested_source,
        provider_attempts=provider_attempts + [DATA_SOURCE_DEMO],
    )


def _source_downloaders(source, interval):
    """Return provider downloaders in the order they should be attempted."""
    if source == DATA_SOURCE_YAHOO:
        return [(DATA_SOURCE_YAHOO, download_data)]

    if source == DATA_SOURCE_STOOQ:
        return [(DATA_SOURCE_STOOQ, download_stooq_data)]

    if source == DATA_SOURCE_AUTO:
        providers = [(DATA_SOURCE_YAHOO, download_data)]
        if interval in STOOQ_INTERVALS:
            providers.append((DATA_SOURCE_STOOQ, download_stooq_data))
        return providers

    return []


def load_market_data(
    tickers,
    start,
    end,
    interval,
    allow_demo_fallback: bool = True,
    source: str | None = DATA_SOURCE_YAHOO,
):
    """Download market data from the selected source, with optional demo fallback."""
    requested_tickers = _coerce_tickers(tickers)
    requested_source = normalize_data_source(source)

    if requested_source == DATA_SOURCE_DEMO:
        return _demo_market_data_response(
            requested_tickers,
            start,
            end,
            interval,
            requested_source,
            [],
            "Using demo data by request",
        )

    provider_attempts = []
    partial_response = None
    for provider_name, downloader in _source_downloaders(requested_source, interval):
        provider_attempts.append(provider_name)
        data = downloader(requested_tickers, start, end, interval)
        if data is None or data.empty:
            continue

        response = _successful_market_data_response(
            data,
            requested_tickers,
            provider_name,
            requested_source,
            provider_attempts.copy(),
            interval,
        )
        if response is not None:
            if response[1]["status"] == "live":
                return response
            partial_response = partial_response or response

    if partial_response is not None:
        return partial_response

    unavailable_source = requested_source if requested_source != DATA_SOURCE_AUTO else ", ".join(provider_attempts) or DATA_SOURCE_AUTO
    if not allow_demo_fallback:
        return None, market_data_status(
            None,
            requested_tickers,
            source=unavailable_source,
            is_demo=False,
            message=f"Market data unavailable from {unavailable_source}",
            interval=interval,
            requested_source=requested_source,
            provider_attempts=provider_attempts,
        )

    message = "Using demo data because selected market data sources are unavailable"
    if requested_source == DATA_SOURCE_AUTO and interval not in STOOQ_INTERVALS:
        message = "Using demo data because recent intraday data is unavailable from Yahoo Finance"

    return _demo_market_data_response(
        requested_tickers,
        start,
        end,
        interval,
        requested_source,
        provider_attempts,
        message,
    )


def _clean_provider_data(data: pd.DataFrame, tickers, min_points: int = 10) -> pd.DataFrame:
    """Normalize and clean a provider response into the app's standard schema."""
    data = _normalize_columns(data, tickers)

    if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is not None:
        data.index = data.index.tz_convert(None)

    available_columns = data.columns.get_level_values(0).unique()
    missing_columns = [col for col in PRICE_COLUMNS if col not in available_columns]
    if missing_columns:
        for col in missing_columns:
            for ticker in tickers:
                if (col, ticker) not in data.columns:
                    data[(col, ticker)] = float("nan")

    ordered_columns = [
        (field, ticker)
        for field in PRICE_COLUMNS
        for ticker in tickers
    ]
    extra_columns = [col for col in data.columns if col not in ordered_columns]
    data = data.reindex(columns=ordered_columns + extra_columns)

    close_cols = [("Close", ticker) for ticker in tickers if ("Close", ticker) in data.columns]
    if close_cols:
        data = data.dropna(subset=close_cols, how="all")
    data = data.sort_index()
    data = data.ffill()

    if len(data) < min_points:
        raise ValueError(f"Insufficient data after cleaning (need at least {min_points} data points)")

    return data


def download_data(tickers, start, end, interval) -> Optional[pd.DataFrame]:
    """
    Download stock data with proper error handling and validation.

    Args:
        tickers: Stock ticker(s) - string or list
        start: Start date
        end: End date
        interval: Data interval

    Returns:
        DataFrame with OHLCV data or None if failed
    """
    try:
        import yfinance as yf

        tickers = _coerce_tickers(tickers)
        start_dt, end_dt = _validate_download_request(start, end, interval)

        data = yf.download(
            tickers,
            start=start_dt,
            end=end_dt,
            interval=interval,
            auto_adjust=True,
            group_by="column",
            progress=False,
            threads=False,
        )

        # Check if data was retrieved successfully
        if data is None or data.empty:
            raise ValueError("No data retrieved from Yahoo Finance")

        return _clean_provider_data(data, tickers)

    except Exception as e:
        print(f"Error downloading data for {tickers}: {str(e)}")
        return None


def _stooq_symbol(ticker: str) -> str:
    """Map a ticker to the symbol format used by Stooq's CSV endpoint."""
    symbol = str(ticker).strip().lower().replace("-", ".")
    known_suffixes = (
        ".us", ".uk", ".de", ".fr", ".nl", ".pl", ".jp",
        ".hk", ".ca", ".au", ".ch", ".it", ".es",
    )
    if "." not in symbol or not symbol.endswith(known_suffixes):
        symbol = f"{symbol}.us"
    return symbol


def _stooq_frame_to_ohlcv(frame: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """Convert one Stooq CSV frame into the normalized OHLCV schema."""
    if frame is None or frame.empty or "Date" not in frame.columns:
        return None

    renamed = {column: str(column).strip().title() for column in frame.columns}
    frame = frame.rename(columns=renamed)
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"]).set_index("Date").sort_index()
    if frame.empty:
        return None

    for column in PRICE_COLUMNS:
        if column not in frame.columns:
            frame[column] = float("nan")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.reindex(columns=PRICE_COLUMNS)
    frame.columns = pd.MultiIndex.from_product(
        [PRICE_COLUMNS, [str(ticker).strip().upper()]],
        names=["Field", "Ticker"],
    )
    return frame


def download_stooq_data(tickers, start, end, interval) -> Optional[pd.DataFrame]:
    """
    Download daily stock data from Stooq's CSV endpoint.

    Stooq is used here as a no-key daily source and as Auto's fallback when
    Yahoo Finance is unavailable.
    """
    try:
        from urllib.parse import urlencode
        from urllib.request import urlopen

        tickers = _coerce_tickers(tickers)
        start_dt, end_dt = _validate_download_request(start, end, interval, STOOQ_INTERVALS)

        frames = []
        for ticker in tickers:
            params = urlencode({
                "s": _stooq_symbol(ticker),
                "d1": start_dt.strftime("%Y%m%d"),
                "d2": end_dt.strftime("%Y%m%d"),
                "i": "d",
            })
            url = f"https://stooq.com/q/d/l/?{params}"
            with urlopen(url, timeout=12) as response:
                raw_frame = pd.read_csv(response)
            ticker_frame = _stooq_frame_to_ohlcv(raw_frame, ticker)
            if ticker_frame is not None:
                frames.append(ticker_frame)

        if not frames:
            raise ValueError("No data retrieved from Stooq")

        data = pd.concat(frames, axis=1).sort_index()
        return _clean_provider_data(data, tickers)

    except Exception as e:
        print(f"Error downloading Stooq data for {tickers}: {str(e)}")
        return None
