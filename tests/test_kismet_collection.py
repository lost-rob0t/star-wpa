"""Real CLI/HTTP fixture tests, not deployed Kismet or physical RF proof."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from star_wpa.contracts import validate_bundle


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-kismet-token"
DEVICE_PATH = "/devices/last-time/-60/devices.json"


class KismetCollectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.seen = []
        devices = json.loads((ROOT / "tests/fixtures/kismet.json").read_text())["devices"]
        seen = self.seen
        redirects = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization"), self.headers.get("Cookie")))
                if self.path in redirects:
                    status, location = redirects[self.path]
                    self.send_response(status)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
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

        self.servers = []
        for _ in range(2):
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            self.servers.append(server)
            self.addCleanup(self.stop_server, server, thread)
        self.origin = f"http://127.0.0.1:{self.servers[0].server_port}"
        self.sink = f"http://127.0.0.1:{self.servers[1].server_port}"
        self.url = self.origin + DEVICE_PATH
        self.redirects = redirects
        self.request = dict(dataset="lab", receiverId="fixture-kismet", operation="collect",
                            url=self.url, timeoutSeconds=2)

    def stop_server(self, server, thread):
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        self.assertFalse(thread.is_alive())

    def collect(self, *, request=None, policy=None, token=TOKEN, policy_text=None, proxy=None):
        directory = Path(self.directory.name)
        request_path = directory / "request.json"
        request_path.write_text(json.dumps(self.request if request is None else request))
        env = dict(os.environ)
        # Never reuse a developer/deployment credential or policy in fixture tests.
        for key in ("STAR_WPA_POLICY_FILE", "STAR_WPA_KISMET_TOKEN"):
            env.pop(key, None)
        env.update(NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
                   OTHER_SECRET="synthetic-unrelated-secret")
        if proxy is not None:
            env.update(HTTP_PROXY=proxy, http_proxy=proxy, NO_PROXY="", no_proxy="")
        if token is not None:
            env["STAR_WPA_KISMET_TOKEN"] = token
        if policy is not None or policy_text is not None:
            policy_path = directory / "policy.json"
            policy_path.write_text(json.dumps(policy) if policy_text is None else policy_text)
            env["STAR_WPA_POLICY_FILE"] = str(policy_path)
        result = subprocess.run([sys.executable, "-m", "star_wpa", "kismet", "--request", str(request_path)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=8)
        for secret in (TOKEN, "synthetic-unrelated-secret", token):
            if secret:
                self.assertNotIn(secret, result.stdout + result.stderr)
        return result

    def assert_denied(self, result, error="PermissionError"):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, f"star-wpa adapter failed: {error}\n")
        self.assertEqual(self.seen, [])

    def assert_collected(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        docs = json.loads(result.stdout)
        validate_bundle(docs)
        networks = [doc for doc in docs if doc["dtype"] == "wireless-network"]
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["bssid"], "aa:bb:cc:dd:ee:ff")
        self.assertTrue(all(doc["schemaVersion"] == "0.10.1" for doc in docs))
        return docs

    def test_cli_loads_exact_destination_from_local_policy_and_emits_canonical_docs(self):
        self.assert_collected(self.collect(policy={"kismetTokenUrls": [self.url]}))
        self.assertEqual(self.seen, [(DEVICE_PATH, "Bearer " + TOKEN, None)])

    def test_direct_kismet_examples_load_cookie_mode_from_operator_policy(self):
        request = json.loads((ROOT / "examples/kismet-collect.json").read_text())
        policy = json.loads((ROOT / "examples/kismet-policy.json").read_text())
        self.assertEqual(policy["kismetTokenUrls"], [request["url"]])
        self.assertEqual(request["url"].split(":2501", 1)[1], DEVICE_PATH)
        request["url"] = self.url
        policy["kismetTokenUrls"] = [self.url]
        docs = self.assert_collected(self.collect(request=request, policy=policy))
        self.assertTrue(all(doc["dataset"] == request["dataset"] for doc in docs))
        self.assertEqual(self.seen, [(DEVICE_PATH, None, "KISMET=" + TOKEN)])

    def test_missing_and_malformed_allowlists_fail_before_network_io(self):
        for policy in (None, {}, {"kismetTokenUrls": []}, {"kismetTokenUrls": self.url},
                       {"kismetTokenUrls": None}, {"kismetTokenUrls": {self.url: True}}):
            with self.subTest(policy=policy):
                self.assert_denied(self.collect(policy=policy))

    def test_allowlist_is_exact_including_path_query_host_port_and_scheme(self):
        wrong_urls = [self.origin, self.url + "/", self.url + "?view=all",
                      self.url.replace("127.0.0.1", "localhost"), self.sink + DEVICE_PATH,
                      self.url.replace("http:", "https:"), self.origin + "/devices/*"]
        for url in wrong_urls:
            with self.subTest(url=url):
                self.assert_denied(self.collect(policy={"kismetTokenUrls": [url]}))

    def test_request_cannot_supply_allowlist_or_select_environment_secrets(self):
        for extra in ({"kismetTokenUrls": [self.url]}, {"policy": {"kismetTokenUrls": [self.url]}},
                      {"tokenEnv": "OTHER_SECRET"}):
            with self.subTest(extra=extra):
                request = dict(self.request, **extra)
                policy = {"kismetTokenUrls": [self.url]} if "tokenEnv" in extra else {}
                self.assert_denied(self.collect(request=request, policy=policy))
        self.assert_denied(self.collect(request=dict(self.request, tokenEnv="OTHER_SECRET"),
                                       policy={"kismetTokenUrls": [self.url]}, token=None))

    def test_request_cannot_override_operator_cookie_authentication(self):
        request = dict(self.request, kismetTokenAuth="bearer")
        policy = {"kismetTokenUrls": [self.url], "kismetTokenAuth": "cookie"}
        self.assert_collected(self.collect(request=request, policy=policy))
        self.assertEqual(self.seen, [(DEVICE_PATH, None, "KISMET=" + TOKEN)])

    def test_unknown_auth_and_unsafe_cookie_tokens_fail_before_network_io(self):
        self.assert_denied(self.collect(policy={"kismetTokenUrls": [self.url], "kismetTokenAuth": "query"}),
                           error="ValueError")
        policy = {"kismetTokenUrls": [self.url], "kismetTokenAuth": "cookie"}
        for token in ("fixture;extra=value", "fixture\r\nHeader:value", "fixture token",
                      'fixture"quoted', "fixture,other", "fixture\\escape", "fixture\u007f", "fixture\u00e9"):
            with self.subTest(token=repr(token)):
                self.assert_denied(self.collect(policy=policy, token=token), error="ValueError")

    def test_redirects_fail_without_contacting_even_allowlisted_destination(self):
        for auth in ("bearer", "cookie"):
            for code in (301, 302, 303, 307, 308):
                for target in (self.url, self.sink + DEVICE_PATH):
                    with self.subTest(auth=auth, code=code, target=target):
                        path = f"/redirect/{code}"
                        self.redirects[path] = (code, target)
                        source = self.origin + path
                        policy = {"kismetTokenUrls": [source, target], "kismetTokenAuth": auth}
                        self.seen.clear()
                        result = self.collect(request=dict(self.request, url=source), policy=policy)
                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(result.stdout, "")
                        self.assertEqual(result.stderr, "star-wpa adapter failed: HTTPError\n")
                        expected = (path, "Bearer " + TOKEN, None) if auth == "bearer" else (path, None, "KISMET=" + TOKEN)
                        self.assertEqual(self.seen, [expected])

    def test_authenticated_plaintext_remote_http_rejected_before_io(self):
        url = "http://192.0.2.1:2501" + DEVICE_PATH
        for auth in ("bearer", "cookie"):
            with self.subTest(auth=auth):
                request = dict(self.request, url=url)
                policy = {"kismetTokenUrls": [url], "kismetTokenAuth": auth}
                self.assert_denied(self.collect(request=request, policy=policy))

    def test_tokened_loopback_bypasses_untrusted_environment_proxy(self):
        policy = {"kismetTokenUrls": [self.url], "kismetTokenAuth": "cookie"}
        self.assert_collected(self.collect(policy=policy, proxy=self.sink))
        self.assertEqual(self.seen, [(DEVICE_PATH, None, "KISMET=" + TOKEN)])

    def test_localhost_hostname_cannot_bypass_plaintext_protection(self):
        url = "http://localhost:2501" + DEVICE_PATH
        policy = {"kismetTokenUrls": [url], "kismetTokenAuth": "cookie"}
        request = dict(self.request, url=url)
        self.assert_denied(self.collect(request=request, policy=policy))

    def test_unset_token_collects_without_authentication_or_allowlist(self):
        self.assert_collected(self.collect(token=None))
        self.assertEqual(self.seen, [(DEVICE_PATH, None, None)])

    def test_invalid_or_missing_policy_file_fails_closed(self):
        self.assert_denied(self.collect(policy_text="{malformed"), error="JSONDecodeError")
        self.assert_denied(self.collect(policy_text="null"))
        directory = Path(self.directory.name)
        request_path = directory / "request.json"
        request_path.write_text(json.dumps(self.request))
        env = dict(os.environ, STAR_WPA_POLICY_FILE=str(directory / "does-not-exist.json"),
                   STAR_WPA_KISMET_TOKEN=TOKEN)
        result = subprocess.run([sys.executable, "-m", "star_wpa", "kismet", "--request", str(request_path)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=8)
        self.assert_denied(result, error="FileNotFoundError")
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
