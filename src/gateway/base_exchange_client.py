"""Abstract base class for exchange clients — defines the interface for all exchanges."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OrderResult:
    """Result of an order placement attempt."""
    order_id: str
    symbol: str
    side: str           # BUY | SELL
    order_type: str     # MARKET | LIMIT
    quantity: float
    filled_quantity: float
    avg_price: float
    status: str         # FILLED | PARTIALLY_FILLED | REJECTED | CANCELLED
    fees: float
    timestamp: str
    raw_response: dict = field(default_factory=dict)


@dataclass
class BalanceInfo:
    """Balance information for a single asset."""
    asset: str
    free: float
    locked: float


class BaseExchangeClient(ABC):
    """Interface all exchange clients must implement."""

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        """Place a market order. Side = 'BUY' or 'SELL'."""

    @abstractmethod
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        """Place a limit order."""

    @abstractmethod
    def get_balance(self, asset: str) -> BalanceInfo:
        """Get balance for a specific asset (e.g. 'USDT')."""

    @abstractmethod
    def get_all_balances(self) -> List[BalanceInfo]:
        """Get all non-zero balances."""

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders, optionally filtered by symbol."""

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order. Returns True if successful."""

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> dict:
        """Get trading rules for a symbol (lot size, min notional, etc.)."""

    @abstractmethod
    def place_oco_order(
        self, symbol: str, side: str, quantity: float,
        price: float, stop_price: float, stop_limit_price: float,
    ) -> OrderResult:
        """Place OCO order (take-profit limit + stop-loss). One cancels the other."""

    @abstractmethod
    def place_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> OrderResult:
        """Place a stop-loss limit order."""

    @abstractmethod
    def place_take_profit(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        """Place a take-profit limit order."""
