"""Curated sector taxonomy; unknown securities remain unclassified."""
SECTOR_BY_SYMBOL = {
 "AAPL":"Information Technology","MSFT":"Information Technology","NVDA":"Information Technology",
 "AVGO":"Information Technology","ORCL":"Information Technology","CRM":"Information Technology",
 "AMD":"Information Technology","CSCO":"Information Technology","ADBE":"Information Technology",
 "GOOGL":"Communication Services","GOOG":"Communication Services","META":"Communication Services",
 "NFLX":"Communication Services","DIS":"Communication Services",
 "AMZN":"Consumer Discretionary","TSLA":"Consumer Discretionary","HD":"Consumer Discretionary",
 "MCD":"Consumer Discretionary","NKE":"Consumer Discretionary",
 "WMT":"Consumer Staples","COST":"Consumer Staples","KO":"Consumer Staples","PEP":"Consumer Staples",
 "LLY":"Health Care","JNJ":"Health Care","UNH":"Health Care","ABBV":"Health Care","MRK":"Health Care",
 "JPM":"Financials","BAC":"Financials","GS":"Financials","MS":"Financials","V":"Financials","MA":"Financials",
 "XOM":"Energy","CVX":"Energy","COP":"Energy",
 "CAT":"Industrials","GE":"Industrials","HON":"Industrials","UPS":"Industrials",
 "PLD":"Real Estate","AMT":"Real Estate","O":"Real Estate",
 "NEE":"Utilities","DUK":"Utilities","SO":"Utilities",
 "LIN":"Materials","SHW":"Materials","FCX":"Materials",
}
TAXONOMY = "Curated symbol map; review against issuer filings before institutional use"
def classify(positions):
    sectors = {}
    unknown = []
    total = sum(int(p["qty"])*int(p["last_cents"]) for p in positions)
    for p in positions:
        symbol=p["symbol"]; value=int(p["qty"])*int(p["last_cents"])
        sector=SECTOR_BY_SYMBOL.get(symbol)
        if sector is None:
            unknown.append({"symbol":symbol,"market_value_cents":value})
        else:
            sectors[sector]=sectors.get(sector,0)+value
    return {"taxonomy":TAXONOMY,"status":"PARTIAL" if unknown else "CLASSIFIED",
            "sectors":[{"sector":k,"market_value_cents":v,
                        "weight_pct":round(v*100/total,2) if total else 0}
                       for k,v in sorted(sectors.items())],
            "unclassified":unknown,
            "disclaimer":"Ticker-level curated mapping, not a licensed point-in-time GICS feed. ETFs and unknown tickers are not decomposed."}
