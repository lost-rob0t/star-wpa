import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from star_wpa.contracts import NS
from star_wpa.tools import CATALOG, dispatch_tool

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nix_bindings', ROOT / 'scripts/nix-tool-bindings.py')
bindings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bindings)


class NixRuntimeTests(unittest.TestCase):
    def test_inventory_covers_catalog_exactly_and_matches_pin(self):
        inventory = json.loads((ROOT / 'catalog/nix-tools.json').read_text())
        lock = json.loads((ROOT / 'flake.lock').read_text())
        self.assertEqual(inventory['nixpkgsRevision'], lock['nodes']['nixpkgs']['locked']['rev'])
        self.assertEqual([row['package'] for row in inventory['packages']], list(CATALOG))
        for row in inventory['packages']:
            self.assertIsInstance(row['requiredExecutables'], list)
            if row['attribute'] is None:
                self.assertTrue(row['reason'])
            else:
                self.assertNotIn('reason', row)

    def test_absent_declared_command_fails_instead_of_silent_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            row = {'package': 'rfkill', 'root': directory, 'version': 'fixture',
                   'requiredExecutables': ['rfkill']}
            with self.assertRaisesRegex(ValueError, 'rfkill'):
                bindings.build_bindings([row])
            (Path(directory) / 'bin').mkdir()
            path = Path(directory) / 'bin/unrelated'
            path.write_text('fixture'); path.chmod(0o700)
            with self.assertRaisesRegex(ValueError, 'rfkill'):
                bindings.build_bindings([row])

    def test_split_provider_filters_other_commands_and_wrapper_internals(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'bin').mkdir()
            for name in ('rfkill', 'mount', '.rfkill-wrapped'):
                path = Path(directory) / 'bin' / name
                path.write_text('fixture'); path.chmod(0o700)
            result = bindings.build_bindings([{'package': 'rfkill', 'root': directory,
                'version': 'fixture', 'requiredExecutables': ['rfkill'], 'selectExecutables': ['rfkill']}])
            self.assertEqual(set(result['toolInstallations']['rfkill']['executables']), {'rfkill'})

    def test_nix_manifest_precedes_host_dpkg_and_missing_stays_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'bin').mkdir()
            tool = Path(directory) / 'bin/rfkill'; tool.write_text('fixture'); tool.chmod(0o700)
            result = bindings.build_bindings([{'package': 'rfkill', 'root': directory, 'version': 'fixture'}])
            result['toolCoverage'] = [{'package': 'wifiphisher', 'reason': 'not packaged in pinned nixpkgs'}]
            manifest = Path(directory) / 'manifest.json'; manifest.write_text(json.dumps(result))
            with patch.dict(os.environ, {'STAR_WPA_NIX_TOOL_MANIFEST': str(manifest)}), \
                    patch('star_wpa.tools.discover_package', side_effect=AssertionError('host dpkg consulted')):
                info = dispatch_tool('rfkill', {'dataset': 'test'})[0]['extensions'][NS]
                self.assertEqual(info['installation'], 'nix-pinned')
                info = dispatch_tool('wifiphisher', {'dataset': 'test'})[0]['extensions'][NS]
                self.assertEqual(info['status'], 'nix-unavailable')
                self.assertEqual(info['reason'], 'not packaged in pinned nixpkgs')
                with self.assertRaises(FileNotFoundError):
                    dispatch_tool('wifiphisher', {'dataset': 'test', 'operation': 'execute'})

    def test_executable_hashing_streams_and_retains_finite_regular_file_bound(self):
        import hashlib
        from star_wpa.files import sha256_bounded
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'large-tool'
            raw = b'x' * (2 * 1024 * 1024 + 3)
            binary.write_bytes(raw)
            self.assertEqual(sha256_bounded(binary, len(raw)), hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                sha256_bounded(binary, len(raw) - 1)
            fifo = Path(directory) / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                sha256_bounded(fifo)
