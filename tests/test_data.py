import pandas as pd
import pytest

from market_dashboard.modules.data import (
    DATA_SOURCE_AUTO,
    DATA_SOURCE_OPTIONS,
    DATA_SOURCE_STOOQ,
    MAX_DEMO_POINTS,
    PRICE_COLUMNS,
    _clean_provider_data,
    available_tickers,
    demo_market_data,
    get_close_prices,
    get_ticker_frame,
    load_market_data,
    normalize_market_data,
    validate_ohlcv,
)


def _single_ticker_frame() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=3)
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0],
            "High": [11.0, 12.0, 13.0],
            "Low": [9.5, 10.5, 11.5],
            "Close": [10.5, 11.5, 12.5],
            "Volume": [1000, 1100, 1200],
        },
        index=index,
    )


def test_normalize_single_ticker_frame_to_standard_multiindex():
    data = normalize_market_data(_single_ticker_frame(), "aapl")

    assert isinstance(data.columns, pd.MultiIndex)
    assert data.columns.names == ["Field", "Ticker"]
    assert ("Close", "AAPL") in data.columns
    assert data.loc[pd.Timestamp("2024-01-02"), ("Close", "AAPL")] == 11.5


def test_normalize_multi_ticker_frame_and_helpers():
    index = pd.date_range("2024-01-01", periods=2)
    columns = pd.MultiIndex.from_product(
        [["Open", "High", "Low", "Close", "Volume"], ["AAPL", "MSFT"]],
        names=["Field", "Ticker"],
    )
    rows = [
        list(range(row * len(columns), (row + 1) * len(columns)))
        for row in range(len(index))
    ]
    data = pd.DataFrame(rows, index=index, columns=columns)

    normalized = normalize_market_data(data, ["msft", "aapl"])

    assert available_tickers(normalized) == ["AAPL", "MSFT"]
    assert list(get_ticker_frame(normalized, "msft").columns) == PRICE_COLUMNS
    close = get_close_prices(normalized)
    assert list(close.columns) == ["AAPL", "MSFT"]


def test_validate_ohlcv_rejects_missing_required_columns():
    bad_data = _single_ticker_frame().drop(columns=["Volume"])

    with pytest.raises(ValueError, match="missing required columns"):
        validate_ohlcv(bad_data)


def test_validate_ohlcv_accepts_normalized_data():
    data = normalize_market_data(_single_ticker_frame(), "AAPL")

    assert validate_ohlcv(data) is True


def test_demo_market_data_matches_standard_schema_and_caps_intraday_points():
    data = demo_market_data(
        ["AAPL", "MSFT"],
        start="2024-01-01",
        end="2024-03-01",
        interval="1m",
    )

    assert isinstance(data.columns, pd.MultiIndex)
    assert data.columns.names == ["Field", "Ticker"]
    assert len(data) <= MAX_DEMO_POINTS
    assert available_tickers(data) == ["AAPL", "MSFT"]
    assert validate_ohlcv(data) is True
    assert not get_close_prices(data).isna().any().any()


def test_load_market_data_can_return_demo_fallback(monkeypatch):
    def fake_download(*args, **kwargs):
        return None

    monkeypatch.setattr("market_dashboard.modules.data.download_data", fake_download)

    data, status = load_market_data(["AAPL"], "2024-01-01", "2024-02-01", "1d")

    assert status["is_demo"] is True
    assert status["source"] == "Demo dataset"
    assert ("Close", "AAPL") in data.columns


