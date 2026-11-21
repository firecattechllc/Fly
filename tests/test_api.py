import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
import app

class ApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.old_db=app.DB
        app.DB=Path(cls.tmp.name)/"test.db"
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
        cls.tmp.cleanup()
    def request(self,method,path,headers=None,body=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=3)
        conn.request(method,path,body=body,headers=headers or {})
        response=conn.getresponse()
        data=response.read()
        result=(response.status,{k.lower():v for k,v in response.getheaders()},data)
        conn.close()
        return result
    def test_health_includes_database_integrity(self):
        status,headers,body=self.request("GET","/healthz")
        self.assertEqual(status,200)
        self.assertEqual(__import__("json").loads(body)["database"],"ok")
        self.assertEqual(headers["cache-control"],"no-store")
        self.assertEqual(headers["x-frame-options"],"DENY")
        self.assertEqual(headers["referrer-policy"],"no-referrer")
    def test_host_header_rejected(self):
        status,_,_=self.request("GET","/",{"Host":"untrusted.example"})
        self.assertEqual(status,403)
    def test_dashboard_has_strict_csp(self):
        status,headers,body=self.request("GET","/")
        self.assertEqual(status,200)
        self.assertIn("default-src 'self'",headers["content-security-policy"])
        self.assertIn(b"FLY",body)
    def test_order_requires_csrf_token(self):
        status,_,_=self.request("POST","/api/paper-orders",{"Content-Type":"application/json","Content-Length":"2"},"{}")
        self.assertEqual(status,403)

if __name__ == "__main__":
    unittest.main()
