import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from star_wpa.adapters import gpsd_reports, kismet_devices


class ProtocolTests(unittest.TestCase):
    def test_kismet_collect_uses_real_http_json_boundary(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'[{"kismet.device.base.macaddr":"aa:bb:cc:dd:ee:ff"}]')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            result = kismet_devices({'url': f'http://127.0.0.1:{server.server_port}/devices.json', 'timeoutSeconds': 2})
            self.assertEqual(result[0]['kismet.device.base.macaddr'], 'aa:bb:cc:dd:ee:ff')
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_gpsd_watch_and_tpv_collection_use_real_socket(self):
        server = socket.socket()
        server.bind(('127.0.0.1', 0)); server.listen(1)
        seen = []
        def serve():
            with server.accept()[0] as connection:
                seen.append(connection.recv(1024))
                connection.sendall(b'{"class":"VERSION"}\n{"class":"TPV","mode":1}\n{"class":"TPV","mode":3,"lat":0,"lon":0,"time":"2026-01-01T00:00:00Z"}\n')
        thread = threading.Thread(target=serve); thread.start()
        try:
            result = gpsd_reports({'host': '127.0.0.1', 'port': server.getsockname()[1], 'maxReports': 1, 'timeoutSeconds': 2})
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['lat'], 0)
            self.assertEqual(seen[0], b'?WATCH={"enable":true,"json":true};\n')
        finally:
            thread.join(); server.close()
