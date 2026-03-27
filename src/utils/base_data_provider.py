"""Abstract base class for exchange data providers."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd


class BaseDataProvider(ABC):
    """Interface for fetching OHLCV data from exchanges."""

    @abstractmethod
    def get_historical_klines(
        self, symbol: str, timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get historical klines with date range."""

    @abstractmethod
    def get_history_klines_with_end_time(
        self, symbol: str, timeframe: str,
        end_time: datetime, limit: int = 500,
    ) -> pd.DataFrame:
        """Get klines up to end_time with a limit."""

    @abstractmethod
    def get_latest_data(
        self, symbol: str, timeframe: str, limit: int = 1000,
    ) -> pd.DataFrame:
        """Get the latest candlestick data."""

    def get_multiple_timeframes_with_end_time(
        self, symbol: str, timeframes: List[str],
        end_time: str, limit: int = 500,
    ) -> Dict[str, pd.DataFrame]:
        """Get data for multiple timeframes. Default loops over single-timeframe method."""
        result = {}
        for tf in timeframes:
            result[tf] = self.get_history_klines_with_end_time(
                symbol=symbol, timeframe=tf, end_time=end_time, limit=limit,
            )
        return result
