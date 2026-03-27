"""Tests for circuit breaker — daily loss tracking and trading halt."""
from datetime import date, timedelta


class TestCircuitBreaker:
    def test_allows_trading_initially(self, circuit_breaker):
        can, reason = circuit_breaker.can_trade()
        assert can is True
        assert reason == ""

    def test_small_loss_still_allows_trading(self, circuit_breaker):
        circuit_breaker.record_trade(-2000)  # 2% of 100K < 5% threshold
        can, _ = circuit_breaker.can_trade()
        assert can is True

    def test_halts_after_exceeding_threshold(self, circuit_breaker):
        circuit_breaker.record_trade(-3000)
        circuit_breaker.record_trade(-2500)  # total 5500 > 5000 limit
        can, reason = circuit_breaker.can_trade()
        assert can is False
        assert "5500" in reason

    def test_profitable_trades_dont_reduce_loss(self, circuit_breaker):
        circuit_breaker.record_trade(-4000)
        circuit_breaker.record_trade(2000)   # profit doesn't offset
        assert circuit_breaker.daily_realized_loss == 4000.0

    def test_resets_next_day(self, circuit_breaker):
        circuit_breaker.record_trade(-6000)
        assert circuit_breaker.can_trade()[0] is False
        # Simulate day change
        circuit_breaker.reset_date = date.today() - timedelta(days=1)
        can, _ = circuit_breaker.can_trade()
        assert can is True
        assert circuit_breaker.daily_realized_loss == 0.0

    def test_exact_threshold_triggers_halt(self, circuit_breaker):
        circuit_breaker.record_trade(-5000)  # exactly at limit
        can, _ = circuit_breaker.can_trade()
        assert can is False
