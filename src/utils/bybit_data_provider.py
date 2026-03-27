"""Bybit data provider — fetches OHLCV data via pybit V5 unified API."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from pybit.unified_trading import HTTP

from .base_data_provider import BaseDataProvider
from .constants import COLUMNS, NUMERIC_COLUMNS, BYBIT_INTERVAL_MAP, INTERVAL_MS

logger = logging.getLogger(__name__)


class BybitDataProvider(BaseDataProvider):
    """Fetch OHLCV data from Bybit, normalized to match Binance DataFrame schema."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 testnet: bool = False):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key or "",
            api_secret=api_secret or "",
        )
        self.cache_dir = Path("./cache")
        self.cache_dir.mkdir(exist_ok=True)

    def get_historical_klines(
        self, symbol: str, timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        formatted = symbol.replace("/", "")
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        cache_file = self.cache_dir / f"bybit_{formatted}_{timeframe}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"
        if use_cache and cache_file.exists():
            return pd.read_csv(cache_file, parse_dates=["open_time", "close_time"])

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        try:
            all_klines = self._fetch_paginated(formatted, timeframe, start_ms, end_ms)
            df = self._normalize(all_klines, timeframe)
            if use_cache and not df.empty:
                df.to_csv(cache_file, index=False)
            return df
        except Exception as e:
            logger.error(f"Bybit historical fetch failed {formatted} {timeframe}: {e}")
            return pd.DataFrame()

    def get_history_klines_with_end_time(
        self, symbol: str, timeframe: str,
        end_time: datetime, limit: int = 500,
    ) -> pd.DataFrame:
        formatted = symbol.replace("/", "")
        bybit_interval = BYBIT_INTERVAL_MAP.get(timeframe, timeframe)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            resp = self.session.get_kline(
                category="spot",
                symbol=formatted,
                interval=bybit_interval,
                end=end_ms,
                limit=min(limit, 1000),
            )
            klines = resp["result"]["list"]
            klines.reverse()  # Bybit returns newest-first
            return self._normalize(klines, timeframe)
        except Exception as e:
            logger.error(f"Bybit klines fetch failed {formatted} {timeframe}: {e}")
            return pd.DataFrame()

    def get_latest_data(
        self, symbol: str, timeframe: str, limit: int = 1000,
    ) -> pd.DataFrame:
        formatted = symbol.replace("/", "")
        bybit_interval = BYBIT_INTERVAL_MAP.get(timeframe, timeframe)

        try:
            resp = self.session.get_kline(
                category="spot",
                symbol=formatted,
                interval=bybit_interval,
                limit=min(limit, 1000),
            )
            klines = resp["result"]["list"]
            klines.reverse()
            return self._normalize(klines, timeframe)
        except Exception as e:
            logger.error(f"Bybit latest data failed {formatted} {timeframe}: {e}")
            return pd.DataFrame()

    def _fetch_paginated(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list:
        """Paginate through Bybit's 1000-candle limit."""
        bybit_interval = BYBIT_INTERVAL_MAP.get(timeframe, timeframe)
        all_klines = []
        cursor_end = end_ms

        while cursor_end > start_ms:
            resp = self.session.get_kline(
                category="spot", symbol=symbol,
                interval=bybit_interval, end=cursor_end, limit=1000,
            )
            klines = resp["result"]["list"]
            if not klines:
                break
            klines.reverse()
            # Filter klines within start_ms
            klines = [k for k in klines if int(k[0]) >= start_ms]
            all_klines = klines + all_klines
            # Move cursor before oldest candle
            cursor_end = int(klines[0][0]) - 1

        return all_klines

    @staticmethod
    def _normalize(klines: list, timeframe: str) -> pd.DataFrame:
        """Normalize Bybit kline data to match Binance COLUMNS schema."""
        if not klines:
            return pd.DataFrame()

        # Bybit kline format: [startTime, open, high, low, close, volume, turnover]
        rows = []
        interval_ms = INTERVAL_MS.get(timeframe, 60000)
        for k in klines:
            open_time = int(k[0])
            rows.append([
                open_time,           # open_time
                k[1],                # open
                k[2],                # high
                k[3],                # low
                k[4],                # close
                k[5],                # volume
                open_time + interval_ms,  # close_time
                k[6] if len(k) > 6 else 0,  # quote_volume (turnover)
                0,                   # count (not available)
                0,                   # taker_buy_volume
                0,                   # taker_buy_quote_volume
                0,                   # ignore
            ])

        df = pd.DataFrame(rows, columns=COLUMNS)
        for col in NUMERIC_COLUMNS:
            df[col] = pd.to_numeric(df[col])
        df["open_time"] = pd.to_datetime(df["open_time"].astype(int), unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"].astype(int), unit="ms")
        return df
