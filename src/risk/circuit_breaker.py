"""Circuit breaker — halts trading when daily realized loss exceeds threshold."""
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Tracks daily realized losses and halts trading when threshold is breached.

    State is in-memory only — resets on restart (safer default).
    Auto-resets at midnight UTC each day.
    """

    def __init__(self, max_daily_loss_pct: float, initial_capital: float):
        self.max_daily_loss = initial_capital * (max_daily_loss_pct / 100)
        self.daily_realized_loss = 0.0
        self.is_halted = False
        self.halt_reason = ""
        self.reset_date = date.today()
        logger.info(f"CircuitBreaker initialized: max daily loss ${self.max_daily_loss:.2f}")

    def record_trade(self, pnl: float) -> None:
        """Record a trade's PnL. Negative PnL accumulates toward daily limit."""
        self._check_reset()
        if pnl < 0:
            self.daily_realized_loss += abs(pnl)
            logger.info(f"CircuitBreaker: loss ${abs(pnl):.2f}, daily total ${self.daily_realized_loss:.2f}")

        if self.daily_realized_loss >= self.max_daily_loss:
            self.is_halted = True
            self.halt_reason = (
                f"Daily loss ${self.daily_realized_loss:.2f} >= limit ${self.max_daily_loss:.2f}"
            )
            logger.warning(f"🛑 CIRCUIT BREAKER TRIGGERED: {self.halt_reason}")

    def can_trade(self) -> tuple:
        """Check if trading is allowed. Returns (allowed: bool, reason: str)."""
        self._check_reset()
        if self.is_halted:
            return False, self.halt_reason
        return True, ""

    def _check_reset(self) -> None:
        """Reset daily counters if a new day has started."""
        today = date.today()
        if today > self.reset_date:
            self.daily_realized_loss = 0.0
            self.is_halted = False
            self.halt_reason = ""
            self.reset_date = today
            logger.info(f"CircuitBreaker reset for {today}")
