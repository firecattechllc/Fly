"""Advanced, reproducible portfolio analytics. Pure Python; long-only and paper-only."""
from __future__ import annotations
import math
import random
from statistics import mean

FACTOR_LABELS = {
    "SPY": "Market", "IWM": "Size proxy", "IWD": "Value proxy",
    "MTUM": "Momentum proxy", "USMV": "Minimum-volatility proxy",
    "QQQ": "Growth proxy",
}
SECTOR_ETFS = {
    "XLB":"Materials","XLC":"Communication Services","XLE":"Energy",
    "XLF":"Financials","XLI":"Industrials","XLK":"Information Technology",
    "XLP":"Consumer Staples","XLRE":"Real Estate","XLU":"Utilities",
    "XLV":"Health Care","XLY":"Consumer Discretionary",
}
TRADING_DAYS = 252


def _return_map(history):
    bars = history.get("bars", []) if history else []
    prices = {b["timestamp"][:10]: float(b["close"]) for b in bars if float(b.get("close", 0)) > 0}
    dates = sorted(prices)
    return {dates[i]: prices[dates[i]] / prices[dates[i-1]] - 1
            for i in range(1, len(dates)) if prices[dates[i-1]] > 0}


def _solve(matrix, vector, tolerance=1e-11):
    """Gauss-Jordan solve with partial pivoting; singular matrices fail closed."""
    n = len(vector)
    a = [list(map(float, matrix[i])) + [float(vector[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < tolerance:
            raise ValueError("Singular or collinear design matrix")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [x / scale for x in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor:
                a[row] = [x - factor*y for x, y in zip(a[row], a[col])]
    return [a[i][-1] for i in range(n)]


def _ols(y, columns, labels):
    """OLS with intercept. Returns coefficients, t-statistics, R2 and residual risk."""
    n = len(y)
    k = len(labels) + 1
    if n <= k + 1:
        return {"status":"INSUFFICIENT_DATA","observations":n,"parameters":k}
    x = [[1.0] + [columns[label][i] for label in labels] for i in range(n)]
    xtx = [[sum(row[i]*row[j] for row in x) for j in range(k)] for i in range(k)]
    xty = [sum(x[r][i]*y[r] for r in range(n)) for i in range(k)]
    try:
        beta = _solve(xtx, xty)
        inv = []
        for j in range(k):
            e = [1.0 if i == j else 0.0 for i in range(k)]
            inv.append(_solve(xtx, e))
        inv = [[inv[j][i] for j in range(k)] for i in range(k)]
    except ValueError as exc:
        return {"status":"COLLINEAR_FACTORS","observations":n,"factors":labels,"reason":str(exc)}
    fitted = [sum(a*b for a,b in zip(row,beta)) for row in x]
    residuals = [a-b for a,b in zip(y,fitted)]
    ybar = mean(y)
    sse = sum(v*v for v in residuals)
    sst = sum((v-ybar)**2 for v in y)
    dof = n-k
    mse = sse/dof
    coefs = {}
    for j, label in enumerate(["alpha"]+labels):
        se = math.sqrt(max(0.0, mse*inv[j][j]))
        coefs[label] = {"daily":beta[j],"annualized_pct":round(beta[j]*TRADING_DAYS*100,4) if j==0 else None,
                        "standard_error":se,"t_stat":round(beta[j]/se,4) if se else None}
        if j:
            coefs[label]["beta"] = round(beta[j],4)
    return {"status":"COMPUTED","observations":n,"parameters":k,"factors":labels,
            "coefficients":coefs,"r_squared":round(1-sse/sst,6) if sst else None,
            "adjusted_r_squared":round(1-(1-(1-sse/sst))*(n-1)/dof,6) if sst and dof else None,
            "residual_volatility_annualized_pct":round(math.sqrt(mse)*math.sqrt(TRADING_DAYS)*100,4),
            "method":"OLS with intercept; daily simple returns; conventional standard errors/t-statistics assume homoskedastic, uncorrelated residuals. No Newey-West correction."}


def _covariance(series):
    n=len(series)
    means=[mean(x) for x in series]
    return [[sum((series[i][t]-means[i])*(series[j][t]-means[j]) for t in range(n))/(n-1)
             for j in range(len(series))] for i in range(len(series))]


def _portfolio_stats(weights, mu, cov):
    annual_return=sum(w*m for w,m in zip(weights,mu))*TRADING_DAYS
    variance=sum(weights[i]*cov[i][j]*weights[j] for i in range(len(weights)) for j in range(len(weights)))
    vol=math.sqrt(max(variance,0)*TRADING_DAYS)
    return annual_return,vol


def _optimization(symbols, series):
    n=len(symbols)
    if n==0 or not series or len(series[0])<3:
        return {"status":"INSUFFICIENT_DATA","message":"At least one holding and three aligned daily returns are required."}
    if n>10:
        return {"status":"LIMIT_EXCEEDED","message":"Optimization supports at most 10 holdings."}
    mu=[mean(x) for x in series]
    cov=_covariance(series)
    rng=random.Random(20261122)
    candidates=[]
    # Deterministic Dirichlet-like long-only portfolios; includes equal weights and corners.
    candidates.append([1/n]*n)
    for i in range(n):
        candidates.append([1.0 if j==i else 0.0 for j in range(n)])
    for _ in range(6000):
        raw=[rng.expovariate(1.0) for _ in range(n)]
        total=sum(raw)
        candidates.append([x/total for x in raw])
    rows=[]
    for w in candidates:
        ret,vol=_portfolio_stats(w,mu,cov)
        sharpe=ret/vol if vol>1e-12 else None
        rows.append({"weights":{s:round(w[i]*100,3) for i,s in enumerate(symbols)},
                     "expected_return_pct":round(ret*100,4),"volatility_pct":round(vol*100,4),
                     "sharpe_zero_rf":round(sharpe,4) if sharpe is not None else None})
    minvar=min(rows,key=lambda x:x["volatility_pct"])
    maxsharpe=max((x for x in rows if x["sharpe_zero_rf"] is not None),key=lambda x:x["sharpe_zero_rf"],default=None)
    # Approximate efficient frontier: lowest-volatility candidate for each expected-return bucket.
    low=min(x["expected_return_pct"] for x in rows); high=max(x["expected_return_pct"] for x in rows)
    frontier=[]
    if high-low<1e-9:
        frontier=[minvar]
    else:
        for bucket in range(11):
            target=low+(high-low)*bucket/10
            eligible=[x for x in rows if target <= x["expected_return_pct"] <= target+(high-low)/10+1e-9]
            if eligible:
                best=min(eligible,key=lambda x:x["volatility_pct"])
                if not frontier or best["expected_return_pct"]>frontier[-1]["expected_return_pct"]:
                    frontier.append(best)
    return {"status":"COMPUTED","method":"6,002 deterministic long-only random/equal-weight/corner portfolios; sample mean/covariance annualized by 252; zero risk-free proxy. Approximate frontier, not a convex optimizer.",
            "observations":len(series[0]),"assets":symbols,"portfolios_evaluated":len(rows),
            "minimum_variance":minvar,"maximum_sharpe_zero_rf":maxsharpe,
            "efficient_frontier":frontier,"expected_return_assumption":"Historical arithmetic mean daily return × 252; highly sample-sensitive."}


def _monte_carlo(portfolio, seed=20261122, paths=1500, horizon=252):
    if len(portfolio)<3:
        return {"status":"INSUFFICIENT_DATA","observations":len(portfolio)}
    rng=random.Random(seed)
    finals=[]; drawdowns=[]; losses=0
    n=len(portfolio)
    for _ in range(paths):
        wealth=peak=1.0; worst=0.0
        for _day in range(horizon):
            r=portfolio[rng.randrange(n)]
            wealth*=max(0.000001,1+r)
            peak=max(peak,wealth)
            worst=min(worst,wealth/peak-1)
        finals.append(wealth)
        drawdowns.append(worst)
        if wealth<1: losses+=1
    finals.sort(); drawdowns.sort()
    def pct(a,p): return a[min(len(a)-1,max(0,int((len(a)-1)*p)))]
    return {"status":"COMPUTED","paths":paths,"horizon_sessions":horizon,"seed":seed,
            "method":"Historical daily-return bootstrap with replacement; independent daily resampling; no fitted distribution or regime switching.",
            "probability_of_loss_pct":round(losses/paths*100,2),
            "ending_wealth_percentiles":{"p05":round(pct(finals,.05),4),"p25":round(pct(finals,.25),4),
                                        "p50":round(pct(finals,.50),4),"p75":round(pct(finals,.75),4),
                                        "p95":round(pct(finals,.95),4)},
            "maximum_drawdown_percentiles":{"p05":round(pct(drawdowns,.05)*100,2),
                                            "p50":round(pct(drawdowns,.50)*100,2)},
            "disclaimer":"Illustrative resampling of a short historical sample; path dependence, fat tails, changing regimes, liquidity, fees and taxes are not modeled."}


def _sector_rotation(histories):
    maps={s:_return_map(histories.get(s)) for s in SECTOR_ETFS}
    if not any(maps.values()):
        return {"status":"INSUFFICIENT_DATA","sectors":[]}
    dates=sorted(set.intersection(*(set(v) for v in maps.values() if v))) if sum(bool(v) for v in maps.values())>1 else []
    rows=[]
    for symbol,sector in SECTOR_ETFS.items():
        values=maps[symbol]
        common=sorted(set(values)&set(dates)) if dates else sorted(values)
        if len(common)<22:
            continue
        def compound(window):
            chosen=common[-window:]
            growth=math.prod(1+values[d] for d in chosen)
            return (growth-1)*100
        rows.append({"symbol":symbol,"sector":sector,"sessions":len(common),
                     "return_21d_pct":round(compound(21),3),
                     "return_63d_pct":round(compound(min(63,len(common))),3),
                     "return_252d_pct":round(compound(min(252,len(common))),3),
                     "last_date":common[-1]})
    rows.sort(key=lambda x:x["return_63d_pct"],reverse=True)
    for i,row in enumerate(rows,1): row["rank_63d"]=i
    return {"status":"COMPUTED" if rows else "INSUFFICIENT_DATA","sectors":rows,
            "method":"Sector ETF total price-return proxies ranked on aligned 63-session close-to-close samples; returns exclude dividends and may be IEX-incomplete.",
            "leaders":[x["sector"] for x in rows[:3]],"laggards":[x["sector"] for x in rows[-3:]] if rows else []}


def analyze(positions, histories, days=365, paths=1500, horizon=252):
    """Produce regression, sector rotation, frontier, bootstrap and risk decomposition."""
    if not positions:
        return {"status":"INSUFFICIENT_DATA","message":"No current paper holdings to analyze."}
    clean=[p for p in positions if int(p.get("qty",0))>0 and int(p.get("last_cents",0))>0]
    total=sum(int(p["qty"])*int(p["last_cents"]) for p in clean)
    if not total:
        return {"status":"INSUFFICIENT_DATA","message":"No invested paper holdings."}
    if len(clean)>10:
        return {"status":"LIMIT_EXCEEDED","message":"Advanced analytics supports at most 10 holdings."}
    weights={p["symbol"]:int(p["qty"])*int(p["last_cents"])/total for p in clean}
    symbols=list(weights)
    maps={s:_return_map(histories.get(s)) for s in symbols}
    factor_symbols=list(FACTOR_LABELS)
    factor_maps={s:_return_map(histories.get(s)) for s in factor_symbols}
    # Require market and available factor series; missing optional factor ETFs are reported, not imputed.
    required=["SPY"]
    absent=[s for s in required if not factor_maps.get(s)]
    if absent:
        return {"status":"INSUFFICIENT_DATA","missing_symbols":absent,"message":"Market proxy history is required."}
    base_dates=set.intersection(*(set(maps[s]) for s in symbols),set(factor_maps["SPY"]))
    # An optional ETF with sparse coverage must not shrink the whole sample.
    coverage_floor=max(10,int(len(base_dates)*0.80))
    factor_available=[s for s in factor_symbols if factor_maps.get(s) and
                      len(base_dates & set(factor_maps[s]))>=coverage_floor]
    excluded_optional=[s for s in factor_symbols if s not in factor_available]
    common=set(base_dates)
    for s in factor_available:
        common &= set(factor_maps[s])
    dates=sorted(common)
    if len(dates)<max(10,len(factor_available)+3):
        return {"status":"INSUFFICIENT_DATA","aligned_observations":len(dates),"message":"Not enough common daily observations for stable regression and portfolio analysis."}
    asset_series=[[maps[s][d] for d in dates] for s in symbols]
    portfolio=[sum(weights[s]*maps[s][d] for s in symbols) for d in dates]
    # Factor design uses market plus active-proxy spreads to reduce shared market component.
    factor_cols={"Market":factor_maps["SPY"]}
    for symbol,label in (("IWM","Size (IWM-SPY)"),("IWD","Value (IWD-SPY)"),
                         ("MTUM","Momentum (MTUM-SPY)"),("USMV","Low volatility (USMV-SPY)"),
                         ("QQQ","Growth (QQQ-SPY)")):
        if symbol in factor_available:
            factor_cols[label]={d:factor_maps[symbol][d]-factor_maps["SPY"][d] for d in dates}
    regression_columns={k:[v[d] for d in dates] for k,v in factor_cols.items()}
    regression_labels=list(regression_columns)
    excluded_factors=[]
    regression=_ols(portfolio,regression_columns,regression_labels)
    # Deterministically drop the least essential proxy first if the sample is rank-deficient.
    for candidate in ("Growth (QQQ-SPY)","Low volatility (USMV-SPY)","Value (IWD-SPY)","Momentum (MTUM-SPY)","Size (IWM-SPY)"):
        if regression.get("status")!="COLLINEAR_FACTORS": break
        if candidate in regression_labels:
            regression_labels.remove(candidate); excluded_factors.append(candidate)
            regression=_ols(portfolio,regression_columns,regression_labels)
    regression["excluded_collinear_factors"]=excluded_factors
    cov=_covariance(asset_series)
    # Euler volatility contributions: w_i * (Sigma w)_i / portfolio variance.
    w=[weights[s] for s in symbols]
    variance=sum(w[i]*cov[i][j]*w[j] for i in range(len(w)) for j in range(len(w)))
    vol=math.sqrt(max(variance,0)*TRADING_DAYS)
    risk=[]
    for i,s in enumerate(symbols):
        component=sum(cov[i][j]*w[j] for j in range(len(w)))
        contribution=w[i]*component/variance if variance>1e-18 else None
        risk.append({"symbol":s,"weight_pct":round(w[i]*100,3),
                     "marginal_volatility_pct":round(component/vol*math.sqrt(TRADING_DAYS)*100,4) if vol>1e-12 else None,
                     "component_volatility_pct":round((contribution or 0)*vol*100,4) if contribution is not None else None,
                     "share_of_portfolio_variance_pct":round(contribution*100,3) if contribution is not None else None})
    optimization=_optimization(symbols,asset_series)
    simulation=_monte_carlo(portfolio,paths=max(250,min(int(paths),5000)),horizon=max(20,min(int(horizon),756)))
    # Market scenario beta is approximated from regression; sector-specific shock uses current mapped sector exposure.
    from sectors import classify
    sector=classify(clean)
    sector_returns=_sector_rotation(histories)
    market_beta=regression.get("coefficients",{}).get("Market",{}).get("beta")
    scenario_defs=[
        ("broad_risk_off","Broad risk-off", -0.20, -0.05),
        ("growth_repricing","Growth repricing", -0.15, 0.00),
        ("rates_shock","Rates shock", -0.08, -0.06),
        ("inflation_energy","Inflation / energy shock", -0.06, 0.10),
        ("liquidity_event","Severe liquidity event", -0.30, -0.12),
    ]
    sector_shocks={"Energy":.10,"Utilities":-.03,"Financials":-.12,"Information Technology":-.18,
                   "Consumer Discretionary":-.15,"Communication Services":-.14,"Health Care":-.06,
                   "Industrials":-.10,"Materials":-.10,"Real Estate":-.15,"Consumer Staples":-.04}
    sector_by_symbol={}
    from sectors import SECTOR_BY_SYMBOL
    for p in clean:
        sector_by_symbol[p["symbol"]]=SECTOR_BY_SYMBOL.get(p["symbol"],"Unclassified")
    exposure={x["sector"]:x["weight_pct"]/100 for x in sector["sectors"]}
    scenarios=[]
    for key,label,market_shock,bond_shock in scenario_defs:
        pnl=sum(weights[p["symbol"]]*sector_shocks.get(sector_by_symbol[p["symbol"]],market_shock) for p in clean)
        if key=="broad_risk_off" and market_beta is not None:
            pnl=sum(weights[s] for s in symbols)*market_shock*market_beta
        scenarios.append({"id":key,"label":label,"portfolio_return_proxy_pct":round(pnl*100,3),
                          "hypothetical_pnl_cents":round(total*pnl),
                          "assumptions":"Static current weights; sector shock map is illustrative, unknown sectors use broad market shock."})
    return {"status":"COMPUTED","as_of":dates[-1],"first_date":dates[0],"last_date":dates[-1],
            "aligned_observations":len(dates),"lookback_calendar_days":days,
            "portfolio_weights_pct":{s:round(v*100,3) for s,v in weights.items()},
            "multi_factor_regression":regression,
            "factor_proxies_excluded_for_coverage":excluded_optional,
            "sector_rotation":sector_returns,
            "optimization":optimization,
            "monte_carlo":simulation,
            "risk_decomposition":{"status":"COMPUTED","annualized_portfolio_volatility_pct":round(vol*100,4),
                                  "contributions":risk,"method":"Euler decomposition of sample covariance; contributions sum to portfolio variance, not volatility."},
            "scenario_report":{"status":"COMPUTED","current_sector_weights":exposure,
                               "scenarios":scenarios,"disclaimer":"Deterministic hypothetical shocks; not forecasts, VaR, stress calibration or investment advice."},
            "methodology":"Current paper holdings and manual marks define weights, held constant over the sample. Historical adjusted-price and corporate-action gaps remain.",
            "limitations":"This is not historical holdings reconstruction. IEX may be incomplete; prices may be unadjusted for dividends/splits. OLS conventional t-statistics are not HAC-robust. Optimization uses sample estimates and randomized candidate search, not a production-grade convex solver. Monte Carlo assumes IID bootstrap resampling and does not model regime changes, fees, taxes or liquidity."}
