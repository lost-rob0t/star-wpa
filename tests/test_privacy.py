"""All inputs are synthetic; never load operator captures or personal locations."""
import csv
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

from star_wpa.privacy import (
    Box, EARTH_METERS, HEADER_9, HEADER_11, HEADER_14, MAX_BYTES, Observation,
    OUTPUT_HEADER, PrivacyError, export_new, observation, parse_source, read_source,
    render_csv, sanitize,
)
from star_wpa.privacy_ui import make_server


def wigle(header=HEADER_14, rows=None, preamble=True):
    values = dict(zip(HEADER_14, ["02:00:00:00:00:01", 'PRIVATE,"name"\nline', "[WPA2]",
                      "2026-01-01 00:00:01", "1", "2412", "-50", "10.12345", "20.54321",
                      "123", "5", "DEADBEEF", "", "WIFI"]))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    if preamble:
        writer.writerow(["WigleWifi-1.6" if header == HEADER_14 else "WigleWifi-1.4",
                         'model=PRIVATE,phone', "device=PRIVATE-device", "star=Sol", "body=3", "subBody=0"])
    writer.writerow(header)
    for row in rows or [values]:
        writer.writerow([row.get(k, values.get(k, "")) for k in header])
    return stream.getvalue().encode()


def warstar(**changes):
    sample = {"id": 1, "address": "02:00:00:00:00:01", "time": 1700000000123,
              "radio": "WIFI", "latitude": 10.12345, "longitude": 20.54321,
              "level": -50, "name": "PRIVATE-name", "security": "WPA2", "frequency": 2412}
    sample.update(changes)
    return json.dumps({"dataset": "PRIVATE-dataset", "device_id": "PRIVATE-device",
                       "observations": [sample]}).encode()


class ParsingTests(unittest.TestCase):
    def test_documented_csv_variants_and_quoted_embedded_newline(self):
        for header in (HEADER_9, HEADER_11, HEADER_14):
            for preamble in (False, True):
                with self.subTest(columns=len(header), preamble=preamble):
                    rows = parse_source(wigle(header, preamble=preamble), "wigle")
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].radio, "WIFI")
                    self.assertEqual(rows[0].latitude, 10.12345)

    def test_warstar_and_existing_zero_fixture(self):
        self.assertEqual(parse_source(warstar(), "warstar")[0].signal_dbm, -50)
        source = Path(__file__).parent / "fixtures/wardrive.json"
        self.assertEqual(parse_source(source.read_bytes(), "warstar")[0].latitude, 0)
        for radio in ("W", "B", "BLUETOOTH", "BLE"):
            self.assertIn(parse_source(warstar(radio=radio), "warstar")[0].radio, {"WIFI", "BT", "BLE"})

    def test_invalid_coordinates(self):
        for key, bad in [("latitude", 91), ("latitude", -91), ("longitude", 181), ("longitude", -181),
                         ("latitude", float("nan")), ("longitude", float("inf")), ("latitude", True),
                         ("longitude", None), ("latitude", "10"), ("latitude", 10**400)]:
            with self.subTest(key=key, bad=str(bad)[:20]), self.assertRaises(PrivacyError):
                parse_source(warstar(**{key: bad}), "warstar")
        for value in ("nan", "Infinity", "1e999", "-91", " 10", "", "1_0"):
            with self.subTest(csv=value), self.assertRaises(PrivacyError):
                parse_source(wigle(rows=[{"CurrentLatitude": value}]), "wigle")

    def test_malformed_utf8_and_control_bytes(self):
        for raw in (b"\xff", b"", wigle() + b"\x00", b"x" * (MAX_BYTES + 1)):
            with self.assertRaises(PrivacyError):
                parse_source(raw, "wigle")
        self.assertEqual(len(parse_source(b"\xef\xbb\xbf" + wigle(), "wigle")), 1)

    def test_headers_width_quotes_and_preamble(self):
        bad = [wigle(HEADER_14 + ("SSID",)), wigle(HEADER_14 + ("HiddenRawBlob",)),
               wigle(tuple(reversed(HEADER_14))), wigle().replace(b"WigleWifi-1.6", b"WigleWifi-9.9"),
               wigle().replace(b"body=3", b"body=4"), wigle().replace(b"body=3", b"body=3,body=3"),
               wigle().replace(b"WigleWifi-1.6", b"WigleWifi-1.4"),
               wigle().replace(b",WIFI\r\n", b",WIFI,extra\r\n"),
               wigle().replace(b",WIFI\r\n", b"\r\n"),
               wigle().replace(b"[WPA2]", b'bad"quote'),
               wigle().replace(b'"PRIVATE,', b'"unclosed"junk,'),
               wigle() + b"\n", b'"unclosed', b"MAC,SSID\n"]
        for raw in bad:
            with self.subTest(raw=raw[:30]), self.assertRaises(PrivacyError):
                parse_source(raw, "wigle")

    def test_csv_removed_fields_are_still_validated(self):
        for field, value in [("FirstSeen", "2026-02-30 00:00:00"), ("FirstSeen", "yesterday"),
                             ("MAC", "PRIVATE"), ("RSSI", "nan"), ("Channel", ""),
                             ("AltitudeMeters", "Infinity"), ("AccuracyMeters", "-1"),
                             ("Type", "PRIVATE-radio"), ("MfgrId", "formula"), ("Frequency", "a")]:
            with self.subTest(field=field), self.assertRaises(PrivacyError):
                parse_source(wigle(rows=[{field: value}]), "wigle")

    def test_cell_and_bluetooth_rows(self):
        for radio in ("CDMA", "GSM", "WCDMA", "LTE", "NR"):
            self.assertEqual(parse_source(wigle(rows=[{"Type": radio, "MAC": "001001_2_3", "Channel": ""}]), "wigle")[0].radio, radio)
        self.assertEqual(parse_source(wigle(rows=[{"Type": "BLE", "Channel": "0", "Frequency": "", "MfgrId": "72"}]), "wigle")[0].radio, "BLE")

    def test_json_unknown_duplicate_hidden_and_malformed(self):
        base = json.loads(warstar())
        cases = [[], {}, dict(base, raw="PRIVATE"), dict(base, observations=[]),
                 dict(base, observations=[dict(base["observations"][0], track="PRIVATE")])]
        for case in cases:
            with self.assertRaises(PrivacyError):
                parse_source(json.dumps(case).encode(), "warstar")
        for raw in [warstar().replace(b'"id": 1', b'"id": 1, "id": 2'), b'{', b'{}{}', b'[' * 1500]:
            with self.assertRaises(PrivacyError):
                parse_source(raw, "warstar")
        for key, value in [("id", True), ("id", 0), ("time", -1), ("time", "123"),
                           ("radio", []), ("level", -201), ("name", {}), ("frequency", "nan"), ("frequency", "2412")]:
            with self.assertRaises(PrivacyError):
                parse_source(warstar(**{key: value}), "warstar")


