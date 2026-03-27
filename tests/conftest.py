"""Shared test fixtures for ai-hedge-fund-crypto."""
import sys
import os
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.gateway.base_exchange_client import OrderResult, BalanceInfo
from src.risk.circuit_breaker import CircuitBreaker
from src.utils.constants import COLUMNS, NUMERIC_COLUMNS


@pytest.fixture
def sample_ohlcv_df():
    """Standard 5-row OHLCV DataFrame matching Binance/Bybit schema."""
    base_time = datetime(2025, 1, 1)
    rows = []
    for i in range(5):
        t = base_time + timedelta(hours=i)
        rows.append([
            int(t.timestamp() * 1000),   # open_time
            100.0 + i,                    # open
            102.0 + i,                    # high
            99.0 + i,                     # low
            101.0 + i,                    # close
            1000.0 + i * 100,             # volume
            int((t + timedelta(hours=1)).timestamp() * 1000),  # close_time
            50000.0 + i * 500,            # quote_volume
            100 + i,                      # count
            500.0 + i * 50,               # taker_buy_volume
            25000.0 + i * 250,            # taker_buy_quote_volume
            0,                            # ignore
        ])
    df = pd.DataFrame(rows, columns=COLUMNS)
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    return df


@pytest.fixture
def sample_portfolio():
    """Standard test portfolio with 100K USDT."""
    return {
        "cash": 100000,
        "margin_requirement": 0.0,
        "margin_used": 0.0,
        "positions": {
            "BTCUSDT": {"long": 0.0, "short": 0.0, "long_cost_basis": 0.0,
                        "short_cost_basis": 0.0, "short_margin_used": 0.0},
        },
        "realized_gains": {"BTCUSDT": {"long": 0.0, "short": 0.0}},
    }


@pytest.fixture
def circuit_breaker():
    """Circuit breaker with 5% max daily loss on 100K capital."""
    return CircuitBreaker(max_daily_loss_pct=5.0, initial_capital=100000)


@pytest.fixture
def filled_order_result():
    """A successful FILLED order result."""
    return OrderResult(
        order_id="TEST123", symbol="BTCUSDT", side="BUY",
        order_type="MARKET", quantity=0.01, filled_quantity=0.01,
        avg_price=50000.0, status="FILLED", fees=0.005,
        timestamp="1234567890", raw_response={},
    )


@pytest.fixture
def mock_exchange_client(filled_order_result):
    """Mock exchange client returning successful fills."""
    client = MagicMock()
    client.place_market_order.return_value = filled_order_result
    client.place_stop_loss.return_value = OrderResult(
        order_id="SL001", symbol="BTCUSDT", side="SELL",
        order_type="STOP_LOSS", quantity=0.01, filled_quantity=0,
        avg_price=0, status="NEW", fees=0, timestamp="", raw_response={},
    )
    client.place_take_profit.return_value = OrderResult(
        order_id="TP001", symbol="BTCUSDT", side="SELL",
        order_type="TAKE_PROFIT", quantity=0.01, filled_quantity=0,
        avg_price=0, status="NEW", fees=0, timestamp="", raw_response={},
    )
    client.get_balance.return_value = BalanceInfo(asset="USDT", free=10000.0, locked=0.0)
    client.get_symbol_info.return_value = {
        "parsed_filters": {
            "LOT_SIZE": {"stepSize": "0.00001", "minQty": "0.00001"},
            "PRICE_FILTER": {"tickSize": "0.01"},
        }
    }
    return client
