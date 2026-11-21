import json
import os
import unittest
from unittest.mock import patch
import market_data

class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, n): return json.dumps({"quotes":{"AAPL":{"bp":100.5,"ap":101.0,"t":"2026-11-21T10:00:00Z"}}}).encode()

class DataTests(unittest.TestCase):
    def test_unconfigured_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(market_data.MarketDataError):
            market_data.get_quotes(["AAPL"])
    def test_read_only_and_feed(self):
        with patch.dict(os.environ, {"APCA_API_KEY_ID":"example","APCA_API_SECRET_KEY":"example"}):
            result=market_data.get_quotes(["AAPL"],opener=lambda req,timeout:Response())
            self.assertTrue(result["read_only"])
            self.assertFalse(result["broker_connected"])
            self.assertEqual(result["quotes"][0]["bid"],100.5)
    def test_invalid_symbols_and_feed(self):
        with patch.dict(os.environ, {"APCA_API_KEY_ID":"example","APCA_API_SECRET_KEY":"example"}):
            for s in ["BAD/../", "", "A"*40]:
                with self.assertRaises(market_data.MarketDataError): market_data.get_quotes([s])
            with self.assertRaises(market_data.MarketDataError): market_data.get_quotes(["AAPL"],feed="sip")
if __name__ == "__main__": unittest.main()
