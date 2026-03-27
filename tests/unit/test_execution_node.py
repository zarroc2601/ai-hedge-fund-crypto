"""Tests for ExecutionNode — order placement, SL/TP, circuit breaker integration."""
import json
import pytest
from langchain_core.messages import HumanMessage
from src.graph.execution_node import ExecutionNode
from src.risk.circuit_breaker import CircuitBreaker
from src.gateway.base_exchange_client import OrderResult


def _make_state(decisions, show_reasoning=False):
    return {
        "messages": [HumanMessage(content=json.dumps(decisions))],
        "data": {"name": "test"},
        "metadata": {"show_reasoning": show_reasoning},
    }


class TestExecutionNodePassThrough:
    def test_disabled_when_no_client(self):
        node = ExecutionNode(exchange_client=None)
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 80}}))
        assert result["data"]["execution_results"]["status"] == "disabled"

    def test_skips_hold_action(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        result = node(_make_state({"BTCUSDT": {"action": "hold", "quantity": 0, "confidence": 90}}))
        assert result["data"]["execution_results"]["BTCUSDT"]["status"] == "skipped"
        mock_exchange_client.place_market_order.assert_not_called()

    def test_skips_low_confidence(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client, min_confidence=70)
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 50}}))
        assert result["data"]["execution_results"]["BTCUSDT"]["status"] == "skipped"
        assert "low_confidence" in result["data"]["execution_results"]["BTCUSDT"]["reason"]

    def test_skips_zero_quantity(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0, "confidence": 80}}))
        assert result["data"]["execution_results"]["BTCUSDT"]["status"] == "skipped"


class TestExecutionNodeOrders:
    def test_buy_places_market_order(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 80}}))
        mock_exchange_client.place_market_order.assert_called_with(symbol="BTCUSDT", side="BUY", quantity=0.01)
        assert result["data"]["execution_results"]["BTCUSDT"]["status"] == "FILLED"

    def test_sell_places_sell_order(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        result = node(_make_state({"BTCUSDT": {"action": "sell", "quantity": 0.01, "confidence": 80}}))
        mock_exchange_client.place_market_order.assert_called_with(symbol="BTCUSDT", side="SELL", quantity=0.01)

    def test_short_maps_to_sell(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        node(_make_state({"BTCUSDT": {"action": "short", "quantity": 0.01, "confidence": 80}}))
        mock_exchange_client.place_market_order.assert_called_with(symbol="BTCUSDT", side="SELL", quantity=0.01)

    def test_cover_maps_to_buy(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        node(_make_state({"BTCUSDT": {"action": "cover", "quantity": 0.01, "confidence": 80}}))
        mock_exchange_client.place_market_order.assert_called_with(symbol="BTCUSDT", side="BUY", quantity=0.01)

    def test_multiple_tickers(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client)
        decisions = {
            "BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 80},
            "ETHUSDT": {"action": "sell", "quantity": 0.5, "confidence": 75},
        }
        result = node(_make_state(decisions))
        assert mock_exchange_client.place_market_order.call_count == 2


class TestExecutionNodeSLTP:
    def test_buy_places_sl_tp(self, mock_exchange_client):
        node = ExecutionNode(
            exchange_client=mock_exchange_client,
            stop_loss_pct=2.0, take_profit_pct=5.0,
        )
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 80}}))
        prot = result["data"]["execution_results"]["BTCUSDT"]["protective_orders"]
        assert "stop_loss" in prot
        assert "take_profit" in prot
        # SL should be below entry, TP above
        assert prot["stop_loss"]["price"] < 50000.0
        assert prot["take_profit"]["price"] > 50000.0

    def test_no_sl_tp_when_not_configured(self, mock_exchange_client):
        node = ExecutionNode(exchange_client=mock_exchange_client, stop_loss_pct=0, take_profit_pct=0)
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 80}}))
        prot = result["data"]["execution_results"]["BTCUSDT"].get("protective_orders", {})
        assert prot.get("status") == "no_sl_tp_configured" or "stop_loss" not in prot

    def test_sell_no_sl_tp(self, mock_exchange_client):
        """Closing positions (sell/cover) shouldn't place SL/TP."""
        node = ExecutionNode(exchange_client=mock_exchange_client, stop_loss_pct=2.0, take_profit_pct=5.0)
        result = node(_make_state({"BTCUSDT": {"action": "sell", "quantity": 0.01, "confidence": 80}}))
        assert "protective_orders" not in result["data"]["execution_results"]["BTCUSDT"]


class TestExecutionNodeCircuitBreaker:
    def test_halted_skips_all_trades(self, mock_exchange_client):
        cb = CircuitBreaker(max_daily_loss_pct=5.0, initial_capital=100000)
        cb.record_trade(-6000)  # Trigger halt
        node = ExecutionNode(exchange_client=mock_exchange_client, circuit_breaker=cb)
        result = node(_make_state({"BTCUSDT": {"action": "buy", "quantity": 0.01, "confidence": 90}}))
        assert result["data"]["execution_results"]["status"] == "halted"
        mock_exchange_client.place_market_order.assert_not_called()