def test_load_market_data_reports_partial_ticker_failures(monkeypatch):
    index = pd.date_range("2024-01-01", periods=3)
    columns = pd.MultiIndex.from_product(
        [["Open", "High", "Low", "Close", "Volume"], ["AAPL", "MSFT"]],
        names=["Field", "Ticker"],
    )
    data = pd.DataFrame(1.0, index=index, columns=columns)
    data[("Close", "AAPL")] = [10.0, 11.0, 12.0]
    data[("Close", "MSFT")] = [float("nan"), float("nan"), float("nan")]

    def fake_download(*args, **kwargs):
        return data

    monkeypatch.setattr("market_dashboard.modules.data.download_data", fake_download)

    loaded, status = load_market_data(["AAPL", "MSFT"], "2024-01-01", "2024-02-01", "1d")

    assert status["status"] == "partial"
    assert status["loaded_tickers"] == ["AAPL"]
    assert status["unavailable_tickers"] == ["MSFT"]
    assert ("Close", "AAPL") in loaded.columns
    assert ("Close", "MSFT") not in loaded.columns


def test_provider_cleaning_preserves_missing_symbol_bars():
    index = pd.date_range("2024-01-01", periods=10, freq="B")
    columns = pd.MultiIndex.from_product(
        [PRICE_COLUMNS, ["AAPL", "MSFT"]],
        names=["Field", "Ticker"],
    )
    data = pd.DataFrame(100.0, index=index, columns=columns)
    data.loc[index[5], pd.IndexSlice[:, "MSFT"]] = float("nan")

    cleaned = _clean_provider_data(data, ["AAPL", "MSFT"], min_points=1)

    assert cleaned.loc[index[5], pd.IndexSlice[:, "MSFT"]].isna().all()
    assert cleaned.loc[index[5], ("Close", "AAPL")] == 100


def test_data_source_options_include_auto_and_stooq():
    assert DATA_SOURCE_OPTIONS[0] == DATA_SOURCE_AUTO
    assert DATA_SOURCE_STOOQ in DATA_SOURCE_OPTIONS


def test_load_market_data_auto_can_fall_back_to_stooq(monkeypatch):
    index = pd.date_range("2024-01-01", periods=3)
    columns = pd.MultiIndex.from_product(
        [["Open", "High", "Low", "Close", "Volume"], ["AAPL"]],
        names=["Field", "Ticker"],
    )
    stooq_data = pd.DataFrame(1.0, index=index, columns=columns)
    stooq_data[("Close", "AAPL")] = [10.0, 11.0, 12.0]

    def fake_yahoo(*args, **kwargs):
        return None

    def fake_stooq(*args, **kwargs):
        return stooq_data

    monkeypatch.setattr("market_dashboard.modules.data.download_data", fake_yahoo)
    monkeypatch.setattr("market_dashboard.modules.data.download_stooq_data", fake_stooq)

    loaded, status = load_market_data(
        ["AAPL"],
        "2024-01-01",
        "2024-02-01",
        "1d",
        source=DATA_SOURCE_AUTO,
    )

    assert status["source"] == DATA_SOURCE_STOOQ
    assert status["requested_source"] == DATA_SOURCE_AUTO
    assert status["provider_attempts"] == ["Yahoo Finance", DATA_SOURCE_STOOQ]
    assert ("Close", "AAPL") in loaded.columns


def test_load_market_data_auto_continues_after_partial_yahoo(monkeypatch):
    index = pd.date_range("2024-01-01", periods=10, freq="B")
    partial = pd.DataFrame(
        1.0,
        index=index,
        columns=pd.MultiIndex.from_product([PRICE_COLUMNS, ["AAPL"]], names=["Field", "Ticker"]),
    )
    complete = pd.DataFrame(
        1.0,
        index=index,
        columns=pd.MultiIndex.from_product([PRICE_COLUMNS, ["AAPL", "MSFT"]], names=["Field", "Ticker"]),
    )

    monkeypatch.setattr("market_dashboard.modules.data.download_data", lambda *args: partial)
    monkeypatch.setattr("market_dashboard.modules.data.download_stooq_data", lambda *args: complete)

    loaded, status = load_market_data(
        ["AAPL", "MSFT"],
        "2024-01-01",
        "2024-02-01",
        "1d",
        source=DATA_SOURCE_AUTO,
    )

    assert status["source"] == DATA_SOURCE_STOOQ
    assert status["loaded_tickers"] == ["AAPL", "MSFT"]
    assert ("Close", "MSFT") in loaded.columns
