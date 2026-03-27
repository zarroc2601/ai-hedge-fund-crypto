"""Factory to create exchange clients from config settings."""
import os
import logging

from .base_exchange_client import BaseExchangeClient
from .binance_exchange_client import BinanceExchangeClient
from .bybit_exchange_client import BybitExchangeClient

logger = logging.getLogger(__name__)


def create_exchange_client(exchange: str, testnet: bool = True) -> BaseExchangeClient:
    """Create an exchange client based on config.

    Args:
        exchange: Exchange name ('binance' or 'bybit')
        testnet: Whether to use testnet/demo mode

    Returns:
        Configured exchange client
    """
    if exchange == "binance":
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET env vars required for execution")
        return BinanceExchangeClient(api_key=api_key, api_secret=api_secret, testnet=testnet)

    elif exchange == "bybit":
        api_key = os.getenv("BYBIT_API_KEY", "")
        api_secret = os.getenv("BYBIT_API_SECRET", "")
        if not api_key or not api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET env vars required for execution")
        return BybitExchangeClient(api_key=api_key, api_secret=api_secret, testnet=testnet)

    else:
        raise ValueError(f"Unknown exchange: {exchange}. Supported: binance, bybit")
