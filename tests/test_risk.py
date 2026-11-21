import unittest
import risk

class PortfolioRiskTests(unittest.TestCase):
    def test_empty_portfolio_is_all_cash(self):
        state={"cash_cents":10000000,"equity_cents":10000000,"positions":[]}
        r=risk.calculate(state)
        self.assertEqual(r["cash_weight_pct"],100)
        self.assertEqual(r["gross_exposure_cents"],0)
        self.assertEqual(r["largest_position_pct"],0)
        self.assertEqual(r["scenarios"][2]["hypothetical_equity_cents"],10000000)
    def test_concentration_and_stress(self):
        state={"cash_cents":7500000,"equity_cents":10000000,"positions":[{"symbol":"AAPL","qty":100,"last_cents":25000}]}
        r=risk.calculate(state)
        self.assertEqual(r["invested_weight_pct"],25)
        self.assertEqual(r["largest_position_pct"],25)
        self.assertEqual(r["scenarios"][1]["hypothetical_equity_cents"],9750000)
        self.assertEqual(r["scenarios"][2]["hypothetical_loss_cents"],-500000)
    def test_rejects_broken_accounting(self):
        with self.assertRaises(ValueError):
            risk.calculate({"cash_cents":100,"equity_cents":200,"positions":[]})

if __name__ == "__main__":
    unittest.main()
