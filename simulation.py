import json
from datetime import datetime, timezone


def ensure_baseline(db):
    db.execute("CREATE TABLE IF NOT EXISTS simulation_baseline(id INTEGER PRIMARY KEY CHECK(id=1), created_utc TEXT NOT NULL, cash_cents INTEGER NOT NULL, positions_json TEXT NOT NULL)")
    row=db.execute("SELECT id FROM simulation_baseline WHERE id=1").fetchone()
    if row is None:
        cash=int(db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0])
        positions=[dict(r) for r in db.execute("SELECT symbol,qty,last_cents FROM positions ORDER BY symbol")]
        db.execute("INSERT INTO simulation_baseline VALUES(1,?,?,?)",(datetime.now(timezone.utc).isoformat(),cash,json.dumps(positions,sort_keys=True)))


def replay(db):
    row=db.execute("SELECT created_utc,cash_cents,positions_json FROM simulation_baseline WHERE id=1").fetchone()
    if row is None:
        return {"status":"BASELINE_REQUIRED","points":[],"message":"No dated opening snapshot exists."}
    cash=int(row["cash_cents"])
    positions={p["symbol"]:{"qty":int(p["qty"]),"mark":int(p["last_cents"])} for p in json.loads(row["positions_json"])}
    baseline_equity=cash+sum(x["qty"]*x["mark"] for x in positions.values())
    points=[{"timestamp":row["created_utc"],"event":"OPENING_BASELINE","cash_cents":cash,"equity_cents":baseline_equity}]
    trades=db.execute("SELECT created_utc,symbol,side,qty,price_cents,notional_cents FROM transactions ORDER BY id").fetchall()
    for trade in trades:
        t=dict(trade); sym=t["symbol"]; q=int(t["qty"]); price=int(t["price_cents"]); amount=int(t["notional_cents"])
        holding=positions.setdefault(sym,{"qty":0,"mark":price})
        if t["side"]=="BUY":
            cash-=amount; holding["qty"]+=q
        else:
            if q>holding["qty"]: raise ValueError("Transaction replay found a negative position")
            cash+=amount; holding["qty"]-=q
        holding["mark"]=price
        equity=cash+sum(x["qty"]*x["mark"] for x in positions.values())
        if cash<0 or equity<=0: raise ValueError("Transaction replay accounting failed")
        points.append({"timestamp":t["created_utc"],"event":t["side"],"symbol":sym,"qty":q,"price_cents":price,"cash_cents":cash,"equity_cents":equity})
    current_cash=int(db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0])
    current={r["symbol"]:(int(r["qty"]),int(r["last_cents"])) for r in db.execute("SELECT symbol,qty,last_cents FROM positions")}
    replayed={s:(v["qty"],v["mark"]) for s,v in positions.items() if v["qty"]>0}
    if cash!=current_cash or replayed!=current:
        return {"status":"RECONCILIATION_REQUIRED","baseline_utc":row["created_utc"],"points":points,"message":"Replay does not match current paper account; no performance result is published."}
    final=points[-1]["equity_cents"]
    return {"status":"RECONCILED_EVENT_REPLAY","baseline_utc":row["created_utc"],"observations":len(points),"baseline_equity_cents":baseline_equity,"current_equity_cents":final,"equity_change_cents":final-baseline_equity,"equity_change_pct":round((final/baseline_equity-1)*100,2),"points":points,"method":"Opening snapshot plus chronological paper transactions, valued at last transaction marks. No daily market-price history is implied.","disclaimer":"Event-based simulator replay, not time-weighted performance, historical market backtest, or investment return. Opening holdings carry unknown pre-baseline cost basis."}
