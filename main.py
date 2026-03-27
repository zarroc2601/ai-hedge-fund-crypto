import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
from src.utils import settings
from datetime import datetime
from src.agent import Agent
from src.backtest.backtester import Backtester

load_dotenv()

if __name__ == "__main__":

    if settings.mode == "backtest":
        backtester = Backtester(
            primary_interval=settings.primary_interval,
            intervals=settings.signals.intervals,
            tickers=settings.signals.tickers,
            start_date=settings.start_date,
            end_date=settings.end_date,
            initial_capital=settings.initial_cash,
            strategies=settings.signals.strategies,
            show_agent_graph=settings.show_agent_graph,
            show_reasoning=settings.show_reasoning,
            model_name=settings.model.name,
            model_provider=settings.model.provider,
            model_base_url=settings.model.base_url,
        )
        print("Starting backtest...")
        performance_metrics = backtester.run_backtest()
        performance_df = backtester.analyze_performance()

    else:
        # Create exchange client if execution is enabled
        exchange_client = None
        circuit_breaker = None

        if settings.execution.enabled:
            from src.gateway import create_exchange_client
            from src.risk import CircuitBreaker

            exchange_client = create_exchange_client(
                exchange=settings.execution.exchange,
                testnet=settings.execution.testnet,
            )
            circuit_breaker = CircuitBreaker(
                max_daily_loss_pct=settings.risk.max_daily_loss_pct,
                initial_capital=settings.initial_cash,
            )
            mode_label = "TESTNET" if settings.execution.testnet else "LIVE"
            print(f"🔗 Execution enabled: {settings.execution.exchange} ({mode_label})")
            print(f"🛡️ Risk: SL={settings.risk.stop_loss_pct}% / TP={settings.risk.take_profit_pct}% / Max daily loss={settings.risk.max_daily_loss_pct}%")
        else:
            print("📊 Signal-only mode (execution disabled)")

        portfolio = {
            "cash": settings.initial_cash,
            "margin_requirement": settings.margin_requirement,
            "margin_used": 0.0,
            "positions": {
                ticker: {
                    "long": 0.0,
                    "short": 0.0,
                    "long_cost_basis": 0.0,
                    "short_cost_basis": 0.0,
                    "short_margin_used": 0.0,
                }
                for ticker in settings.signals.tickers
            },
            "realized_gains": {
                ticker: {
                    "long": 0.0,
                    "short": 0.0,
                }
                for ticker in settings.signals.tickers
            },
        }

        agent = Agent(
            intervals=settings.signals.intervals,
            strategies=settings.signals.strategies,
            show_agent_graph=settings.show_agent_graph,
            exchange=settings.execution.exchange,
            exchange_client=exchange_client,
            min_confidence=settings.execution.min_confidence,
            max_order_value=settings.execution.max_order_value,
            circuit_breaker=circuit_breaker,
            stop_loss_pct=settings.risk.stop_loss_pct,
            take_profit_pct=settings.risk.take_profit_pct,
        )

        result = agent.run(
            primary_interval=settings.primary_interval,
            tickers=settings.signals.tickers,
            end_date=datetime.now(),
            portfolio=portfolio,
            show_reasoning=settings.show_reasoning,
            model_name=settings.model.name,
            model_provider=settings.model.provider,
            model_base_url=settings.model.base_url,
        )

        print("\n📋 Decisions:")
        print(result.get("decisions"))

        if result.get("execution_results"):
            print("\n⚡ Execution Results:")
            print(result.get("execution_results"))
