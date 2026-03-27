"""RSI Strategy — standalone RSI-based signal generation node."""
from typing import Dict, Any
import json
import pandas as pd
from langchain_core.messages import HumanMessage
from src.graph import AgentState, BaseNode, show_agent_reasoning
from indicators import calculate_rsi, normalize_pandas


class RSIStrategy(BaseNode):
    """Generate buy/sell signals based on RSI overbought/oversold levels."""

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        data = state.get("data", {})
        data["name"] = "RSIStrategy"
        tickers = data.get("tickers", [])
        intervals = data.get("intervals", [])

        technical_analysis: Dict[str, Dict] = {}

        for ticker in tickers:
            technical_analysis[ticker] = {}
            for interval in intervals:
                df = data.get(f"{ticker}_{interval.value}", pd.DataFrame())
                if df.empty or "close" not in df.columns:
                    continue

                rsi_series = calculate_rsi(df, period=14)
                if rsi_series.empty:
                    continue

                rsi_value = float(rsi_series.iloc[-1])

                # Determine signal from RSI thresholds
                if rsi_value < 30:
                    signal, confidence = "bullish", min(90, int(80 + (30 - rsi_value)))
                elif rsi_value > 70:
                    signal, confidence = "bearish", min(90, int(80 + (rsi_value - 70)))
                elif rsi_value < 40:
                    signal, confidence = "bullish", 60
                elif rsi_value > 60:
                    signal, confidence = "bearish", 60
                else:
                    signal, confidence = "neutral", 50

                technical_analysis[ticker][interval.value] = {
                    "signal": signal,
                    "confidence": confidence,
                    "strategy_signals": {
                        "rsi": {
                            "signal": signal,
                            "confidence": confidence,
                            "metrics": {"rsi": rsi_value, "period": 14},
                        }
                    },
                }

        message = HumanMessage(
            content=json.dumps(technical_analysis),
            name="rsi_agent",
        )

        if state["metadata"]["show_reasoning"]:
            show_agent_reasoning(technical_analysis, "RSI Analyst")

        state["data"]["analyst_signals"]["rsi_agent"] = technical_analysis

        return {"messages": [message], "data": data}
