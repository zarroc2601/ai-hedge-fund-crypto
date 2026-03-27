"""Bybit exchange client — implements BaseExchangeClient using pybit V5 unified API."""
import logging
from typing import List, Optional

from pybit.unified_trading import HTTP

from .base_exchange_client import BaseExchangeClient, OrderResult, BalanceInfo

logger = logging.getLogger(__name__)


class BybitExchangeClient(BaseExchangeClient):
    """Trading client for Bybit spot market via V5 API."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.testnet = testnet
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )
        env_label = "TESTNET" if testnet else "PRODUCTION"
        logger.info(f"BybitExchangeClient initialized ({env_label})")

    def place_market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        bybit_side = "Buy" if side == "BUY" else "Sell"
        try:
            resp = self.session.place_order(
                category="spot",
                symbol=symbol,
                side=bybit_side,
                orderType="Market",
                qty=str(quantity),
            )
            return self._parse_order_response(resp, symbol, side, "MARKET", quantity)
        except Exception as e:
            logger.error(f"Bybit market order failed {symbol} {side} {quantity}: {e}")
            return self._rejected_result(symbol, side, "MARKET", quantity, str(e))

    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        bybit_side = "Buy" if side == "BUY" else "Sell"
        try:
            resp = self.session.place_order(
                category="spot",
                symbol=symbol,
                side=bybit_side,
                orderType="Limit",
                qty=str(quantity),
                price=str(price),
                timeInForce="GTC",
            )
            return self._parse_order_response(resp, symbol, side, "LIMIT", quantity)
        except Exception as e:
            logger.error(f"Bybit limit order failed {symbol}: {e}")
            return self._rejected_result(symbol, side, "LIMIT", quantity, str(e))

    def get_balance(self, asset: str) -> BalanceInfo:
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED", coin=asset)
            coins = resp.get("result", {}).get("list", [{}])[0].get("coin", [])
            for c in coins:
                if c.get("coin") == asset:
                    return BalanceInfo(
                        asset=asset,
                        free=float(c.get("availableToWithdraw", 0)),
                        locked=float(c.get("locked", 0)),
                    )
            return BalanceInfo(asset=asset, free=0.0, locked=0.0)
        except Exception as e:
            logger.error(f"Bybit get_balance failed {asset}: {e}")
            return BalanceInfo(asset=asset, free=0.0, locked=0.0)

    def get_all_balances(self) -> List[BalanceInfo]:
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED")
            coins = resp.get("result", {}).get("list", [{}])[0].get("coin", [])
            return [
                BalanceInfo(
                    asset=c["coin"],
                    free=float(c.get("availableToWithdraw", 0)),
                    locked=float(c.get("locked", 0)),
                )
                for c in coins
                if float(c.get("walletBalance", 0)) > 0
            ]
        except Exception as e:
            logger.error(f"Bybit get_all_balances failed: {e}")
            return []

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        try:
            params = {"category": "spot"}
            if symbol:
                params["symbol"] = symbol
            resp = self.session.get_open_orders(**params)
            return resp.get("result", {}).get("list", [])
        except Exception as e:
            logger.error(f"Bybit get_open_orders failed: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            self.session.cancel_order(category="spot", symbol=symbol, orderId=order_id)
            return True
        except Exception as e:
            logger.error(f"Bybit cancel_order failed {order_id}: {e}")
            return False

    def get_symbol_info(self, symbol: str) -> dict:
        try:
            resp = self.session.get_instruments_info(category="spot", symbol=symbol)
            items = resp.get("result", {}).get("list", [])
            return items[0] if items else {}
        except Exception as e:
            logger.error(f"Bybit get_symbol_info failed {symbol}: {e}")
            return {}

    def place_oco_order(
        self, symbol: str, side: str, quantity: float,
        price: float, stop_price: float, stop_limit_price: float,
    ) -> OrderResult:
        # Bybit doesn't have native OCO — return rejected so ExecutionNode falls back to separate orders
        return self._rejected_result(symbol, side, "OCO", quantity, "Bybit does not support OCO orders")

    def place_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> OrderResult:
        """Place conditional market order triggered at stop_price."""
        bybit_side = "Buy" if side == "BUY" else "Sell"
        # triggerDirection: 1 = rises above, 2 = falls below
        trigger_dir = 2 if side == "SELL" else 1
        try:
            resp = self.session.place_order(
                category="spot",
                symbol=symbol,
                side=bybit_side,
                orderType="Market",
                qty=str(quantity),
                triggerPrice=str(stop_price),
                triggerDirection=trigger_dir,
            )
            return self._parse_order_response(resp, symbol, side, "STOP_LOSS", quantity)
        except Exception as e:
            logger.error(f"Bybit stop-loss failed {symbol}: {e}")
            return self._rejected_result(symbol, side, "STOP_LOSS", quantity, str(e))

    def place_take_profit(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        """Place conditional limit order triggered at price."""
        bybit_side = "Buy" if side == "BUY" else "Sell"
        trigger_dir = 1 if side == "SELL" else 2
        try:
            resp = self.session.place_order(
                category="spot",
                symbol=symbol,
                side=bybit_side,
                orderType="Limit",
                qty=str(quantity),
                price=str(price),
                triggerPrice=str(price),
                triggerDirection=trigger_dir,
                timeInForce="GTC",
            )
            return self._parse_order_response(resp, symbol, side, "TAKE_PROFIT", quantity)
        except Exception as e:
            logger.error(f"Bybit take-profit failed {symbol}: {e}")
            return self._rejected_result(symbol, side, "TAKE_PROFIT", quantity, str(e))

    # --- Private helpers ---

    def _parse_order_response(self, resp: dict, symbol: str, side: str,
                              order_type: str, quantity: float) -> OrderResult:
        result = resp.get("result", {})
        ret_code = resp.get("retCode", -1)
        if ret_code != 0:
            return self._rejected_result(symbol, side, order_type, quantity, resp.get("retMsg", "Unknown error"))
        return OrderResult(
            order_id=result.get("orderId", ""),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            filled_quantity=quantity,  # Bybit doesn't return fill details in place_order
            avg_price=0.0,            # Need to query order details for actual fill price
            status="FILLED" if ret_code == 0 else "REJECTED",
            fees=0.0,
            timestamp=str(result.get("createdTime", "")),
            raw_response=resp,
        )

    @staticmethod
    def _rejected_result(symbol: str, side: str, order_type: str, quantity: float, reason: str) -> OrderResult:
        return OrderResult(
            order_id="", symbol=symbol, side=side, order_type=order_type,
            quantity=quantity, filled_quantity=0.0, avg_price=0.0,
            status="REJECTED", fees=0.0, timestamp="",
            raw_response={"error": reason},
        )
