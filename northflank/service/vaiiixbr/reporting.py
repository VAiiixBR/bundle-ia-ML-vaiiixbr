from __future__ import annotations

import math
import pandas as pd


def build_backtest_report(trades_df: pd.DataFrame, equity_df: pd.DataFrame, initial_capital: float) -> dict[str, float]:
    if trades_df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "net_profit": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "final_equity": initial_capital,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] <= 0]
    gross_profit = float(wins["pnl"].sum())
    gross_loss = abs(float(losses["pnl"].sum()))
    final_equity = initial_capital + float(trades_df["pnl"].sum())

    max_drawdown_pct = 0.0
    if not equity_df.empty:
        equity_series = equity_df["equity"]
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max.replace(0, pd.NA)
        max_drawdown_pct = abs(float(drawdown.min())) * 100 if len(drawdown) else 0.0

    return {
        "total_trades": int(len(trades_df)),
        "win_rate": float((len(wins) / len(trades_df)) * 100),
        "net_profit": float(trades_df["pnl"].sum()),
        "avg_pnl": float(trades_df["pnl"].mean()),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else math.inf,
        "final_equity": float(final_equity),
        "return_pct": float(((final_equity / initial_capital) - 1) * 100),
        "max_drawdown_pct": float(max_drawdown_pct),
    }
