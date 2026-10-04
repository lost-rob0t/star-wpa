import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from star_wpa.adapters import dispatch
from star_wpa.ingest import ingest_wardrive, observations
from star_wpa.contracts import validate_bundle


class EffectTests(unittest.TestCase):
    def request(self):
        return {'dataset': 'lab', 'interface': 'wlan0mon', 'bssid': 'aa:bb:cc:dd:ee:ff', 'count': 1, 'requestId': 'deauth-1'}

    def policy(self):
        return {'interfaces': ['wlan0mon'], 'bssids': ['aa:bb:cc:dd:ee:ff'], 'allowDeauth': True}

    def test_active_effect_is_once_and_rechecks_policy(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'STAR_WPA_EFFECT_DB': directory + '/effects.sqlite'}):
            with patch('star_wpa.adapters.subprocess.run') as run:
                run.return_value.returncode = 0
                first = dispatch('deauth', self.request(), self.policy())
                self.assertEqual(first, dispatch('deauth', self.request(), self.policy()))
                self.assertEqual(run.call_count, 1)
                changed = dict(self.request(), count=2)
                with self.assertRaises(ValueError):
                    dispatch('deauth', changed, self.policy())
                with self.assertRaises(PermissionError):
                    dispatch('deauth', self.request(), {})

    def test_uncertain_effect_never_retries_automatically(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'STAR_WPA_EFFECT_DB': directory + '/effects.sqlite'}):
            with patch('star_wpa.adapters.subprocess.run', side_effect=RuntimeError('tool failed')) as run:
                with self.assertRaises(RuntimeError):
                    dispatch('deauth', self.request(), self.policy())
                with self.assertRaises(PermissionError):
                    dispatch('deauth', self.request(), self.policy())
                self.assertEqual(run.call_count, 1)

    def test_invalid_request_does_not_run_tool(self):
        with patch('star_wpa.adapters.subprocess.run') as run:
            with self.assertRaises(ValueError):
                dispatch('deauth', dict(self.request(), requestId=''), self.policy())
            run.assert_not_called()

    def test_wardrive_wifi_bluetooth_export(self):
        samples = [{'id': 1, 'address': 'aa:bb:cc:dd:ee:ff', 'level': -50, 'latitude': 0, 'longitude': 0,
                    'time': 1700000000123, 'radio': 'WIFI', 'name': 'Lab', 'security': 'WPA2'},
                   {'id': 2, 'address': '11:22:33:44:55:66', 'level': -60, 'latitude': 0, 'longitude': 0,
                    'time': 1700000000123, 'radio': 'BLE'}]
        docs = ingest_wardrive({'dataset': 'lab', 'device_id': 'installation-1', 'observations': samples})
        validate_bundle(docs)
        self.assertIn('network-device', [d['dtype'] for d in docs])
        ap = next(d for d in docs if d['dtype'] == 'wireless-network')
        self.assertNotIn('location', ap)
        self.assertEqual(ap['lastSeen'], 1700000000)
        self.assertEqual(docs, ingest_wardrive({'dataset': 'lab', 'device_id': 'installation-1', 'observations': samples}))

    def test_oversized_observations_fail_before_normalization(self):
        with self.assertRaises(ValueError):
            observations({'dataset': 'lab', 'receiverId': 'r1', 'observations': [{}] * 1001})
