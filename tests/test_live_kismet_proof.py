"""Mocked Kismet acceptance tests.

These exercise the real live-kismet-proof script and maintained adapter CLI
against a local HTTP server with synthetic credentials. They are CI evidence,
not physical RF or deployed-Kismet evidence.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/live-kismet-proof.py"
TOKEN = "synthetic-live-proof-token"
DEVICE_PATH = "/devices/last-time/-60/devices.json"


class LiveKismetProofTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        devices = json.loads((ROOT / "tests/fixtures/kismet.json").read_text())["devices"]
        self.seen = []
        seen = self.seen

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                if self.path != DEVICE_PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                raw = json.dumps(devices).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}{DEVICE_PATH}"

        directory = Path(self.directory.name)
        self.request = directory / "request.json"
        self.request.write_text(json.dumps({
            "dataset": "lab",
            "receiverId": "mock-kismet",
            "operation": "collect",
            "url": self.url,
            "timeoutSeconds": 2,
        }))
        self.policy = directory / "policy.json"
        self.policy.write_text(json.dumps({"kismetTokenUrls": [self.url]}))

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.assertFalse(self.thread.is_alive())

    def run_script(self, *, token=TOKEN, policy=True, extra=None):
        env = dict(os.environ)
        env.pop("STAR_WPA_KISMET_TOKEN", None)
        env.pop("STAR_WPA_POLICY_FILE", None)
        env.update(NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
        if token is not None:
            env["STAR_WPA_KISMET_TOKEN"] = token
        if policy:
            env["STAR_WPA_POLICY_FILE"] = str(self.policy)
        argv = [sys.executable, str(SCRIPT), "--request", str(self.request)]
        if extra:
            argv.extend(extra)
        return subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)

    def test_mocked_server_exercises_real_live_script_and_canonical_validation(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertTrue(summary["ok"])
        self.assertGreater(summary["documents"], 0)
        self.assertEqual(summary["schemaVersions"], ["0.10.1"])
        self.assertEqual(summary["datasets"], ["lab"])
        self.assertEqual(self.seen, [(DEVICE_PATH, "Bearer " + TOKEN)])
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertNotIn("aa:bb:cc:dd:ee:ff", result.stdout)

    def test_live_script_requires_deployment_env_before_network_io(self):
        for token, policy in ((None, True), (TOKEN, False)):
            with self.subTest(token=token is not None, policy=policy):
                self.seen.clear()
                result = self.run_script(token=token, policy=policy)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("missing deployment credential or policy", result.stderr)
                self.assertEqual(self.seen, [])

    def test_documents_output_is_explicit_private_and_summary_stays_sanitized(self):
        output = Path(self.directory.name) / "documents.json"
        result = self.run_script(extra=["--documents-out", str(output)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        documents = json.loads(output.read_text())
        self.assertTrue(documents)
        self.assertNotIn(TOKEN, output.read_text())
        self.assertNotIn(TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
