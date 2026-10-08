import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from star_wpa.adapters import kismet_devices
from star_wpa.couchdb import CouchDB
from star_wpa.effects import run_once
from star_wpa.files import read_bounded
from star_wpa.tools import MAX_OUTPUT, run_tool


class HardeningTests(unittest.TestCase):
    def test_http_redirects_never_forward_credentials_or_follow_location(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get('Authorization')))
                self.send_response(302)
                self.send_header('Location', '/credential-sink')
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        url = f'http://127.0.0.1:{server.server_port}/devices'
        try:
            with patch.dict(os.environ, {'STAR_WPA_KISMET_TOKEN': 'fixture-secret'}):
                with self.assertRaises(HTTPError) as failure:
                    kismet_devices({'url': url}, {'kismetTokenUrls': [url]})
                self.assertEqual(failure.exception.code, 302)
                failure.exception.close()
            with self.assertRaises(HTTPError) as failure:
                CouchDB(url, user='fixture', password='fixture-secret').request('GET')
            self.assertEqual(failure.exception.code, 302)
            failure.exception.close()
            self.assertEqual(len(seen), 2)
            self.assertEqual([entry[0] for entry in seen], ['/devices', '/devices'])
            self.assertEqual(seen[0][1], 'Bearer fixture-secret')
            self.assertTrue(seen[1][1].startswith('Basic '))
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_kismet_cannot_select_secrets_or_unapproved_token_destination(self):
        with patch.dict(os.environ, {'OTHER_SECRET': 'fixture', 'STAR_WPA_KISMET_TOKEN': 'fixture'}), patch('star_wpa.adapters.open_http') as transport:
            with self.assertRaises(PermissionError):
                kismet_devices({'url': 'https://example.com/devices', 'tokenEnv': 'OTHER_SECRET'})
            with self.assertRaises(PermissionError):
                kismet_devices({'url': 'https://example.com/devices'})
            transport.assert_not_called()

    def test_ledger_rejects_symlinks_hardlinks_and_shared_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'; target.touch(mode=0o600)
            ledger = Path(directory) / 'effects.sqlite'
            operation = unittest.mock.Mock(return_value=[])
            with patch.dict(os.environ, {'STAR_WPA_EFFECT_DB': str(ledger)}):
                ledger.symlink_to(target)
                with self.assertRaises(OSError):
                    run_once('fixture', {'dataset': 'lab', 'requestId': '1'}, operation)
                ledger.unlink(); os.link(target, ledger)
                with self.assertRaises(PermissionError):
                    run_once('fixture', {'dataset': 'lab', 'requestId': '1'}, operation)
                ledger.unlink(); ledger.touch(mode=0o644); ledger.chmod(0o644)
                with self.assertRaises(PermissionError):
                    run_once('fixture', {'dataset': 'lab', 'requestId': '1'}, operation)
                operation.assert_not_called()
                self.assertEqual(target.read_bytes(), b'')

    def test_fifo_and_oversized_files_fail_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / 'fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                read_bounded(fifo, 20)
            source = Path(directory) / 'stdin'; source.write_bytes(b'x' * (MAX_OUTPUT + 1))
            for mode in ['headless', 'terminal']:
                with patch('star_wpa.tools.subprocess.Popen') as launch:
                    with self.assertRaises(ValueError):
                        run_tool('/fixture', {'argv': [], 'workingDirectory': directory,
                            'stdinFile': str(source), 'uiMode': mode}, 1)
                    launch.assert_not_called()
            source.write_bytes(b'1234')
            self.assertEqual(read_bounded(source, 4), b'1234')
            with self.assertRaises(ValueError):
                read_bounded(source, 3)

    def test_package_inventory_preserves_exit_status_and_bounds_output(self):
        import sys
        from star_wpa.tools import package_query
        result = package_query([sys.executable, '-c', 'import sys; print("fixture"); sys.exit(7)'])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, 'fixture\n')
        with self.assertRaises(ValueError):
            package_query([sys.executable, '-c', 'import sys; sys.stdout.write("x" * 2000000)'])

    def test_concurrent_request_cannot_duplicate_an_inflight_effect(self):
        from star_wpa.contracts import document
        entered, release = threading.Event(), threading.Event()
        errors, results = [], []
        request = {'dataset': 'lab', 'requestId': 'concurrent'}
        def operation():
            entered.set()
            if not release.wait(5):
                raise TimeoutError('fixture wait')
            return [document('event', 'lab', 'fixture:concurrent')]
        def first():
            try:
                results.append(run_once('fixture', request, operation))
            except Exception as error:
                errors.append(error)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'STAR_WPA_EFFECT_DB': directory + '/ledger'}):
            worker = threading.Thread(target=first); worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(PermissionError):
                    run_once('fixture', request, lambda: self.fail('duplicate execution'))
            finally:
                release.set(); worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 1)
            self.assertEqual(run_once('fixture', request, lambda: self.fail('replay execution')), results[0])
