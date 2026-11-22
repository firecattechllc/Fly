"""Daily market-close valuation of the paper ledger; fail closed on missing prices."""
from datetime import datetime, timezone


def calculate(db, histories):
    base=db.execute("SELECT created_utc,cash_cents,positions_json FROM simulation_baseline WHERE id=1").fetchone()
    if base is None:
        return {"status":"BASELINE_REQUIRED","points":[]}
    baseline_date=datetime.fromisoformat(base["created_utc"].replace("Z","+00:00")).date().isoformat()
    holdings={p["symbol"]:{"qty":int(p["qty"]),"mark":int(p["last_cents"])}
              for p in __import__("json").loads(base["positions_json"])}
    trades=[dict(r) for r in db.execute("SELECT created_utc,symbol,side,qty,price_cents,notional_cents FROM transactions ORDER BY created_utc,id")]
    required=set(holdings)|{t["symbol"] for t in trades}
    if not required:
        return {"status":"INSUFFICIENT_DATA","points":[],"message":"No holdings or transactions exist yet."}
    if not required.issubset(histories):
        return {"status":"MISSING_SYMBOL_HISTORY","points":[],"missing_symbols":sorted(required-set(histories))}
    price_maps={}
    for symbol in required:
        bars=histories[symbol].get("bars",[])
        price_maps[symbol]={b["timestamp"][:10]:int(round(float(b["close"])*100)) for b in bars}
    dates=sorted(set.intersection(*(set(v) for v in price_maps.values())))
    dates=[d for d in dates if d>baseline_date]
    if not dates:
        return {"status":"INSUFFICIENT_DATA","points":[],"message":"No common market sessions after the opening baseline."}
    cash=int(base["cash_cents"])
    baseline_equity=cash+sum(x["qty"]*x["mark"] for x in holdings.values())
    previous_equity=baseline_equity
    trade_index=0
    points=[]
    for day in dates:
        while trade_index<len(trades) and trades[trade_index]["created_utc"][:10]<=day:
            t=trades[trade_index]; sym=t["symbol"]; q=int(t["qty"]); amount=int(t["notional_cents"])
            h=holdings.setdefault(sym,{"qty":0,"mark":int(t["price_cents"])})
            if t["side"]=="BUY":
                cash-=amount; h["qty"]+=q
            else:
                if q>h["qty"]:
                    return {"status":"RECONCILIATION_REQUIRED","points":[],"message":"Replay would create a negative holding."}
                cash+=amount; h["qty"]-=q
            trade_index+=1
        market_value=0
        for symbol,h in holdings.items():
            if h["qty"]:
                h["mark"]=price_maps[symbol][day]
                market_value+=h["qty"]*h["mark"]
        equity=cash+market_value
        if cash<0 or equity<=0 or previous_equity<=0:
            return {"status":"RECONCILIATION_REQUIRED","points":[],"message":"Invalid daily account valuation."}
        daily_return=equity/previous_equity-1
        points.append({"date":day,"cash_cents":cash,"market_value_cents":market_value,
                       "equity_cents":equity,"daily_return_pct":round(daily_return*100,5)})
        previous_equity=equity
    current_cash=int(db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0])
    current={r["symbol"]:(int(r["qty"]),int(r["last_cents"])) for r in db.execute("SELECT symbol,qty,last_cents FROM positions")}
    replayed={s:(h["qty"],h["mark"]) for s,h in holdings.items() if h["qty"]>0}
    if cash!=current_cash or {s:q for s,(q,m) in replayed.items()}!={s:q for s,(q,m) in current.items()}:
        return {"status":"RECONCILIATION_REQUIRED","points":[],"message":"Daily market replay does not reconcile to current paper cash and quantities."}
    growth=1.0
    peak=1.0
    max_drawdown=0.0
    for point in points:
        growth*=1+point["daily_return_pct"]/100
        peak=max(peak,growth)
        max_drawdown=min(max_drawdown,growth/peak-1)
    return {"status":"DAILY_MARKET_REPLAY","baseline_utc":base["created_utc"],
            "first_date":points[0]["date"],"last_date":points[-1]["date"],
            "observations":len(points),"daily_time_weighted_return_pct":round((growth-1)*100,4),
            "max_drawdown_pct":round(max_drawdown*100,4),"points":points,
            "method":"Daily close-to-close account equity using paper transactions and aligned Alpaca daily closes. Trades are applied on their recorded UTC date; no external deposits or withdrawals are modeled.",
            "limitations":"Approximate event-date treatment; raw daily bars may omit dividends and corporate actions. IEX is single-exchange coverage. Not an audited return, recommendation, or live brokerage statement."}
