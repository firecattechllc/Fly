import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
import app
import auth

PASS = "unittest-owner-password-2026"

class ApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.old_db=app.DB
        cls.old_auth=auth.AUTH_PATH
        app.DB=Path(cls.tmp.name)/"test.db"
        auth.AUTH_PATH=Path(cls.tmp.name)/"owner-auth.json"
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.port=cls.server.server_address[1]
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        app.DB=cls.old_db
        auth.AUTH_PATH=cls.old_auth
        cls.tmp.cleanup()
    def setUp(self):
        auth.AUTH_PATH.unlink(missing_ok=True)
        with auth.LOCK:
            auth.SESSIONS.clear()
            auth.FAILED.clear()
    def request(self,method,path,headers=None,body=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=5)
        h={"Host":"127.0.0.1:"+str(self.port)}
        h.update(headers or {})
        conn.request(method,path,body=body,headers=h)
        response=conn.getresponse()
        raw=response.read()
        result=(response.status,{k.lower():v for k,v in response.getheaders()},raw)
        conn.close()
        return result
    def post_json(self,path,payload,headers=None):
        h={"Content-Type":"application/json"}
        h.update(headers or {})
        return self.request("POST",path,h,json.dumps(payload))
    def setup(self):
        status,headers,body=self.post_json("/api/auth/setup",{"password":PASS})
        self.assertEqual(status,200,body)
        return headers["set-cookie"].split(";",1)[0]
    def test_health_includes_database_integrity(self):
        status,headers,body=self.request("GET","/healthz")
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["database"],"ok")
        self.assertEqual(headers["cache-control"],"no-store")
        self.assertEqual(headers["x-frame-options"],"DENY")
        self.assertEqual(headers["referrer-policy"],"no-referrer")
    def test_host_header_rejected(self):
        status,_,_=self.request("GET","/",{"Host":"untrusted.example"})
        self.assertEqual(status,403)
    def test_unauthenticated_dashboard_redirects_and_api_denies(self):
        status,headers,_=self.request("GET","/")
        self.assertEqual(status,302)
        self.assertEqual(headers["location"],"/auth")
        status,_,_=self.request("GET","/api/state")
        self.assertEqual(status,401)
        status,_,_=self.request("GET","/api/performance")
        self.assertEqual(status,401)
        for endpoint in ("/api/historical?symbol=SPY&days=30", "/api/research?symbol=SPY&days=30"):
            status,_,_=self.request("GET",endpoint)
            self.assertEqual(status,401)
        status,_,_=self.request("GET","/app.js")
        self.assertEqual(status,401)
        status,_,_=self.request("GET","/auth")
        self.assertEqual(status,200)
    def test_setup_cookie_and_csrf(self):
        cookie=self.setup()
        status,headers,body=self.request("GET","/",{"Cookie":cookie})
        self.assertEqual(status,200)
        self.assertIn("default-src 'self'",headers["content-security-policy"])
        self.assertIn(b"FLY",body)
        token=re.search(rb'name="fly-token" content="([^"]+)"',body).group(1).decode()
        self.assertGreater(len(token),30)
        status,_,_=self.post_json("/api/paper-orders",
            {"symbol":"AAPL","side":"BUY","qty":1,"price":"100"},
            {"Cookie":cookie,"X-Fly-Token":"wrong"})
        self.assertEqual(status,403)
        status,_,body=self.post_json("/api/paper-orders",
            {"symbol":"AAPL","side":"BUY","qty":1,"price":"100"},
            {"Cookie":cookie,"X-Fly-Token":token})
        self.assertEqual(status,200,body)
        self.assertFalse(json.loads(body)["broker_connected"])
        status,_,body=self.request("GET","/api/performance",{"Cookie":cookie})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["mode"],"PAPER MARK EVENTS ONLY")
        self.assertEqual(json.loads(body)["observations"],2)
    def test_second_setup_rejected(self):
        self.setup()
        status,_,_=self.post_json("/api/auth/setup",{"password":PASS})
        self.assertEqual(status,400)
    def test_login_lockout(self):
        self.setup()
        for _ in range(5):
            status,_,_=self.post_json("/api/auth/login",{"password":"wrong"})
            self.assertEqual(status,401)
        status,_,_=self.post_json("/api/auth/login",{"password":PASS})
        self.assertEqual(status,429)
    def test_login_and_logout(self):
        cookie=self.setup()
        self.assertEqual(self.post_json("/api/auth/logout",{},{"Cookie":cookie})[0],403)
        status,_,html=self.request("GET","/",{"Cookie":cookie})
        self.assertEqual(status,200)
        csrf=re.search(rb'name="fly-token" content="([^"]+)"',html).group(1).decode()
        status,headers,_=self.post_json("/api/auth/logout",{},{"Cookie":cookie,"X-Fly-Token":csrf})
        self.assertEqual(status,200)
        self.assertIn("Max-Age=0",headers["set-cookie"])
        self.assertEqual(self.request("GET","/api/state",{"Cookie":cookie})[0],401)
        status,headers,_=self.post_json("/api/auth/login",{"password":PASS})
        self.assertEqual(status,200)
        self.assertIn("HttpOnly",headers["set-cookie"])
        self.assertIn("SameSite=Strict",headers["set-cookie"])
    def test_cross_origin_setup_denied(self):
        status,_,_=self.post_json("/api/auth/setup",{"password":PASS},{"Origin":"https://evil.invalid"})
        self.assertEqual(status,403)

if __name__ == "__main__":
    unittest.main()
