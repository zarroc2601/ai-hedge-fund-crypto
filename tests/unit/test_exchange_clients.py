"""Tests for exchange client order parsing, rounding, and factory."""
import pytest
from unittest.mock import MagicMock, patch
from src.gateway.binance_exchange_client import BinanceExchangeClient
from src.gateway.bybit_exchange_client import BybitExchangeClient
from src.gateway.exchange_factory import create_exchange_client


class TestBinanceQuantityRounding:
    def setup_method(self):
        """Create client with mocked Binance API."""
        with patch.object(BinanceExchangeClient, "__init__", lambda self, **kw: None):
            self.client = BinanceExchangeClient()
            self.client.testnet = True
            self.client.client = MagicMock()
            self.client._symbol_info_cache = {
                "BTCUSDT": {
                    "parsed_filters": {
                        "LOT_SIZE": {"stepSize": "0.00001", "minQty": "0.00001"},
                        "PRICE_FILTER": {"tickSize": "0.01"},
                    }
                }
            }

    def test_rounds_to_step_size(self):
        assert self.client._round_quantity("BTCUSDT", 0.123456789) == 0.12345

    def test_returns_zero_below_min(self):
        assert self.client._round_quantity("BTCUSDT", 0.000001) == 0.0

    def test_rounds_price_to_tick(self):
        assert self.client._round_price("BTCUSDT", 66123.456) == 66123.45


class TestBinanceOrderParsing:
    def setup_method(self):
        with patch.object(BinanceExchangeClient, "__init__", lambda self, **kw: None):
            self.client = BinanceExchangeClient()
            self.client.testnet = True
            self.client.client = MagicMock()
            self.client._symbol_info_cache = {}

    def test_parse_filled_order(self):
        raw = {
            "orderId": 12345,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "origQty": "0.01",
            "executedQty": "0.01",
            "status": "FILLED",
            "transactTime": 1700000000000,
            "fills": [
                {"qty": "0.005", "price": "66000.00", "commission": "0.01"},
                {"qty": "0.005", "price": "66100.00", "commission": "0.01"},
            ],
        }
        result = self.client._parse_order_response(raw)
        assert result.order_id == "12345"
        assert result.filled_quantity == 0.01
        assert result.avg_price == pytest.approx(66050.0, rel=0.01)
        assert result.fees == 0.02
        assert result.status == "FILLED"

    def test_rejected_result(self):
        result = BinanceExchangeClient._rejected_result("BTCUSDT", "BUY", "MARKET", 0.01, "Insufficient balance")
        assert result.status == "REJECTED"
        assert result.filled_quantity == 0.0
        assert "Insufficient balance" in result.raw_response["error"]


class TestBybitOrderParsing:
    def setup_method(self):
        with patch.object(BybitExchangeClient, "__init__", lambda self, **kw: None):
            self.client = BybitExchangeClient()
            self.client.testnet = True
            self.client.session = MagicMock()

    def test_parse_successful_order(self):
        resp = {"retCode": 0, "result": {"orderId": "BY001", "createdTime": "1700000000"}}
        result = self.client._parse_order_response(resp, "BTCUSDT", "BUY", "MARKET", 0.01)
        assert result.order_id == "BY001"
        assert result.status == "FILLED"

    def test_parse_failed_order(self):
        resp = {"retCode": 10001, "retMsg": "Insufficient balance", "result": {}}
        result = self.client._parse_order_response(resp, "BTCUSDT", "BUY", "MARKET", 0.01)
        assert result.status == "REJECTED"

    def test_oco_not_supported(self):
        result = self.client.place_oco_order("BTCUSDT", "SELL", 0.01, 70000, 64000, 63900)
        assert result.status == "REJECTED"
        assert "OCO" in result.raw_response["error"]


class TestExchangeFactory:
    @patch.dict("os.environ", {"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "secret"})
    @patch("src.gateway.exchange_factory.BinanceExchangeClient")
    def test_creates_binance(self, mock_cls):
        create_exchange_client("binance", testnet=True)
        mock_cls.assert_called_once_with(api_key="key", api_secret="secret", testnet=True)

    @patch.dict("os.environ", {"BYBIT_API_KEY": "key", "BYBIT_API_SECRET": "secret"})
    @patch("src.gateway.exchange_factory.BybitExchangeClient")
    def test_creates_bybit(self, mock_cls):
        create_exchange_client("bybit", testnet=True)
        mock_cls.assert_called_once_with(api_key="key", api_secret="secret", testnet=True)

    def test_unknown_exchange_raises(self):
        with pytest.raises(ValueError, match="Unknown exchange"):
            create_exchange_client("kraken")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_binance_keys_raises(self):
        with pytest.raises(ValueError, match="BINANCE_API_KEY"):
            create_exchange_client("binance")
