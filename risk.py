"""Transparent, deterministic paper portfolio risk indicators.

These are exposure metrics and arithmetic shock scenarios, NOT BlackRock models
or validated VaR estimates. Scenario shifts are illustrative only.
"""
from decimal import Decimal, ROUND_HALF_UP

SCENARIOS = (
    {"id":"mild","label":"Equities −5%","shock_bps":-500},
    {"id":"correction","label":"Equities −10%","shock_bps":-1000},
    {"id":"severe","label":"Equities −20%","shock_bps":-2000},
)

def calculate(state):
    cash = state["cash_cents"]
    positions = state["positions"]
    equity = state["equity_cents"]
    invested = sum(p["qty"] * p["last_cents"] for p in positions)
    if cash < 0 or invested < 0 or equity <= 0 or cash + invested != equity:
        raise ValueError("Inconsistent simulated portfolio")
    holdings = []
    for p in positions:
        amount = p["qty"] * p["last_cents"]
        holdings.append({
            "symbol": p["symbol"], "market_value_cents": amount,
            "portfolio_weight_pct": round(amount * 100 / equity, 2),
        })
    holdings.sort(key=lambda h: (-h["market_value_cents"], h["symbol"]))
    shocks = []
    for s in SCENARIOS:
        # Half-up rounding to whole cents; assumes all marked positions move equally.
        delta = int((Decimal(invested * s["shock_bps"]) / Decimal(10000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        shocks.append({**s,"hypothetical_loss_cents": delta,"hypothetical_equity_cents":equity+delta})
    return {
        "method":"MARK-TO-LAST-MANUAL-PRICE",
        "disclaimer":"Indicative exposure and parallel equity shocks, not VaR or a predictive risk model.",
        "currency":"USD",
        "gross_exposure_cents":invested,
        "cash_weight_pct":round(cash * 100 / equity, 2),
        "invested_weight_pct":round(invested * 100 / equity, 2),
        "largest_position_pct":holdings[0]["portfolio_weight_pct"] if holdings else 0,
        "position_count":len(holdings),
        "weights":holdings,
        "scenarios":shocks,
    }