class GeometryTests(unittest.TestCase):
    def test_inclusive_boundaries(self):
        box = Box(10, 20, 11, 21, 0)
        for lat in (10, 10.5, 11):
            for lon in (20, 20.5, 21):
                self.assertTrue(box.contains(lat, lon))
        self.assertFalse(box.contains(9.99999, 20))
        self.assertFalse(box.contains(10, 21.00001))

    def test_antimeridian_and_equivalent_endpoints(self):
        box = Box(-1, 179, 1, -179, 0)
        for lon in (179, 180, -180, -179):
            self.assertTrue(box.contains(0, lon))
        self.assertFalse(box.contains(0, 0))
        self.assertTrue(Box(-1, 180, 1, 180, 0).contains(0, -180))
        self.assertTrue(Box(-1, -180, 1, 180, 0).contains(0, 0))

    def test_meter_buffer_and_poles(self):
        delta = math.degrees(100 / EARTH_METERS)
        box = Box(0, 0, 0, 0, 100)
        self.assertTrue(box.contains(delta, 0))
        self.assertTrue(box.contains(0, delta))
        self.assertFalse(box.contains(delta * 1.01, 0))
        for lon in (-180, -90, 0, 90, 180):
            self.assertTrue(Box(89.9999, 10, 89.9999, 10, 100).contains(90, lon))
            self.assertTrue(Box(-90, 10, -89, 11, 0).contains(-90, lon))
            self.assertTrue(Box(0, 0, 0, 0, math.pi * EARTH_METERS).contains(-90, lon))
        self.assertTrue(Box(-1, 179.9999, 1, 179.9999, 100).contains(0, -180))

    def test_spherical_buffer_conservative_for_bearings(self):
        # Independent destination-point formula checks polar and date-line expansion.
        distance = 2500 / EARTH_METERS
        for lat, lon in [(0, 0), (80, 179.99), (-80, -179.99), (89.99, 40)]:
            box = Box(lat, lon, lat, lon, 2500)
            phi, lam = math.radians(lat), math.radians(lon)
            for bearing in range(0, 360, 5):
                theta = math.radians(bearing)
                p = math.asin(math.sin(phi) * math.cos(distance) + math.cos(phi) * math.sin(distance) * math.cos(theta))
                l = lam + math.atan2(math.sin(theta) * math.sin(distance) * math.cos(phi), math.cos(distance) - math.sin(phi) * math.sin(p))
                self.assertTrue(box.contains(math.degrees(p), (math.degrees(l) + 180) % 360 - 180))

    def test_invalid_boxes_and_precision(self):
        for args in [(2, 0, 1, 0), (0, 181, 1, 0), (0, 0, 1, 1, -1), (0, 0, 1, 1, float("nan"))]:
            with self.assertRaises(PrivacyError):
                Box(*args)
        for precision in (-1, 7, True, "2"):
            with self.assertRaises(PrivacyError):
                sanitize([], decimals=precision)

    def test_coarsening_cannot_move_into_protected_box(self):
        rows = [observation(10.004, 20.004, "WIFI", -50)]
        self.assertEqual(sanitize(rows, [Box(10, 20, 10, 20, 0)]), ((), 1))

    def test_allowlist_order_multiplicity_and_metadata_removal(self):
        source = parse_source(wigle(rows=[{}, {"CurrentLatitude": "11", "RSSI": "-40"}, {}]), "wigle")
        a, count = sanitize(source)
        b, _ = sanitize(tuple(reversed(source)))
        self.assertEqual(render_csv(a), render_csv(b))
        self.assertEqual(len(a), 2)
        self.assertEqual(count, 0)
        result = list(csv.DictReader(io.StringIO(render_csv(a).decode())))
        self.assertEqual(tuple(result[0]), OUTPUT_HEADER)
        self.assertEqual(result[0]["latitude"], "10.120000")
        for marker in (b"PRIVATE", b"FirstSeen", b"2026", b"02:00", b"DEADBEEF", b"Wigle", b"device", b"time", b"track", b"source", b"buffer", b"123"):
            self.assertNotIn(marker, render_csv(a))
        self.assertEqual(render_csv(sanitize(parse_source(warstar(), "warstar"))[0]), render_csv(a[:1]))

    def test_zero_sign_and_pole_longitude_do_not_reveal_source_order(self):
        rows = [observation(-0.0, 180, "WIFI", -50), observation(0.0, -180, "WIFI", -50),
                observation(90, 130, "WIFI", -50), observation(90, -130, "WIFI", -50)]
        self.assertEqual(render_csv(sanitize(rows)[0]), render_csv(sanitize(rows[::-1])[0]))
        self.assertEqual(len(sanitize(rows)[0]), 2)


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.csv"
        self.original = wigle()
        self.source.write_bytes(self.original)
        self.rows = sanitize(parse_source(read_source(self.source), "wigle"))[0]

    def test_new_copy_original_bytes_and_permissions(self):
        out = self.root / "sanitized.csv"
        export_new(out, self.rows)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(out.read_bytes(), render_csv(self.rows))
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
        self.assertNotIn(b"PRIVATE", out.read_bytes())

    def test_existing_source_output_and_hardlink_refused(self):
        link = self.root / "hardlink"
        os.link(self.source, link)
        for path in (self.source, link):
            with self.assertRaises(FileExistsError):
                export_new(path, self.rows)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_symlink_sources_destinations_and_parents(self):
        target = self.root / "target"
        target.symlink_to(self.source)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "absent")
        parent = self.root / "parent"
        parent.symlink_to(self.root, target_is_directory=True)
        for path in (target, parent / "source.csv", parent / ".." / "source.csv"):
            with self.assertRaises((OSError, PrivacyError)):
                read_source(path)
        for path in (target, dangling, parent / "new.csv"):
            with self.assertRaises((OSError, PrivacyError)):
                export_new(path, self.rows)
        self.assertFalse((self.root / "new.csv").exists())
        self.assertFalse((self.root / "absent").exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_nonregular_and_oversized_source(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for path in (fifo, self.root):
            with self.assertRaises((OSError, PrivacyError)):
                read_source(path)
        big = self.root / "big"
        with big.open("wb") as stream:
            stream.truncate(MAX_BYTES + 1)
        with self.assertRaises(PrivacyError):
            read_source(big)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "sanitized.csv"
        self.server = make_server(parse_source(wigle(), "wigle"), self.output)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.host = f"127.0.0.1:{self.server.server_port}"
        status, headers, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.page = page.decode()
        self.token = re.search(r"const token='([^']+)'", self.page)[1]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, payload=None, **extra):
        headers = {"Host": self.host}
        if method == "POST":
            headers.update({"Origin": "http://" + self.host, "X-Privacy-Token": getattr(self, "token", ""), "Content-Type": "application/json"})
        headers.update(extra)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, None if payload is None else json.dumps(payload), headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_loopback_host_origin_token_and_no_cors(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        payload = {"boxes": [], "decimals": 2}
        for extra in ({"Host": "evil.test"}, {"Origin": "https://evil.test"}, {"Origin": "null"},
                      {"X-Privacy-Token": "bad"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("POST", "/preview", payload, **extra)[0], 403)
        self.assertEqual(self.request("GET", "/", Host="evil.test")[0], 403)
        self.assertEqual(self.request("GET", "/?private=data")[0], 404)
        _, headers, _ = self.request("GET", "/")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        for marker in ("localStorage", "sessionStorage", "indexedDB", "https://", "PRIVATE"):
            self.assertNotIn(marker, self.page)

    def test_preview_then_exact_export_and_repeated_refusal(self):
        self.assertEqual(self.request("POST", "/export", {"preview_id": "bad"})[0], 400)
        status, _, response = self.request("POST", "/preview", {"boxes": [], "decimals": 2})
        self.assertEqual(status, 200)
        preview = json.loads(response)
        self.assertEqual((preview["total"], preview["retained"]), (1, 1))
        self.assertFalse(self.output.exists())
        self.assertNotIn(b"PRIVATE", response)
        request = {"preview_id": preview["preview_id"]}
        self.assertEqual(self.request("POST", "/export", request)[0], 200)
        self.assertNotIn(b"PRIVATE", self.output.read_bytes())
        self.assertEqual(self.request("POST", "/export", request)[0], 400)
        preview = json.loads(self.request("POST", "/preview", {"boxes": [], "decimals": 2})[2])
        self.assertEqual(self.request("POST", "/export", {"preview_id": preview["preview_id"]})[0], 409)

    def test_invalid_preview_invalidates_previous(self):
        valid = json.loads(self.request("POST", "/preview", {"boxes": [], "decimals": 2})[2])
        self.assertEqual(self.request("POST", "/preview", {"boxes": [{"raw": "hidden"}], "decimals": 2})[0], 400)
        self.assertEqual(self.request("POST", "/export", {"preview_id": valid["preview_id"]})[0], 400)
        self.assertFalse(self.output.exists())
        valid = json.loads(self.request("POST", "/preview", {"boxes": [], "decimals": 2})[2])
        self.assertEqual(self.request("POST", "/preview", {}, **{"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("POST", "/export", {"preview_id": valid["preview_id"]})[0], 400)

    def test_exclusions_and_untrusted_path_rejected(self):
        payload = {"boxes": [{"south": 10, "west": 20, "north": 11, "east": 21, "buffer_m": 100}], "decimals": 2}
        result = json.loads(self.request("POST", "/preview", payload)[2])
        self.assertEqual(result["excluded"], 1)
        self.assertEqual(result["after"], [])
        self.assertEqual(self.request("POST", "/export", {"preview_id": result["preview_id"], "output": "/tmp/private"})[0], 400)
        self.assertEqual(self.request("POST", "/preview", payload, **{"Content-Type": "text/plain"})[0], 400)


class CLITests(unittest.TestCase):
    def test_real_cli_starts_local_preview_without_exporting(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.csv", Path(directory) / "out.csv"
            source.write_bytes(wigle())
            process = subprocess.Popen([sys.executable, "-m", "star_wpa.privacy", str(source), "--format", "wigle", "--output", str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                import select
                self.assertTrue(select.select([process.stdout], [], [], 10)[0])
                line = process.stdout.readline()
                self.assertRegex(line, r"http://127\.0\.0\.1:\d+/")
                self.assertNotIn(str(source), line)
                self.assertFalse(output.exists())
                process.send_signal(signal.SIGINT)
                _, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error)
                self.assertEqual(source.read_bytes(), wigle())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
