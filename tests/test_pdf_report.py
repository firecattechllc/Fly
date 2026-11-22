import unittest
from pdf_report import render

class PdfReportTests(unittest.TestCase):
 def test_pdf_has_valid_signature_and_cross_reference(self):
  report={"status":"DAILY_MARKET_REPLAY","benchmark":"SPY","first_date":"2026-01-01","last_date":"2026-01-31","observations":20,"daily_time_weighted_return_pct":2.1,"benchmark_time_weighted_return_pct":1.2,"active_return_pct":0.9,"max_drawdown_pct":-1.0,"monthly_returns":[{"period":"2026-01","portfolio_return_pct":2.1,"benchmark_return_pct":1.2,"active_return_pct":0.9}],"quarterly_returns":[],"contribution_attribution":[],"scenario_comparison":{"method":"20 session windows"},"method":"daily close","limitations":"IEX sample"}
  pdf=render(report)
  self.assertTrue(pdf.startswith(b'%PDF-1.4'))
  self.assertIn(b'xref',pdf)
  self.assertTrue(pdf.rstrip().endswith(b'%%EOF'))
if __name__=='__main__':unittest.main()
