from typing import List, Dict, Optional
from langchain_core.messages import HumanMessage
from datetime import datetime
from utils import Interval, save_graph_as_png, parse_str_to_json
from src.gateway.base_exchange_client import BaseExchangeClient
from src.risk.circuit_breaker import CircuitBreaker
from .workflow import Workflow


class Agent:

    def __init__(
        self,
        intervals: List[Interval],
        strategies: List[str],
        show_agent_graph: bool = True,
        exchange: str = "binance",
        exchange_client: Optional[BaseExchangeClient] = None,
        min_confidence: int = 50,
        max_order_value: float = 1000.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
        stop_loss_pct: float = 0.0,
        take_profit_pct: float = 0.0,
    ):
        workflow = Workflow.create_workflow(
            intervals=intervals,
            strategies=strategies,
            exchange=exchange,
            exchange_client=exchange_client,
            min_confidence=min_confidence,
            max_order_value=max_order_value,
            circuit_breaker=circuit_breaker,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        self.intervals = intervals
        self.strategies = strategies
        self.agent = workflow.compile()
        if show_agent_graph:
            file_path = ""
            for strategy_name in strategies:
                file_path += strategy_name + "_"
                file_path += "graph.png"
            save_graph_as_png(self.agent, file_path)

    def run(
            self,
            primary_interval: Interval,
            tickers: List[str],
            end_date: datetime,
            portfolio: Dict,
            show_reasoning: bool = False,
            model_name: str = "gpt-4o",
            model_provider: str = "openai",
            model_base_url: Optional[str] = None
    ):
        final_state = self.agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "primary_interval": primary_interval,
                    "intervals": self.intervals,
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                    "model_base_url": model_base_url,
                },
            },
        )
        return {
            "decisions": parse_str_to_json(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
            "execution_results": final_state["data"].get("execution_results"),
        }
