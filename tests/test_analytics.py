import unittest
from analytics import calculate

def bars(values):
    return [{"timestamp":f"2026-01-{i+1:02d}T05:00:00Z","close":v} for i,v in enumerate(values)]

class AnalyticsTests(unittest.TestCase):
    def test_beta_correlation_and_drawdown(self):
        market=[100,102,101,104,100,105]
        stock=[100,104,102,108,100,110]
        result=calculate([{"symbol":"ABC","qty":1,"last_cents":10000}],
                         {"ABC":{"bars":bars(stock)},"SPY":{"bars":bars(market)}})
        self.assertEqual(result["status"],"DESCRIPTIVE_PROXY")
        self.assertEqual(result["aligned_observations"],5)
        self.assertAlmostEqual(result["beta_vs_benchmark"],1.9673,places=3)
        self.assertAlmostEqual(result["correlation_to_benchmark"]["ABC"],1.0,places=3)
        self.assertLess(result["max_drawdown_pct"],0)
        self.assertEqual(result["current_weights_used"],{"ABC":100.0})
    def test_requires_three_aligned_returns(self):
        result=calculate([{"symbol":"ABC","qty":1,"last_cents":10000}],
                         {"ABC":{"bars":bars([100,101,102])},"SPY":{"bars":bars([100,99,100])}})
        self.assertEqual(result["status"],"INSUFFICIENT_DATA")
    def test_no_positions_reports_insufficient(self):
        result=calculate([],{"SPY":{"bars":bars([100,101,102,103])}})
        self.assertEqual(result["status"],"INSUFFICIENT_DATA")
    def test_sector_data_is_never_guessed(self):
        result=calculate([{"symbol":"ABC","qty":1,"last_cents":10000}],
                         {"ABC":{"bars":bars([100,101,102,103])},"SPY":{"bars":bars([100,101,102,103])}})
        self.assertEqual(result["sector_exposure"]["status"],"UNCLASSIFIED")
if __name__=="__main__":unittest.main()
