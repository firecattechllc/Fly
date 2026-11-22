"""Minimal dependency-free PDF renderer for FLY paper performance reports."""
def render(report):
    lines=[
      "FLY | PAPER PORTFOLIO PERFORMANCE REPORT",
      "Generated UTC: "+report.get("generated_utc",""),
      "Status: "+report.get("status",""),
      "Benchmark: "+report.get("benchmark","SPY"),
      "Period: "+report.get("first_date","—")+" to "+report.get("last_date","—"),
      "Observations: "+str(report.get("observations",0)),
      "Portfolio TWR: "+str(report.get("daily_time_weighted_return_pct","—"))+"%",
      "Benchmark TWR: "+str(report.get("benchmark_time_weighted_return_pct","—"))+"%",
      "Active return: "+str(report.get("active_return_pct","—"))+"%",
      "Maximum drawdown: "+str(report.get("max_drawdown_pct","—"))+"%",
      "Portfolio annualized volatility: "+str(report.get("risk_metrics",{}).get("portfolio_annualized_volatility_pct","—"))+"%",
      "Benchmark annualized volatility: "+str(report.get("risk_metrics",{}).get("benchmark_annualized_volatility_pct","—"))+"%",
      "Annualized tracking error: "+str(report.get("risk_metrics",{}).get("annualized_tracking_error_pct","—"))+"%",
      "Information ratio: "+str(report.get("risk_metrics",{}).get("information_ratio","—")),
      "Sharpe ratio (zero risk-free proxy): "+str(report.get("risk_metrics",{}).get("sharpe_ratio_zero_rf","—")),
      "Sortino ratio (zero MAR proxy): "+str(report.get("risk_metrics",{}).get("sortino_ratio_zero_mar","—")),
      "Annualized downside deviation: "+str(report.get("risk_metrics",{}).get("downside_deviation_annualized_pct","—"))+"%",
      "",
      "PORTFOLIO TEAR SHEET",
      "Opening equity cents: "+str(report.get("tear_sheet",{}).get("opening_equity_cents","—")),
      "Ending equity cents: "+str(report.get("tear_sheet",{}).get("ending_equity_cents","—")),
      "Ending cash cents: "+str(report.get("tear_sheet",{}).get("ending_cash_cents","—")),
      "Ending market value cents: "+str(report.get("tear_sheet",{}).get("ending_market_value_cents","—")),
      "Open positions: "+str(report.get("tear_sheet",{}).get("position_count","—")),
      "",
      "MONTHLY RETURNS"
    ]
    for x in report.get("monthly_returns",[]):
        lines.append(f'{x["period"]}: portfolio {x["portfolio_return_pct"]}% | benchmark {x["benchmark_return_pct"]}% | active {x["active_return_pct"]}%')
    lines += ["","QUARTERLY RETURNS"]
    for x in report.get("quarterly_returns",[]):
        lines.append(f'{x["period"]}: portfolio {x["portfolio_return_pct"]}% | benchmark {x["benchmark_return_pct"]}% | active {x["active_return_pct"]}%')
    lines += ["","SECTOR EXPOSURE"]
    for x in report.get("sector_exposure",{}).get("sectors",[]):
        lines.append(f'{x["sector"]}: {x["weight_pct"]}% | market value cents {x["market_value_cents"]}')
    for x in report.get("sector_exposure",{}).get("unclassified",[]):
        lines.append(f'UNCLASSIFIED {x["symbol"]}: {x["market_value_cents"]} cents')
    lines += ["","SECTOR CONTRIBUTION"]
    for x in report.get("sector_contribution",[]):
        lines.append(f'{x["sector"]}: {x["contribution_pct_baseline"]}% baseline-equity contribution')
    lines += ["","FACTOR PROXY EXPOSURE"]
    for x in report.get("factor_exposures",[]):
        lines.append(f'{x["factor"]} ({x["symbol"]}): beta {x["beta"]} | correlation {x["correlation"]} | n={x["observations"]}')
    lines += ["","CONTRIBUTION ATTRIBUTION"]
    for x in report.get("contribution_attribution",[]):
        lines.append(f'{x["symbol"]}: {x["contribution_pct_equity"]}% of baseline equity')
    scenario=report.get("scenario_comparison",{})
    lines += ["","HISTORICAL SCENARIO COMPARISON ("+scenario.get("method","")+")"]
    for label in ("best","worst"):
        x=scenario.get(label)
        if x: lines.append(f'{label.upper()} {x["start"]} to {x["end"]}: portfolio {x["portfolio_return_pct"]}% | benchmark {x["benchmark_return_pct"]}% | active {x["active_return_pct"]}%')
    lines += ["","METHODOLOGY",report.get("method",""),"LIMITATIONS",report.get("limitations",""),
              "SIMULATION ONLY — NOT A BROKERAGE STATEMENT OR INVESTMENT ADVICE"]
    def esc(s):
        return str(s).encode("ascii","replace").decode().replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
    pages=[lines[i:i+48] for i in range(0,len(lines),48)] or [["FLY PAPER REPORT"]]
    objects=[]
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    page_ids=[]
    for idx,chunk in enumerate(pages):
        page_id=3+idx*2; content_id=page_id+1; page_ids.append(f"{page_id} 0 R")
        stream="BT /F1 9 Tf 48 790 Td 12 TL "+" ".join(f"({esc(line)}) Tj T*" for line in chunk)+" ET"
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {content_id} 0 R >>")
        objects.append(f"<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream")
    objects.insert(1,"<< /Type /Pages /Kids ["+" ".join(page_ids)+f"] /Count {len(page_ids)} >>")
    out=bytearray(b"%PDF-1.4\n%FLY\n"); offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(out));out.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref=len(out);out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(out)
