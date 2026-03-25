from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _build_entry_gate(decision: Dict[str, Any], metrics: Dict[str, Any], latest_news: Dict[str, Any]) -> Dict[str, Any]:
    final_signal = str(decision.get("final_signal", "HOLD")).upper()
    status = str(decision.get("status", "UNKNOWN")).upper()
    final_confidence = _safe_float(decision.get("final_confidence", 0.0))
    hybrid_score = _safe_float(decision.get("hybrid_score", 0.0))
    price_bias = str(latest_news.get("price_bias", "NEUTRAL")).upper()
    confidence_hint = _safe_float(latest_news.get("confidence_adjustment_hint", 0.0))

    blockers: List[str] = []
    positives: List[str] = []

    if final_signal == "BUY":
        positives.append("sinal final de compra ativo")
    else:
        blockers.append("sinal final não está em compra")

    if status == "CONFIRMED":
        positives.append("confirmação entre motor principal e ensemble")
    elif status == "WATCHLIST":
        blockers.append("o ensemble detectou oportunidade, mas o motor principal ainda não confirmou")
    elif status == "WEAK_MAIN_SIGNAL":
        blockers.append("o motor principal sinalizou, mas sem confirmação suficiente do ensemble")
    elif status == "CONFLICT":
        blockers.append("há conflito entre os sinais internos")
    elif status == "NEUTRAL":
        blockers.append("o sistema está neutro")

    if final_confidence >= 0.78:
        positives.append(f"confiança alta ({final_confidence:.2%})")
    elif final_confidence >= 0.58:
        positives.append(f"confiança intermediária ({final_confidence:.2%})")
        blockers.append("a confiança ainda não atingiu o nível de entrada garantida")
    else:
        blockers.append(f"confiança baixa ({final_confidence:.2%})")

    if hybrid_score > 0:
        positives.append(f"score híbrido positivo ({hybrid_score:+.3f})")
    else:
        blockers.append(f"score híbrido não favorável ({hybrid_score:+.3f})")

    if price_bias == "UP_BIAS":
        positives.append("noticiário favorece viés de alta")
    elif price_bias == "DOWN_BIAS":
        blockers.append("noticiário atual pesa contra alta")

    if confidence_hint < 0:
        blockers.append("ajuste de confiança por notícias está negativo")

    if metrics.get("position_open"):
        blockers.append("já existe posição aberta no paper trading")

    if _safe_int(metrics.get("cooldown_remaining", 0)) > 0:
        blockers.append(f"cooldown ativo em {_safe_int(metrics.get('cooldown_remaining', 0))} barras")

    ready = final_signal == "BUY" and status == "CONFIRMED" and final_confidence >= 0.78 and not metrics.get("position_open") and _safe_int(metrics.get("cooldown_remaining", 0)) == 0

    if ready:
        verdict = "ENTRADA CONFIRMADA"
    elif final_signal == "BUY" and final_confidence >= 0.58:
        verdict = "POSSÍVEL ENTRADA"
    else:
        verdict = "NÃO ENTROU"

    return {"verdict": verdict, "ready": ready, "positives": positives, "blockers": blockers}


