"""Tests for data provider factory and Bybit data normalization."""
import pytest
from src.utils.data_provider_factory import create_data_provider
from src.utils.binance_data_provider import BinanceDataProvider
from src.utils.bybit_data_provider import BybitDataProvider
from src.utils.constants import COLUMNS, BYBIT_INTERVAL_MAP, INTERVAL_MS


class TestDataProviderFactory:
    def test_creates_binance(self):
        p = create_data_provider("binance")
        assert isinstance(p, BinanceDataProvider)

    def test_creates_bybit(self):
        p = create_data_provider("bybit")
        assert isinstance(p, BybitDataProvider)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown exchange"):
            create_data_provider("kraken")


class TestBybitNormalization:
    def test_normalize_empty_returns_empty(self):
        df = BybitDataProvider._normalize([], "1h")
        assert df.empty

    def test_normalize_matches_columns(self):
        # Simulate Bybit kline row: [startTime, open, high, low, close, volume, turnover]
        klines = [
            ["1700000000000", "50000", "50500", "49800", "50200", "100", "5000000"],
            ["1700003600000", "50200", "50800", "50100", "50600", "120", "6000000"],
        ]
        df = BybitDataProvider._normalize(klines, "1h")
        assert list(df.columns) == COLUMNS
        assert len(df) == 2
        assert df.iloc[0]["close"] == 50200.0

    def test_close_time_calculated(self):
        klines = [["1700000000000", "50000", "50500", "49800", "50200", "100", "5000000"]]
        df = BybitDataProvider._normalize(klines, "1h")
        open_ms = 1700000000000
        expected_close_ms = open_ms + INTERVAL_MS["1h"]
        assert int(df.iloc[0]["close_time"].timestamp() * 1000) == expected_close_ms


class TestBybitIntervalMap:
    def test_all_common_intervals_mapped(self):
        for interval in ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]:
            assert interval in BYBIT_INTERVAL_MAP

    def test_hour_maps_to_60(self):
        assert BYBIT_INTERVAL_MAP["1h"] == "60"

    def test_day_maps_to_D(self):
        assert BYBIT_INTERVAL_MAP["1d"] == "D"
