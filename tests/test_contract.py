from vaiiixbr_standard.contract import normalize_trade_result, build_audit_payload, build_dashboard_state


def test_contract_generates_audit_and_dashboard():
    normalized = normalize_trade_result(
        {
            "symbol": "ITUB4",
            "timestamp": "2026-03-25T12:00:00Z",
            "last_price": 31.45,
            "entry_price": 31.45,
            "stop_price": 30.95,
            "take_price": 32.45,
            "trailing_stop_price": 31.20,
            "decision": {
                "status": "WATCHLIST",
                "final_signal": "BUY",
                "final_confidence": 0.63,
                "hybrid_score": 0.21,
                "regime": "PAPER",
                "main_signal_vaiiixbr": "BUY",
                "main_confidence_vaiiixbr": 0.63,
                "hybrid_signal": "BUY",
                "hybrid_confidence": 0.60,
                "strategies": {"ea_like": 0.20},
                "reasons": ["força moderada"],
            },
            "metrics": {"initial_cash": 50.0, "cash": 50.0, "position_open": False, "cooldown_remaining": 0},
        },
        latest_news={"price_bias": "UP_BIAS", "news_price_score": 0.21, "confidence_adjustment_hint": 0.05, "headline_count": 2, "summary": "teste", "learned_tokens": 10},
        stats={"samples": 120, "positive_rate": 0.51, "model_version": "v1"},
    )

    audit = build_audit_payload(normalized)
    dashboard = build_dashboard_state(normalized)

    assert audit["entry_gate"]["verdict"] in {"POSSÍVEL ENTRADA", "ENTRADA CONFIRMADA", "NÃO ENTROU"}
    assert dashboard["action"] == "COMPRA"
    assert normalized["price"]["last"] == 31.45
    assert "positives" in audit["entry_gate"]
    assert "blockers" in audit["entry_gate"]