def normalize_trade_result(result: Dict[str, Any], latest_news: Dict[str, Any] | None = None, stats: Dict[str, Any] | None = None) -> Dict[str, Any]:
    latest_news = latest_news or {}
    stats = stats or {}
    metrics = result.get("metrics") or {}
    decision = result.get("decision") or {}
    normalized = {
        "symbol": result.get("symbol", "ITUB4"),
        "timestamp": result.get("timestamp") or latest_news.get("timestamp") or "--",
        "price": {
            "last": round(_safe_float(result.get("last_price", 0.0)), 4),
            "entry": round(_safe_float(result.get("entry_price", 0.0)), 4),
            "stop": round(_safe_float(result.get("stop_price", 0.0)), 4),
            "target": round(_safe_float(result.get("take_price", 0.0)), 4),
            "trailing": round(_safe_float(result.get("trailing_stop_price", 0.0)), 4),
        },
        "decision": {
            "status": decision.get("status", "UNKNOWN"),
            "final_signal": decision.get("final_signal", "HOLD"),
            "final_confidence": round(_safe_float(decision.get("final_confidence", 0.0)), 4),
            "hybrid_score": round(_safe_float(decision.get("hybrid_score", 0.0)), 4),
            "regime": decision.get("regime", "UNKNOWN"),
            "main_signal_vaiiixbr": decision.get("main_signal_vaiiixbr", "UNKNOWN"),
            "main_confidence_vaiiixbr": round(_safe_float(decision.get("main_confidence_vaiiixbr", 0.0)), 4),
            "hybrid_signal": decision.get("hybrid_signal", "UNKNOWN"),
            "hybrid_confidence": round(_safe_float(decision.get("hybrid_confidence", 0.0)), 4),
            "strategies": decision.get("strategies") or {},
            "reasons": decision.get("reasons") or [],
        },
        "metrics": {
            "initial_cash": round(_safe_float(metrics.get("initial_cash", 50.0)), 2),
            "cash": round(_safe_float(metrics.get("cash", 0.0)), 2),
            "position_open": bool(metrics.get("position_open", False)),
            "realized_pnl": round(_safe_float(metrics.get("realized_pnl", 0.0)), 4),
            "trade_count": _safe_int(metrics.get("trade_count", 0)),
            "win_trades": _safe_int(metrics.get("win_trades", 0)),
            "loss_trades": _safe_int(metrics.get("loss_trades", 0)),
            "win_rate": round(_safe_float(metrics.get("win_rate", 0.0)), 4),
            "cooldown_remaining": _safe_int(metrics.get("cooldown_remaining", 0)),
        },
        "news": {
            "price_bias": latest_news.get("price_bias", "NEUTRAL"),
            "news_score": round(_safe_float(latest_news.get("news_price_score", 0.0)), 4),
            "confidence_hint": round(_safe_float(latest_news.get("confidence_adjustment_hint", 0.0)), 4),
            "headline_count": _safe_int(latest_news.get("headline_count", 0)),
            "summary": latest_news.get("summary", ""),
            "learned_tokens": _safe_int(latest_news.get("learned_tokens", 0)),
        },
        "colab": {
            "samples": _safe_int(stats.get("samples", 0)),
            "positive_rate": round(_safe_float(stats.get("positive_rate", 0.0)), 4),
            "model_version": stats.get("model_version", "unknown"),
        },
    }
    normalized["entry_gate"] = _build_entry_gate(normalized["decision"], normalized["metrics"], normalized["news"])
    return normalized


def build_audit_payload(normalized: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": normalized["symbol"],
        "timestamp": normalized["timestamp"],
        "price": normalized["price"],
        "decision": normalized["decision"],
        "entry_gate": normalized["entry_gate"],
        "metrics": normalized["metrics"],
        "news": normalized["news"],
        "colab": normalized["colab"],
        "strategies": normalized["decision"]["strategies"],
        "reasons": normalized["decision"]["reasons"],
    }


def build_dashboard_state(normalized: Dict[str, Any]) -> Dict[str, Any]:
    final_signal = str(normalized["decision"]["final_signal"]).upper()
    action_display = "NEUTRO"
    if final_signal == "BUY":
        action_display = "COMPRA"
    elif final_signal == "SELL":
        action_display = "VENDA"

    return {
        "action": action_display,
        "status": normalized["decision"]["status"],
        "mode": normalized["decision"]["regime"],
        "summary": normalized["news"]["summary"],
        "headline_count": normalized["news"]["headline_count"],
        "news_score": normalized["news"]["news_score"],
        "confidence_hint": normalized["news"]["confidence_hint"],
        "learned_tokens": normalized["news"]["learned_tokens"],
        "model_samples": normalized["colab"]["samples"],
        "positive_rate": normalized["colab"]["positive_rate"],
        "audit_verdict": normalized["entry_gate"]["verdict"],
        "last_price": normalized["price"]["last"],
        "entry_price": normalized["price"]["entry"],
        "stop_price": normalized["price"]["stop"],
        "take_price": normalized["price"]["target"],
    }
