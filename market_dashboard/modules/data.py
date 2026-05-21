import pandas as pd
import yfinance as yf
from typing import Optional


PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
VALID_INTERVALS = [
    "1m", "2m", "5m", "15m", "30m", "60m", "90m",
    "1h", "1d", "5d", "1wk", "1mo", "3mo",
]


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
        tickers = _coerce_tickers(tickers)

        # Validate dates - ensure they can be converted to datetime
        try:
            start_dt = pd.to_datetime(start)
            end_dt = pd.to_datetime(end)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid date format: {e}")

        if start_dt >= end_dt:
            raise ValueError("Start date must be before end date")

        # Check for reasonable date ranges (not too far in the past/future)
        today = pd.Timestamp.now().normalize()
        min_date = pd.Timestamp('1900-01-01')
        max_date = today + pd.DateOffset(days=365)  # Allow up to 1 year in the future

        if start_dt < min_date or start_dt > max_date:
            raise ValueError(f"Start date must be between {min_date.date()} and {max_date.date()}")

        if end_dt < min_date or end_dt > max_date:
            raise ValueError(f"End date must be between {min_date.date()} and {max_date.date()}")

        # Validate interval
        if interval not in VALID_INTERVALS:
            raise ValueError(f"Invalid interval. Must be one of: {VALID_INTERVALS}")

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

        data = _normalize_columns(data, tickers)

        if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is not None:
            data.index = data.index.tz_convert(None)

        # Validate data has required columns (be more lenient)
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

        # Clean data: drop rows with all NaN in Close column, then forward fill
        close_cols = [("Close", ticker) for ticker in tickers if ("Close", ticker) in data.columns]
        
        if close_cols:
            data = data.dropna(subset=close_cols, how='all')
        data = data.sort_index()
        data = data.ffill()

        # Check if we have minimum required data
        if len(data) < 10:  # Require at least 10 data points
            raise ValueError("Insufficient data after cleaning (need at least 10 data points)")

        return data

    except Exception as e:
        print(f"Error downloading data for {tickers}: {str(e)}")
        return None
