"""Historical risk diagnostics using current paper weights and aligned provider bars."""
from math import sqrt
from statistics import mean

def _returns(bars):
    by_date = {b["timestamp"][:10]: float(b["close"]) for b in bars}
    dates = sorted(by_date)
    return {dates[i]: by_date[dates[i]] / by_date[dates[i-1]] - 1
            for i in range(1, len(dates)) if by_date[dates[i-1]] > 0}

def _stats(xs):
    if len(xs) < 2:
        return {"observations":len(xs), "status":"INSUFFICIENT_DATA"}
    avg = mean(xs)
    variance = sum((x-avg)**2 for x in xs)/(len(xs)-1)
    return {"observations":len(xs), "mean_daily_return_pct":round(avg*100,4),
            "sample_daily_volatility_pct":round(sqrt(variance)*100,4)}

def calculate(positions, history_by_symbol, benchmark="SPY"):
    """Use present-day paper weights; this is not a historical holdings backtest."""
    weights = {}
    total = sum(int(p["qty"])*int(p["last_cents"]) for p in positions)
    for p in positions:
        value = int(p["qty"])*int(p["last_cents"])
        if value > 0 and total > 0:
            weights[p["symbol"]] = value/total
    if not weights:
        return {"status":"INSUFFICIENT_DATA","benchmark":benchmark,
                "aligned_observations":0,"metrics":[],
                "disclaimer":"No current paper holdings to analyze."}
    series = {s:_returns(history_by_symbol[s]["bars"])
              for s in weights if s in history_by_symbol}
    bench = _returns(history_by_symbol[benchmark]["bars"]) if benchmark in history_by_symbol else {}
    common = set(bench)
    for values in series.values():
        common &= set(values)
    dates = sorted(common)
    if len(dates) < 3:
        return {"status":"INSUFFICIENT_DATA","benchmark":benchmark,
                "aligned_observations":len(dates),"metrics":[],
                "disclaimer":"At least three aligned daily returns are required."}
    portfolio = [sum(weights[s]*series[s][d] for s in weights if s in series)
                 for d in dates]
    market = [bench[d] for d in dates]
    pm, bm = mean(portfolio), mean(market)
    variance = sum((x-bm)**2 for x in market)/(len(market)-1)
    covariance = sum((x-pm)*(y-bm) for x,y in zip(portfolio,market))/(len(market)-1)
    beta = covariance/variance if variance > 0 else None
    peak = 1.0
    wealth = 1.0
    max_dd = 0.0
    for ret in portfolio:
        wealth *= 1+ret
        peak = max(peak, wealth)
        max_dd = min(max_dd, wealth/peak-1)
    correlations = {}
    for symbol, values in series.items():
        xs=[values[d] for d in dates]
        xm, ym = mean(xs), mean(market)
        vx=sum((x-xm)**2 for x in xs)
        vy=sum((y-ym)**2 for y in market)
        correlations[symbol]=round(sum((x-xm)*(y-ym) for x,y in zip(xs,market))/sqrt(vx*vy),4) if vx>0 and vy>0 else None
    return {"status":"DESCRIPTIVE_PROXY","benchmark":benchmark,
            "aligned_observations":len(dates),"first_date":dates[0],"last_date":dates[-1],
            "current_weights_used":{s:round(w*100,2) for s,w in weights.items()},
            "proxy_portfolio":_stats(portfolio),"benchmark":benchmark,
            "benchmark_stats":_stats(market),
            "beta_vs_benchmark":round(beta,4) if beta is not None else None,
            "max_drawdown_pct":round(max_dd*100,2),
            "correlation_to_benchmark":correlations,
            "sector_exposure":{"status":"UNCLASSIFIED","note":"No verified sector taxonomy is connected."},
            "method":"Daily close-to-close returns; present-day weights held constant across the sample.",
            "disclaimer":"Not a historical holdings backtest, forecast, VaR, or investment recommendation. IEX coverage may be incomplete; unadjusted prices omit dividends and corporate actions."}
