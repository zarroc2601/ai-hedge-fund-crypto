"""Data fetching node — retrieves OHLCV data from the configured exchange."""
from datetime import datetime, timedelta
from typing import Dict, Any

from src.utils import Interval
from src.utils.data_provider_factory import create_data_provider
from .base_node import BaseNode, AgentState


class DataNode(BaseNode):
    def __init__(self, interval: Interval = Interval.DAY_1, exchange: str = "binance"):
        self.interval = interval
        self.data_provider = create_data_provider(exchange)

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        data = state.get('data', {})
        data['name'] = "DataNode"
        timeframe: str = self.interval.value
        tickers = data.get('tickers', [])
        end_time = data.get('end_date', datetime.now()) + timedelta(milliseconds=500)

        for ticker in tickers:
            df = self.data_provider.get_history_klines_with_end_time(
                symbol=ticker, timeframe=timeframe, end_time=end_time,
            )
            if df is not None and not df.empty:
                data[f"{ticker}_{timeframe}"] = df
            else:
                print(f"[Warning] No data returned for {ticker} at interval {timeframe}")

        return state
