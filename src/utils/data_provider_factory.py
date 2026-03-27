"""Factory to create data providers based on exchange config."""
from .base_data_provider import BaseDataProvider
from .binance_data_provider import BinanceDataProvider
from .bybit_data_provider import BybitDataProvider


def create_data_provider(exchange: str = "binance") -> BaseDataProvider:
    """Create a data provider for the specified exchange."""
    if exchange == "binance":
        return BinanceDataProvider()
    elif exchange == "bybit":
        return BybitDataProvider()
    raise ValueError(f"Unknown exchange: {exchange}. Supported: binance, bybit")
