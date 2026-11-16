"""The control panel must answer only its own local page, not other websites."""
import http.client
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import panou


class PanelLocalGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), panou.Handler)
        cls.port = cls.server.server_address[1]
        cls.old_port = panou.PANEL_PORT
        panou.PANEL_PORT = cls.port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        panou.PANEL_PORT = cls.old_port

    def status(self, method, path, host=None, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader('Host', host or f'127.0.0.1:{self.port}')
        if origin:
            conn.putheader('Origin', origin)
        if method == 'POST':
            conn.putheader('Content-Length', '2')
            conn.endheaders(b'{}')
        else:
            conn.endheaders()
        code = conn.getresponse().status
        conn.close()
        return code

    # An unknown path is used on purpose: it reaches the router (404) without touching settings.
    def test_own_page_is_served(self):
        self.assertEqual(self.status('GET', '/nu-exista'), 404)
        self.assertEqual(self.status('POST', '/api/nu-exista', origin=f'http://127.0.0.1:{self.port}'), 404)
        self.assertEqual(self.status('GET', '/nu-exista', host=f'localhost:{self.port}'), 404)

    def test_foreign_host_is_refused(self):
        self.assertEqual(self.status('GET', '/api/log', host=f'evil.example:{self.port}'), 403)
        self.assertEqual(self.status('POST', '/api/key', host=f'evil.example:{self.port}'), 403)

    def test_foreign_origin_is_refused(self):
        self.assertEqual(self.status('POST', '/api/key', origin='https://evil.example'), 403)
        self.assertEqual(self.status('POST', '/api/telegram/approve', origin='https://evil.example'), 403)
        self.assertEqual(self.status('GET', '/api/settings', origin='https://evil.example'), 403)


if __name__ == '__main__':
    unittest.main()
