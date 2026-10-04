import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from star_wpa.contracts import NS, validate_bundle
from star_wpa.ingest import ingest_kismet, ingest_gpsd, ingest_airodump, observations
from star_wpa.trilateration import trilaterate
from star_wpa.adapters import dispatch, command


class WirelessTests(unittest.TestCase):
    def test_receiver_geo_does_not_become_access_point_geo(self):
        docs = observations({"dataset": "lab", "receiverId": "r1", "provider": "listener", "observations": [
            {"bssid": "AA:BB:CC:DD:EE:FF", "signalDbm": -50, "observedAt": 123,
             "latitude": 0, "longitude": 0, "distanceMeters": 10}]})
        validate_bundle(docs)
        ap = next(d for d in docs if d["dtype"] == "wireless-network")
        self.assertNotIn("location", ap)
        event = next(d for d in docs if d["dtype"] == "event")
        self.assertEqual(event["extensions"][NS]["receiverId"], "r1")
        self.assertEqual(event["extensions"][NS]["longitude"], 0)
        self.assertEqual({d["predicate"] for d in docs if d["dtype"] == "relation"},
                         {"observed-network", "observed-at"})
        self.assertEqual(docs, observations({"dataset": "lab", "receiverId": "r1", "provider": "listener", "observations": [
            {"bssid": "AA:BB:CC:DD:EE:FF", "signalDbm": -50, "observedAt": 123,
             "latitude": 0, "longitude": 0, "distanceMeters": 10}]}))

    def test_kismet_real_device_fields_and_security(self):
        docs = ingest_kismet({"dataset": "lab", "receiverId": "k1", "devices": [{
            "kismet.device.base.macaddr": "aa:bb:cc:dd:ee:ff", "kismet.device.base.last_time": 123,
            "kismet.device.base.type": "Wi-Fi AP", "kismet.device.base.channel": "6",
            "kismet.device.base.signal": {"kismet.common.signal.last_signal": -54},
            "dot11.device": {"dot11.device.last_beaconed_ssid_record": {
                "dot11.advertisedssid.ssid": "Lab", "dot11.advertisedssid.crypt_string": "WPA2 PSK"}}}]})
        ap = next(d for d in docs if d["dtype"] == "wireless-network")
        self.assertEqual((ap["ssid"], ap["security"], ap["channel"]), ("Lab", "wpa2-psk", 6))
        validate_bundle(docs)

    def test_gpsd_requires_valid_fix_and_preserves_zero(self):
        docs = ingest_gpsd({"dataset": "lab", "receiverId": "gps1", "reports": [
            {"class": "VERSION"}, {"class": "TPV", "mode": 1},
            {"class": "TPV", "mode": 3, "lat": 0, "lon": 0, "altMSL": 2,
             "time": "2026-01-01T00:00:00Z", "epx": 3, "epy": 4}]})
        geo = next(d for d in docs if d["dtype"] == "geo-point")
        self.assertEqual((float(geo["latitude"]), float(geo["longitude"]), float(geo["accuracyMeters"])), (0, 0, 5))
        validate_bundle(docs)

    def test_airodump_station_association_is_evidenced(self):
        csv = '''BSSID, First time seen, Last time seen, channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key
AA:BB:CC:DD:EE:FF, 2026-01-01 00:00:00, 2026-01-01 00:00:01, 6, 54, WPA2, CCMP, PSK, -50, 2, 1, 0.0.0.0, 3, Lab,

Station MAC, First time seen, Last time seen, Power, # packets, BSSID, Probed ESSIDs
11:22:33:44:55:66, 2026-01-01 00:00:00, 2026-01-01 00:00:01, -60, 5, AA:BB:CC:DD:EE:FF, Lab
'''
        docs = ingest_airodump({"dataset": "lab", "receiverId": "r1", "csv": csv})
        validate_bundle(docs)
        self.assertEqual(len([d for d in docs if d["dtype"] == "wireless-station"]), 1)
        self.assertIn("associated-with", [d.get("predicate") for d in docs])

    def solve_input(self):
        # Four known ranges to a target in a local ENU plane, at the equator.
        radius = 6371008.8
        target = (30, 40)
        rows = []
        for i, (x, y) in enumerate([(0, 0), (100, 0), (0, 100), (100, 100)]):
            docs = observations({"dataset": "lab", "receiverId": f"r{i}", "provider": "listener", "observations": [{
                "bssid": "aa:bb:cc:dd:ee:ff", "observedAt": 100 + i,
                "latitude": math.degrees(y / radius), "longitude": math.degrees(x / radius),
                "distanceMeters": math.hypot(target[0] - x, target[1] - y)}]})
            rows.extend(docs)
        return list({d["id"]: d for d in rows}.values())

    def test_multireceiver_trilateration_has_proof_and_uncertainty(self):
        inputs = self.solve_input()
        docs = trilaterate({"dataset": "lab", "documents": inputs, "windowSeconds": 10})
        validate_bundle(docs)
        geo = next(d for d in docs if d["dtype"] == "geo-point" and d.get("extensions", {}).get(NS, {}).get("geography") == "derived")
        self.assertAlmostEqual(float(geo["latitude"]), math.degrees(40 / 6371008.8), places=7)
        self.assertAlmostEqual(float(geo["longitude"]), math.degrees(30 / 6371008.8), places=7)
        proof = geo["extensions"][NS]
        self.assertEqual(len(proof["evidenceIds"]), 4)
        self.assertGreaterEqual(float(geo["accuracyMeters"]), 1)
        self.assertLess(proof["residualRmsMeters"], 0.01)

    def test_solver_rejects_duplicate_receivers_and_degenerate_geometry(self):
        inputs = self.solve_input()
        for d in inputs:
            if d["dtype"] == "event":
                d["extensions"][NS]["receiverId"] = "same"
        with self.assertRaises(ValueError):
            trilaterate({"dataset": "lab", "documents": inputs})
        inputs = self.solve_input()
        for d in inputs:
            if d["dtype"] == "event":
                d["extensions"][NS]["latitude"] = 0
        with self.assertRaises(ValueError):
            trilaterate({"dataset": "lab", "documents": inputs})

    def test_solver_does_not_mix_dataset_transmitter_or_time(self):
        for field, value in [("dataset", "other"), ("observedAt", 10000)]:
            docs = self.solve_input()
            events = [d for d in docs if d["dtype"] == "event"]
            for d in events[2:]:
                d[field] = value
            with self.assertRaises(ValueError):
                trilaterate({"dataset": "lab", "documents": docs, "windowSeconds": 10})

    def test_deauth_is_scoped_and_bounded(self):
        request = {"dataset": "lab", "interface": "wlan0mon", "bssid": "aa:bb:cc:dd:ee:ff", "count": 3}
        with self.assertRaises(PermissionError):
            command("deauth", request, policy=None)
        policy = {"interfaces": ["wlan0mon"], "bssids": ["aa:bb:cc:dd:ee:ff"], "allowDeauth": True}
        argv = command("deauth", request, policy)
        self.assertEqual(argv, ["aireplay-ng", "--deauth", "3", "-a", "aa:bb:cc:dd:ee:ff", "wlan0mon"])
        request["count"] = 0
        with self.assertRaises(ValueError):
            command("deauth", request, policy)
        request["count"] = 3
        request["bssid"] = "00:00:00:00:00:01"
        with self.assertRaises(PermissionError):
            command("deauth", request, policy)

    def test_effect_failures_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"STAR_WPA_EFFECT_DB": directory + "/effects.sqlite"}), patch("star_wpa.adapters.subprocess.run", side_effect=subprocess.TimeoutExpired("aircrack-ng", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                dispatch("aircrack", {"dataset": "lab", "requestId": "effect-1", "capture": "/tmp/lab.cap", "wordlist": "/tmp/words",
                                      "bssid": "aa:bb:cc:dd:ee:ff"}, {"allowAircrack": True,
                                      "bssids": ["aa:bb:cc:dd:ee:ff"]})


if __name__ == "__main__":
    unittest.main()
