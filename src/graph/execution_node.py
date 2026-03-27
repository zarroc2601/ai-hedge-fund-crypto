"""Execution node — places real orders on exchange based on portfolio decisions."""
import json
import logging
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage

from .base_node import BaseNode, AgentState
from .state import show_agent_reasoning
from src.gateway.base_exchange_client import BaseExchangeClient
from src.risk.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Map LLM actions to exchange order sides
ACTION_SIDE_MAP = {
    "buy": "BUY",
    "cover": "BUY",   # Covering short = buying back
    "sell": "SELL",
    "short": "SELL",   # Shorting = selling
}

# Actions that open new positions (need SL/TP protection)
OPENING_ACTIONS = {"buy", "short"}


class ExecutionNode(BaseNode):
    """DAG node that executes trading decisions on a real exchange.

    When no exchange_client is provided (backtest mode or execution disabled),
    this node passes through without placing orders.
    """

    def __init__(
        self,
        exchange_client: Optional[BaseExchangeClient] = None,
        min_confidence: int = 50,
        max_order_value: float = 1000.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
        stop_loss_pct: float = 0.0,
        take_profit_pct: float = 0.0,
    ):
        self.client = exchange_client
        self.min_confidence = min_confidence
        self.max_order_value = max_order_value
        self.circuit_breaker = circuit_breaker
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        data = state.get("data", {})
        data["name"] = "ExecutionNode"

        # Pass through if no client (backtest mode or execution disabled)
        if not self.client:
            data["execution_results"] = {"status": "disabled"}
            return {"messages": state["messages"], "data": data}

        # Check circuit breaker before any trading
        if self.circuit_breaker:
            can_trade, reason = self.circuit_breaker.can_trade()
            if not can_trade:
                logger.warning(f"🛑 Trading halted: {reason}")
                data["execution_results"] = {"status": "halted", "reason": reason}
                return {"messages": state["messages"], "data": data}

        # Parse portfolio management decisions from last message
        last_message = state["messages"][-1].content
        try:
            decisions = json.loads(last_message) if isinstance(last_message, str) else last_message
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse decisions from portfolio management")
            data["execution_results"] = {"status": "parse_error"}
            return {"messages": state["messages"], "data": data}

        execution_results = {}

        for ticker, decision in decisions.items():
            action = decision.get("action", "hold").lower()
            quantity = float(decision.get("quantity", 0))
            confidence = float(decision.get("confidence", 0))

            # Skip hold or zero-quantity decisions
            if action == "hold" or quantity <= 0:
                execution_results[ticker] = {"status": "skipped", "reason": "hold_or_zero"}
                continue

            # Skip low-confidence decisions
            if confidence < self.min_confidence:
                execution_results[ticker] = {"status": "skipped", "reason": f"low_confidence_{confidence}"}
                continue

            # Map action to exchange side
            side = ACTION_SIDE_MAP.get(action)
            if not side:
                execution_results[ticker] = {"status": "skipped", "reason": f"unknown_action_{action}"}
                continue

            # Cap order value (C1 fix: enforce max_order_value)
            if self.max_order_value > 0:
                # Estimate order value from risk data or last known price
                risk_data = data.get("analyst_signals", {}).get("risk_management_agent", {}).get(ticker, {})
                price_est = risk_data.get("current_price", 0)
                if price_est > 0:
                    max_qty = self.max_order_value / price_est
                    if quantity > max_qty:
                        logger.warning(f"{ticker}: capping qty {quantity} → {max_qty:.6f} (max_order_value=${self.max_order_value})")
                        quantity = max_qty

            # Place market order
            result = self.client.place_market_order(symbol=ticker, side=side, quantity=quantity)
            exec_entry = {
                "status": result.status,
                "action": action,
                "side": side,
                "requested_qty": quantity,
                "filled_qty": result.filled_quantity,
                "avg_price": result.avg_price,
                "fees": result.fees,
                "order_id": result.order_id,
            }

            # Place SL/TP protection for opening positions
            if result.status == "FILLED" and action in OPENING_ACTIONS:
                sl_tp_result = self._place_protective_orders(
                    ticker, action, result.filled_quantity, result.avg_price,
                )
                exec_entry["protective_orders"] = sl_tp_result

            # Record trade PnL in circuit breaker (C2 fix: wire record_trade)
            if result.status == "FILLED" and self.circuit_breaker:
                # For closing positions (sell/cover), estimate PnL from fees as proxy
                # Real PnL tracking requires position cost basis — simplified: record fees as loss
                self.circuit_breaker.record_trade(-result.fees)

            status_icon = "✅" if result.status == "FILLED" else "❌"
            logger.info(
                f"{status_icon} {ticker}: {action} {result.filled_quantity} @ {result.avg_price:.2f} "
                f"(fees: {result.fees:.4f}, order: {result.order_id})"
            )

            execution_results[ticker] = exec_entry

        data["execution_results"] = execution_results

        if state["metadata"].get("show_reasoning"):
            show_agent_reasoning(execution_results, "Execution Engine")

        message = HumanMessage(
            content=json.dumps(execution_results),
            name="execution_node",
        )

        return {"messages": [message], "data": data}

    def _place_protective_orders(
        self, symbol: str, action: str, quantity: float, entry_price: float,
    ) -> dict:
        """Place SL/TP (OCO) orders to protect an opened position."""
        if self.stop_loss_pct <= 0 and self.take_profit_pct <= 0:
            return {"status": "no_sl_tp_configured"}

        if action == "buy":
            # Long position: SL below, TP above, close side = SELL
            close_side = "SELL"
            sl_price = entry_price * (1 - self.stop_loss_pct / 100)
            tp_price = entry_price * (1 + self.take_profit_pct / 100)
        else:
            # Short position: SL above, TP below, close side = BUY
            close_side = "BUY"
            sl_price = entry_price * (1 + self.stop_loss_pct / 100)
            tp_price = entry_price * (1 - self.take_profit_pct / 100)

        # Place separate SL + TP orders (more reliable across exchange API versions)
        result = {}

        # Place SL separately
        if self.stop_loss_pct > 0:
            sl_result = self.client.place_stop_loss(
                symbol=symbol, side=close_side, quantity=quantity, stop_price=sl_price,
            )
            result["stop_loss"] = {"price": sl_price, "status": sl_result.status}
            logger.info(f"🛡️ {symbol}: SL@{sl_price:.2f} — {sl_result.status}")

        # Place TP separately
        if self.take_profit_pct > 0:
            tp_result = self.client.place_take_profit(
                symbol=symbol, side=close_side, quantity=quantity, price=tp_price,
            )
            result["take_profit"] = {"price": tp_price, "status": tp_result.status}
            logger.info(f"🎯 {symbol}: TP@{tp_price:.2f} — {tp_result.status}")

        # C4 fix: Alert on partial protection failure
        sl_ok = result.get("stop_loss", {}).get("status") not in ("REJECTED", None)
        tp_ok = result.get("take_profit", {}).get("status") not in ("REJECTED", None)
        if (self.stop_loss_pct > 0 and not sl_ok) or (self.take_profit_pct > 0 and not tp_ok):
            result["warning"] = "PARTIAL_PROTECTION"
            logger.warning(f"⚠️ {symbol}: Incomplete protection! SL={sl_ok}, TP={tp_ok}")

        return result
