"""Portfolio intelligence: sector exposure, transaction cost basis and stress scenarios."""
from decimal import Decimal, ROUND_HALF_UP
from sectors import classify

STRESS = (
 {"id":"rates_up","label":"Rates +100 bps","equity_shock_bps":-300,"bond_shock_bps":-500},
 {"id":"growth_selloff","label":"Growth selloff","equity_shock_bps":-1500,"bond_shock_bps":0},
 {"id":"broad_bear","label":"Broad bear market","equity_shock_bps":-2500,"bond_shock_bps":-500},
 {"id":"energy_spike","label":"Energy shock","equity_shock_bps":-1000,"bond_shock_bps":0},
 {"id":"severe_liquidity","label":"Severe liquidity shock","equity_shock_bps":-3500,"bond_shock_bps":-1500},
)

def stress_test(positions,cash_cents):
    invested=sum(int(p["qty"])*int(p["last_cents"]) for p in positions)
    rows=[]
    for scenario in STRESS:
        loss=int((Decimal(invested*scenario["equity_shock_bps"])/Decimal(10000)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
        equity=int(cash_cents)+invested+loss
        rows.append({**scenario,"hypothetical_pnl_cents":loss,
                     "hypothetical_equity_cents":equity})
    return {"method":"PARALLEL EQUITY SHOCK PROXIES","scenarios":rows,
            "disclaimer":"Illustrative deterministic shocks, not forecasts, VaR, liquidity models, or validated factor scenarios."}

def attribution(db,positions):
    rows=db.execute("SELECT symbol,side,qty,price_cents,notional_cents,created_utc FROM transactions ORDER BY id").fetchall()
    book={}
    realized=0
    for r in rows:
        x=dict(r); sym=x["symbol"]; q=x["qty"]; price=x["price_cents"]
        state=book.setdefault(sym,{"qty":0,"cost":0})
        if x["side"]=="BUY":
            state["qty"]+=q; state["cost"]+=x["notional_cents"]
        else:
            if state["qty"]<=0 or q>state["qty"]:
                raise ValueError("Transaction ledger does not reconcile")
            avg=state["cost"]/state["qty"]
            realized+=int(Decimal(q*(price-avg)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
            state["cost"]-=int(Decimal(q*avg).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
            state["qty"]-=q
    current={p["symbol"]:p for p in positions}
    details=[]
    unrealized=0
    for sym,state in book.items():
        p=current.get(sym)
        if state["qty"]==0:
            continue
        if not p or p["qty"]!=state["qty"]:
            raise ValueError("Transaction ledger does not reconcile to current positions")
        value=state["qty"]*p["last_cents"]
        pnl=value-state["cost"]; unrealized+=pnl
        details.append({"symbol":sym,"quantity":state["qty"],"cost_basis_cents":state["cost"],
                        "market_value_cents":value,"unrealized_pnl_cents":pnl})
    for sym,p in current.items():
        if sym not in book:
            raise ValueError("Existing position predates transaction ledger; attribution baseline unavailable")
    return {"status":"RECONCILED","realized_pnl_cents":realized,
            "unrealized_pnl_cents":unrealized,"total_pnl_cents":realized+unrealized,
            "positions":details,
            "disclaimer":"Paper transaction ledger only; excludes fees, taxes, dividends and corporate actions."}

def report(db,state):
    sectors=classify(state["positions"])
    stress=stress_test(state["positions"],state["cash_cents"])
    try:
        pnl=attribution(db,state["positions"])
    except ValueError as exc:
        pnl={"status":"BASELINE_REQUIRED","reason":str(exc),
             "disclaimer":"No realized/unrealized P&L is reported until the transaction ledger reconciles."}
    return {"report":"FLY PAPER PORTFOLIO INTELLIGENCE","generated_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "mode":"SIMULATION ONLY","portfolio":{"cash_cents":state["cash_cents"],"equity_cents":state["equity_cents"],"positions":state["positions"]},
            "sector_exposure":sectors,"attribution":pnl,"stress_testing":stress,
            "methodology":"Current manually marked paper positions; no brokerage sync or live orders."}
