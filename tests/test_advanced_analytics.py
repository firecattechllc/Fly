import random
import unittest
from datetime import date, timedelta
from advanced_analytics import analyze, _ols

def make_history(seed, count=110, start=100.0):
    rng=random.Random(seed); price=start; bars=[]
    day=date(2026,1,1)
    for i in range(count):
        if i:
            price*=1+rng.gauss(0.0004+seed*0.00001,0.009)
        bars.append({"timestamp":(day+timedelta(days=i)).isoformat()+"T21:00:00Z","close":price})
    return {"bars":bars}

class AdvancedAnalyticsTests(unittest.TestCase):
    def setUp(self):
        from advanced_analytics import FACTOR_LABELS, SECTOR_ETFS
        self.histories={}
        for i,s in enumerate(["AAA","BBB"]+list(FACTOR_LABELS)+list(SECTOR_ETFS)):
            self.histories[s]=make_history(i+1)
        self.positions=[{"symbol":"AAA","qty":5,"last_cents":12000},
                        {"symbol":"BBB","qty":3,"last_cents":8000}]

    def test_all_five_analytics_engines_publish(self):
        result=analyze(self.positions,self.histories,days=365,paths=300,horizon=60)
        self.assertEqual(result["status"],"COMPUTED")
        self.assertEqual(result["multi_factor_regression"]["status"],"COMPUTED")
        self.assertIn("Market",result["multi_factor_regression"]["coefficients"])
        self.assertEqual(result["sector_rotation"]["status"],"COMPUTED")
        self.assertGreaterEqual(len(result["sector_rotation"]["sectors"]),8)
        self.assertEqual(result["optimization"]["status"],"COMPUTED")
        self.assertGreater(result["optimization"]["portfolios_evaluated"],1000)
        self.assertEqual(result["monte_carlo"]["paths"],300)
        self.assertIn("p05",result["monte_carlo"]["maximum_drawdown_percentiles"])
        contributions=result["risk_decomposition"]["contributions"]
        self.assertAlmostEqual(sum(x["share_of_portfolio_variance_pct"] for x in contributions),100,places=2)
        self.assertEqual(len(result["scenario_report"]["scenarios"]),5)

    def test_no_positions_fails_closed(self):
        self.assertEqual(analyze([],self.histories)["status"],"INSUFFICIENT_DATA")

    def test_regression_reports_collinearity(self):
        y=[.01,.02,.03,.04,.05,.06,.07,.08]
        x=[.01,.02,.03,.04,.05,.06,.07,.08]
        result=_ols(y,{"A":x,"B":x},["A","B"])
        self.assertEqual(result["status"],"COLLINEAR_FACTORS")

    def test_optimization_is_long_only_and_deterministic(self):
        a=analyze(self.positions,self.histories,paths=250,horizon=20)
        b=analyze(self.positions,self.histories,paths=250,horizon=20)
        self.assertEqual(a["optimization"],b["optimization"])
        for portfolio in [a["optimization"]["minimum_variance"],a["optimization"]["maximum_sharpe_zero_rf"]]:
            self.assertTrue(all(v>=0 for v in portfolio["weights"].values()))
            self.assertAlmostEqual(sum(portfolio["weights"].values()),100,places=2)

if __name__=="__main__": unittest.main()
