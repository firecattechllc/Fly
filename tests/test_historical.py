import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch
import historical
from market_data import MarketDataError

BARS=[
    {"t":"2026-11-17T05:00:00Z","o":100,"h":103,"l":98,"c":102,"v":400},
    {"t":"2026-11-18T05:00:00Z","o":102,"h":105,"l":101,"c":104,"v":600},
    {"t":"2026-11-19T05:00:00Z","o":104,"h":106,"l":102,"c":103,"v":500}
]
class FakeResponse:
    status=200
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return json.dumps(self.payload).encode()

class HistoricalTests(unittest.TestCase):
    def get(self, bars=BARS):
        self.req=None
        def opener(req,timeout):
            self.req=req
            self.assertEqual(timeout,8)
            return FakeResponse({"bars":bars,"symbol":"SPY","next_page_token":None})
        return historical.get_bars("SPY",90,"iex",opener=opener,
            credential_loader=lambda:("fake-key","fake-secret"),
            now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))
    def test_request_is_read_only_bounded(self):
        result=self.get()
        self.assertEqual(self.req.get_method(),"GET")
        self.assertEqual(urlparse(self.req.full_url).path,"/v2/stocks/SPY/bars")
        self.assertEqual(parse_qs(urlparse(self.req.full_url).query)["feed"],["iex"])
        self.assertEqual(parse_qs(urlparse(self.req.full_url).query)["limit"],["400"])
        self.assertEqual(result["bars"][-1]["close"],103)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["broker_connected"])
    def test_research_is_descriptive_only(self):
        result=historical.research(self.get())
        self.assertEqual(result["observations"],3)
        self.assertEqual(result["latest_close"],103)
        self.assertIsNone(result["sma20"])
        self.assertTrue(result["not_ai"])
        self.assertTrue(result["not_investment_advice"])
        self.assertEqual(result["status"],"DESCRIPTIVE_ONLY")
    def test_requires_market_data(self):
        result=historical.research(self.get([]))
        self.assertEqual(result["status"],"INSUFFICIENT_DATA")
    def test_rejects_malformed_bars(self):
        for bars in [
            [{"t":"2026-11-19","o":100,"h":90,"l":98,"c":102,"v":100}],
            [{"t":"2026-11-19","o":True,"h":105,"l":98,"c":102,"v":100}],
            BARS[::-1],
            [{"t":"2026-11-19","o":100,"h":110,"l":90,"c":102,"v":-1}]
        ]:
            with self.assertRaises(MarketDataError):
                self.get(bars)
    def test_invalid_arguments_do_not_access_credentials(self):
        def refuse():
            raise AssertionError("credential loader must not execute")
        for symbol,days,feed in [("BAD/../",90,"iex"),("SPY",999,"iex"),("SPY",10,"sip")]:
            with self.assertRaises(MarketDataError):
                historical.get_bars(symbol,days,feed,credential_loader=refuse)

if __name__=="__main__":unittest.main()
