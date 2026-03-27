"""Binance exchange client — implements BaseExchangeClient using python-binance."""
import math
import logging
from typing import List, Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from .base_exchange_client import BaseExchangeClient, OrderResult, BalanceInfo

logger = logging.getLogger(__name__)


class BinanceExchangeClient(BaseExchangeClient):
    """Real trading client for Binance spot market."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.testnet = testnet
        self.client = Client(api_key, api_secret, testnet=testnet)
        # Cache symbol info to avoid repeated API calls
        self._symbol_info_cache: dict = {}
        env_label = "TESTNET" if testnet else "PRODUCTION"
        logger.info(f"BinanceExchangeClient initialized ({env_label})")

    def place_market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        """Place market order with automatic quantity rounding."""
        rounded_qty = self._round_quantity(symbol, quantity)
        if rounded_qty <= 0:
            return self._rejected_result(symbol, side, "MARKET", quantity, "Quantity rounds to 0")

        try:
            order = self.client.create_order(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=rounded_qty,
            )
            return self._parse_order_response(order)
        except (BinanceAPIException, BinanceOrderException) as e:
            logger.error(f"Market order failed {symbol} {side} {rounded_qty}: {e}")
            return self._rejected_result(symbol, side, "MARKET", quantity, str(e))

    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        """Place limit order with automatic quantity and price rounding."""
        rounded_qty = self._round_quantity(symbol, quantity)
        rounded_price = self._round_price(symbol, price)
        if rounded_qty <= 0:
            return self._rejected_result(symbol, side, "LIMIT", quantity, "Quantity rounds to 0")

        try:
            order = self.client.create_order(
                symbol=symbol,
                side=side,
                type="LIMIT",
                timeInForce="GTC",
                quantity=rounded_qty,
                price=str(rounded_price),
            )
            return self._parse_order_response(order)
        except (BinanceAPIException, BinanceOrderException) as e:
            logger.error(f"Limit order failed {symbol} {side} {rounded_qty}@{rounded_price}: {e}")
            return self._rejected_result(symbol, side, "LIMIT", quantity, str(e))

    def get_balance(self, asset: str) -> BalanceInfo:
        """Get balance for a single asset."""
        try:
            info = self.client.get_asset_balance(asset=asset)
            if info:
                return BalanceInfo(
                    asset=info["asset"],
                    free=float(info["free"]),
                    locked=float(info["locked"]),
                )
            return BalanceInfo(asset=asset, free=0.0, locked=0.0)
        except BinanceAPIException as e:
            logger.error(f"Failed to get balance for {asset}: {e}")
            return BalanceInfo(asset=asset, free=0.0, locked=0.0)

    def get_all_balances(self) -> List[BalanceInfo]:
        """Get all non-zero balances."""
        try:
            account = self.client.get_account()
            return [
                BalanceInfo(asset=b["asset"], free=float(b["free"]), locked=float(b["locked"]))
                for b in account.get("balances", [])
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            ]
        except BinanceAPIException as e:
            logger.error(f"Failed to get all balances: {e}")
            return []

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders."""
        try:
            if symbol:
                return self.client.get_open_orders(symbol=symbol)
            return self.client.get_open_orders()
        except BinanceAPIException as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order by ID."""
        try:
            self.client.cancel_order(symbol=symbol, orderId=order_id)
            return True
        except BinanceAPIException as e:
            logger.error(f"Failed to cancel order {order_id} for {symbol}: {e}")
            return False

    def get_symbol_info(self, symbol: str) -> dict:
        """Get symbol trading rules with caching."""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]

        try:
            info = self.client.get_symbol_info(symbol)
            if info:
                # Parse filters into a convenient dict
                filters = {}
                for f in info.get("filters", []):
                    filters[f["filterType"]] = f
                info["parsed_filters"] = filters
                self._symbol_info_cache[symbol] = info
            return info or {}
        except BinanceAPIException as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
            return {}

    def place_oco_order(
        self, symbol: str, side: str, quantity: float,
        price: float, stop_price: float, stop_limit_price: float,
    ) -> OrderResult:
        """Place OCO order: take-profit limit + stop-loss stop-limit."""
        rounded_qty = self._round_quantity(symbol, quantity)
        rounded_price = self._round_price(symbol, price)
        rounded_stop = self._round_price(symbol, stop_price)
        rounded_stop_limit = self._round_price(symbol, stop_limit_price)
        if rounded_qty <= 0:
            return self._rejected_result(symbol, side, "OCO", quantity, "Quantity rounds to 0")

        try:
            order = self.client.create_oco_order(
                symbol=symbol,
                side=side,
                quantity=rounded_qty,
                price=str(rounded_price),
                stopPrice=str(rounded_stop),
                stopLimitPrice=str(rounded_stop_limit),
                stopLimitTimeInForce="GTC",
            )
            # OCO returns orderListId + list of orders
            orders = order.get("orderReports", order.get("orders", []))
            if orders:
                return self._parse_order_response(orders[0])
            return OrderResult(
                order_id=str(order.get("orderListId", "")),
                symbol=symbol, side=side, order_type="OCO",
                quantity=rounded_qty, filled_quantity=0, avg_price=0,
                status="NEW", fees=0, timestamp="", raw_response=order,
            )
        except (BinanceAPIException, BinanceOrderException) as e:
            logger.error(f"OCO order failed {symbol}: {e}")
            return self._rejected_result(symbol, side, "OCO", quantity, str(e))

    def place_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> OrderResult:
        """Place a stop-loss limit order (stop_price = trigger, limit slightly worse)."""
        rounded_qty = self._round_quantity(symbol, quantity)
        rounded_stop = self._round_price(symbol, stop_price)
        # Limit price slightly worse than stop to ensure fill
        slippage = 0.001  # 0.1%
        if side == "SELL":
            limit_price = self._round_price(symbol, stop_price * (1 - slippage))
        else:
            limit_price = self._round_price(symbol, stop_price * (1 + slippage))

        if rounded_qty <= 0:
            return self._rejected_result(symbol, side, "STOP_LOSS_LIMIT", quantity, "Quantity rounds to 0")

        try:
            order = self.client.create_order(
                symbol=symbol, side=side, type="STOP_LOSS_LIMIT",
                timeInForce="GTC", quantity=rounded_qty,
                price=str(limit_price), stopPrice=str(rounded_stop),
            )
            return self._parse_order_response(order)
        except (BinanceAPIException, BinanceOrderException) as e:
            logger.error(f"Stop-loss order failed {symbol}: {e}")
            return self._rejected_result(symbol, side, "STOP_LOSS_LIMIT", quantity, str(e))

    def place_take_profit(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        """Place a take-profit limit order."""
        rounded_qty = self._round_quantity(symbol, quantity)
        rounded_price = self._round_price(symbol, price)
        if rounded_qty <= 0:
            return self._rejected_result(symbol, side, "TAKE_PROFIT_LIMIT", quantity, "Quantity rounds to 0")

        try:
            order = self.client.create_order(
                symbol=symbol, side=side, type="TAKE_PROFIT_LIMIT",
                timeInForce="GTC", quantity=rounded_qty,
                price=str(rounded_price), stopPrice=str(rounded_price),
            )
            return self._parse_order_response(order)
        except (BinanceAPIException, BinanceOrderException) as e:
            logger.error(f"Take-profit order failed {symbol}: {e}")
            return self._rejected_result(symbol, side, "TAKE_PROFIT_LIMIT", quantity, str(e))

    # --- Private helpers ---

    def _round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to the symbol's LOT_SIZE step size."""
        info = self.get_symbol_info(symbol)
        filters = info.get("parsed_filters", {})
        lot_size = filters.get("LOT_SIZE", {})
        step_size = float(lot_size.get("stepSize", "0.00001"))
        min_qty = float(lot_size.get("minQty", "0.00001"))

        if step_size > 0:
            precision = max(0, int(round(-math.log10(step_size))))
            rounded = round(quantity - (quantity % step_size), precision)
        else:
            rounded = quantity

        return rounded if rounded >= min_qty else 0.0

    def _round_price(self, symbol: str, price: float) -> float:
        """Round price to the symbol's PRICE_FILTER tick size."""
        info = self.get_symbol_info(symbol)
        filters = info.get("parsed_filters", {})
        price_filter = filters.get("PRICE_FILTER", {})
        tick_size = float(price_filter.get("tickSize", "0.01"))

        if tick_size > 0:
            precision = max(0, int(round(-math.log10(tick_size))))
            return round(price - (price % tick_size), precision)
        return price

    def _parse_order_response(self, order: dict) -> OrderResult:
        """Parse Binance order response into OrderResult."""
        fills = order.get("fills", [])
        total_qty = sum(float(f["qty"]) for f in fills) if fills else float(order.get("executedQty", 0))
        total_cost = sum(float(f["qty"]) * float(f["price"]) for f in fills) if fills else 0.0
        total_fees = sum(float(f.get("commission", 0)) for f in fills) if fills else 0.0
        avg_price = total_cost / total_qty if total_qty > 0 else 0.0

        return OrderResult(
            order_id=str(order.get("orderId", "")),
            symbol=order.get("symbol", ""),
            side=order.get("side", ""),
            order_type=order.get("type", ""),
            quantity=float(order.get("origQty", 0)),
            filled_quantity=total_qty,
            avg_price=avg_price,
            status=order.get("status", "UNKNOWN"),
            fees=total_fees,
            timestamp=str(order.get("transactTime", "")),
            raw_response=order,
        )

    @staticmethod
    def _rejected_result(symbol: str, side: str, order_type: str, quantity: float, reason: str) -> OrderResult:
        """Create a rejected OrderResult."""
        return OrderResult(
            order_id="",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            filled_quantity=0.0,
            avg_price=0.0,
            status="REJECTED",
            fees=0.0,
            timestamp="",
            raw_response={"error": reason},
        )
