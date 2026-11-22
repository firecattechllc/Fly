"""Auditable paper-account daily valuation, benchmark comparison and attribution."""
from datetime import datetime
import json


def _compound(values):
    growth=1.0
    for value in values:
        growth*=1+value
    return growth-1


def _periods(points, key):
    groups={}
    for p in points:
        period=p["date"][:7] if key=="month" else p["date"][:4]+"Q"+str((int(p["date"][5:7])-1)//3+1)
        groups.setdefault(period,[]).append(p)
    return [{"period":name,"portfolio_return_pct":round(_compound([x["daily_return_pct"]/100 for x in rows])*100,4),
             "benchmark_return_pct":round(_compound([x["benchmark_return_pct"]/100 for x in rows])*100,4),
             "active_return_pct":round((_compound([x["daily_return_pct"]/100 for x in rows])-_compound([x["benchmark_return_pct"]/100 for x in rows]))*100,4)}
            for name,rows in sorted(groups.items())]


def _scenarios(points, window=20):
    if len(points)<window:
        return {"status":"INSUFFICIENT_DATA","window_sessions":window,"scenarios":[]}
    windows=[]
    for i in range(0,len(points)-window+1):
        rows=points[i:i+window]
        pr=_compound([x["daily_return_pct"]/100 for x in rows])
        br=_compound([x["benchmark_return_pct"]/100 for x in rows])
        windows.append({"start":rows[0]["date"],"end":rows[-1]["date"],"sessions":window,
                        "portfolio_return_pct":round(pr*100,4),"benchmark_return_pct":round(br*100,4),
                        "active_return_pct":round((pr-br)*100,4)})
    return {"status":"COMPUTED","window_sessions":window,"method":"Rolling, overlapping 20-session windows over the exact fetched sample; best/worst ranked by portfolio return.",
            "best":max(windows,key=lambda x:x["portfolio_return_pct"]),
            "worst":min(windows,key=lambda x:x["portfolio_return_pct"]),
            "all_windows":windows}


def calculate(db, histories, benchmark="SPY"):
    base=db.execute("SELECT created_utc,cash_cents,positions_json FROM simulation_baseline WHERE id=1").fetchone()
    if base is None:
        return {"status":"BASELINE_REQUIRED","points":[]}
    baseline_date=datetime.fromisoformat(base["created_utc"].replace("Z","+00:00")).date().isoformat()
    holdings={p["symbol"]:{"qty":int(p["qty"]),"mark":int(p["last_cents"])} for p in json.loads(base["positions_json"])}
    trades=[dict(r) for r in db.execute("SELECT created_utc,symbol,side,qty,price_cents,notional_cents FROM transactions ORDER BY created_utc,id")]
    required=set(holdings)|{t["symbol"] for t in trades}
    if not required:
        return {"status":"INSUFFICIENT_DATA","points":[],"message":"No holdings or transactions exist yet."}
    missing=sorted((required|{benchmark})-set(histories))
    if missing:
        return {"status":"MISSING_SYMBOL_HISTORY","points":[],"missing_symbols":missing}
    price_maps={}
    for symbol in required|{benchmark}:
        price_maps[symbol]={b["timestamp"][:10]:int(round(float(b["close"])*100)) for b in histories[symbol].get("bars",[]) if float(b["close"])>0}
    dates=sorted(set.intersection(*(set(v) for v in price_maps.values())))
    dates=[d for d in dates if d>baseline_date]
    if not dates:
        return {"status":"INSUFFICIENT_DATA","points":[],"message":"No common market sessions after baseline."}
    cash=int(base["cash_cents"])
    baseline_equity=cash+sum(x["qty"]*x["mark"] for x in holdings.values())
    previous_equity=baseline_equity
    previous_benchmark=next((price_maps[benchmark][d] for d in sorted(price_maps[benchmark]) if d<=baseline_date),None)
    if previous_benchmark is None:
        return {"status":"INSUFFICIENT_DATA","points":[],"message":"No benchmark close on or before baseline."}
    trade_index=0
    points=[]
    contribution_cents={}
    for day in dates:
        previous_values={s:h["qty"]*h["mark"] for s,h in holdings.items()}
        previous_marks={s:h["mark"] for s,h in holdings.items()}
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
        asset_returns={}
        for symbol,h in holdings.items():
            if h["qty"]:
                old=previous_values.get(symbol,0)
                close=price_maps[symbol][day]
                asset_returns[symbol]=(close/previous_marks[symbol] - 1) if previous_marks.get(symbol,0)>0 else 0.0
                h["mark"]=close
                market_value+=h["qty"]*close
        equity=cash+market_value
        if cash<0 or equity<=0 or previous_equity<=0:
            return {"status":"RECONCILIATION_REQUIRED","points":[],"message":"Invalid daily account valuation."}
        daily_return=equity/previous_equity-1
        benchmark_close=price_maps[benchmark][day]
        benchmark_return=benchmark_close/previous_benchmark-1
        day_contributions={}
        for symbol,old_value in previous_values.items():
            if old_value>0 and previous_equity>0:
                contribution=(old_value/previous_equity)*asset_returns.get(symbol,0)
                day_contributions[symbol]=contribution
                contribution_cents[symbol]=contribution_cents.get(symbol,0)+contribution*previous_equity
        points.append({"date":day,"cash_cents":cash,"market_value_cents":market_value,
                       "equity_cents":equity,"daily_return_pct":round(daily_return*100,5),
                       "benchmark_return_pct":round(benchmark_return*100,5),
                       "active_return_pct":round((daily_return-benchmark_return)*100,5),
                       "contributions_pct":{s:round(v*100,5) for s,v in day_contributions.items()}})
        previous_equity=equity
        previous_benchmark=benchmark_close
    current_cash=int(db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0])
    current={r["symbol"]:(int(r["qty"]),int(r["last_cents"])) for r in db.execute("SELECT symbol,qty,last_cents FROM positions")}
    replayed={s:(h["qty"],h["mark"]) for s,h in holdings.items() if h["qty"]>0}
    if cash!=current_cash or {s:q for s,(q,m) in replayed.items()}!={s:q for s,(q,m) in current.items()}:
        return {"status":"RECONCILIATION_REQUIRED","points":[],"message":"Market replay does not reconcile to current paper cash and quantities."}
    portfolio_return=_compound([p["daily_return_pct"]/100 for p in points])
    benchmark_return=_compound([p["benchmark_return_pct"]/100 for p in points])
    growth=peak=1.0; max_drawdown=0.0
    for point in points:
        growth*=1+point["daily_return_pct"]/100; peak=max(peak,growth); max_drawdown=min(max_drawdown,growth/peak-1)
    contributions=[{"symbol":s,"contribution_cents":round(v),"contribution_pct_equity":round(v/baseline_equity*100,4)} for s,v in sorted(contribution_cents.items())]
    return {"status":"DAILY_MARKET_REPLAY","benchmark":benchmark,"baseline_utc":base["created_utc"],
            "first_date":points[0]["date"],"last_date":points[-1]["date"],"observations":len(points),
            "daily_time_weighted_return_pct":round(portfolio_return*100,4),
            "benchmark_time_weighted_return_pct":round(benchmark_return*100,4),
            "active_return_pct":round((portfolio_return-benchmark_return)*100,4),
            "max_drawdown_pct":round(max_drawdown*100,4),"monthly_returns":_periods(points,"month"),
            "quarterly_returns":_periods(points,"quarter"),"contribution_attribution":contributions,
            "scenario_comparison":_scenarios(points),"points":points,
            "method":"Daily close-to-close paper NAV, external cash flows excluded, chained daily returns. Benchmark uses the same aligned sessions.",
            "limitations":"Approximate UTC trade-date application; simple contribution attribution uses prior-close position weights and does not fully allocate intraday execution effects. Raw IEX bars may omit dividends/corporate actions and represent one exchange. No audited statement or recommendation."}
