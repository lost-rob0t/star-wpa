import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from star_wpa.tools import CATALOG, dispatch_tool


class ToolActorsTests(unittest.TestCase):
    def policy(self, package, directory, argv=None):
        return {'toolCommands': {package: [{'executable': 'fixture-tool', 'argv': argv or ['--fixture'],
                 'workingDirectory': directory, 'uiMode': 'headless', 'stdinFile': None}]}}

    def test_every_catalog_package_traverses_discovery_and_execution_ports(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'STAR_WPA_EFFECT_DB': directory + '/effects.sqlite'}):
            with patch('star_wpa.tools.discover_package') as discover, patch('star_wpa.tools.run_tool') as run:
                discover.return_value = {'status': 'installed', 'version': '1.0', 'architecture': 'amd64',
                    'executables': [{'name': 'fixture-tool', 'path': '/fixture/tool'}]}
                run.return_value = {'exitCode': 0, 'stdoutBytes': 0, 'stderrBytes': 0, 'stdoutSha256': '0'*64, 'stderrSha256': '0'*64}
                for package in CATALOG:
                    with self.subTest(package=package):
                        request = {'dataset': 'lab', 'requestId': package, 'operation': 'execute', 'executable': 'fixture-tool',
                                   'argv': ['--fixture'], 'workingDirectory': directory}
                        docs = dispatch_tool(package, request, self.policy(package, directory))
                        self.assertEqual(docs[0]['eventKind'], 'wireless-tool-execution')
                self.assertEqual(run.call_count, len(CATALOG))

    def test_unknown_or_uninstalled_tool_fails_closed(self):
        with self.assertRaises(ValueError):
            dispatch_tool('not-a-tool', {'dataset': 'lab'}, {})
        with patch('star_wpa.tools.discover_package', return_value={'status': 'not-installed', 'executables': []}):
            with self.assertRaises(FileNotFoundError):
                dispatch_tool('airgeddon', {'dataset': 'lab', 'operation': 'execute'}, {})

    def test_request_cannot_approve_its_own_command(self):
        with patch('star_wpa.tools.discover_package', return_value={'status': 'installed', 'version': '1', 'executables': [{'name': 'fixture-tool', 'path': '/fixture/tool'}]}), patch('star_wpa.tools.run_tool') as run:
            with tempfile.TemporaryDirectory() as directory:
                request = {'dataset': 'lab', 'operation': 'execute', 'requestId': 'x', 'executable': 'fixture-tool',
                           'argv': ['--other'], 'workingDirectory': directory, 'toolCommands': {'airgeddon': True}}
                with self.assertRaises(PermissionError):
                    dispatch_tool('airgeddon', request, self.policy('airgeddon', directory))
                run.assert_not_called()

    def test_pinned_source_tool_runs_and_receipt_excludes_raw_output(self):
        import hashlib
        from star_wpa.contracts import NS
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'STAR_WPA_EFFECT_DB': directory + '/effects.sqlite'}):
            path = Path(directory) / 'fixture-tool'
            path.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\nprintf "fixture-output"\n')
            path.chmod(0o700)
            policy = self.policy('wifiphisher', directory)
            policy['toolInstallations'] = {'wifiphisher': {'version': 'fixture', 'executables': {
                'fixture-tool': {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}}}
            with patch('star_wpa.tools.discover_package', return_value={'status': 'not-installed', 'executables': []}):
                docs = dispatch_tool('wifiphisher', {'dataset': 'lab', 'operation': 'execute', 'requestId': 'actual-run',
                    'executable': 'fixture-tool', 'argv': ['--fixture'], 'workingDirectory': directory}, policy)
            receipt = docs[0]['extensions'][NS]
            self.assertEqual(receipt['stdoutBytes'], len('fixture-output'))
            self.assertEqual(receipt['stdoutSha256'], hashlib.sha256(b'fixture-output').hexdigest())
            self.assertNotIn('fixture-output', json.dumps(docs))

    def test_output_overflow_and_timeout_stop_and_reap_real_child(self):
        import time
        from star_wpa.tools import run_tool
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture-tool'
            invocation = {'argv': [], 'workingDirectory': directory, 'stdinFile': None, 'uiMode': 'headless'}
            path.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\nexec yes overflow\n'); path.chmod(0o700)
            with self.assertRaises(ValueError):
                run_tool(str(path), invocation, 3)
            path.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\nexec sleep 30\n')
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                run_tool(str(path), invocation, 1)
            self.assertLess(time.monotonic() - started, 4)

    def test_terminal_mode_has_real_tty_and_bounded_input(self):
        from star_wpa.tools import run_tool
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture-tool'
            path.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\ntest -t 0 || exit 5\nread answer\ntest "$answer" = "fixture" || exit 6\nprintf "ok"\n')
            path.chmod(0o700)
            source = Path(directory) / 'input'
            source.write_text('fixture\n')
            result = run_tool(str(path), {'argv': [], 'workingDirectory': directory, 'stdinFile': str(source), 'uiMode': 'terminal'}, 3)
            self.assertEqual(result['exitCode'], 0)
            self.assertTrue(result['streamsMerged'])

    def test_discovery_excludes_other_package_owned_executables(self):
        from star_wpa.tools import discover_package
        import os
        results = [subprocess.CompletedProcess([], 0, 'amd64', ''),
                   subprocess.CompletedProcess([], 0, 'installed\t1.0', ''),
                   subprocess.CompletedProcess([], 0, '/usr/bin/sh\n/usr/share/doc/ignored\n', ''),
                   subprocess.CompletedProcess([], 0, 'dash: /usr/bin/dash\n', '')]
        with patch('star_wpa.tools.package_query', side_effect=results), patch('star_wpa.tools.shutil.which', return_value='/usr/bin/dpkg'), patch('star_wpa.tools.Path.is_file', return_value=True), patch('star_wpa.tools.os.access', return_value=True), patch('star_wpa.tools.Path.resolve', return_value=Path('/usr/bin/dash')):
            self.assertEqual(discover_package('wifite')['executables'], [])

    def test_architecture_exclusion_survives_catalog_projection(self):
        from star_wpa.tools import discover_package
        with patch('star_wpa.tools.package_query', return_value=subprocess.CompletedProcess([], 0, 'i386', '')), patch('star_wpa.tools.shutil.which', return_value='/usr/bin/dpkg'):
            self.assertEqual(discover_package('aircrack-ng')['status'], 'architecture-excluded')

    def test_pinned_binary_change_and_missing_display_fail_closed(self):
        from star_wpa.tools import pinned_installation
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture-tool'
            path.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\nexit 0\n'); path.chmod(0o700)
            with self.assertRaises(PermissionError):
                pinned_installation('wifiphisher', {'toolInstallations': {'wifiphisher': {'version': 'fixture',
                    'executables': {'fixture-tool': {'path': str(path), 'sha256': '0'*64}}}}})
            request = {'dataset': 'lab', 'operation': 'execute', 'requestId': 'x', 'executable': 'fixture-tool',
                       'argv': ['--fixture'], 'workingDirectory': directory, 'uiMode': 'desktop'}
            policy = self.policy('inspectrum', directory); policy['toolCommands']['inspectrum'][0]['uiMode'] = 'desktop'
            with patch.dict('os.environ', {'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), patch('star_wpa.tools.discover_package', return_value={
                    'status': 'installed', 'version': '1', 'executables': [{'name': 'fixture-tool', 'path': str(path)}]}), patch('star_wpa.tools.run_tool') as run:
                with self.assertRaises(RuntimeError):
                    dispatch_tool('inspectrum', request, policy)
                run.assert_not_called()

    def test_nix_bindings_are_hash_verified_and_discoverable(self):
        import hashlib
        import sys
        from star_wpa.contracts import NS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'nix-package'; (root / 'bin').mkdir(parents=True)
            tool = root / 'bin/eaphammer'
            tool.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\nexit 0\n'); tool.chmod(0o700)
            inputs = Path(directory) / 'inputs.json'; manifest = Path(directory) / 'bindings.json'
            inputs.write_text(json.dumps([{'package': 'eaphammer', 'root': str(root), 'version': 'fixture'}]))
            subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / 'scripts/nix-tool-bindings.py'),
                            str(inputs), str(manifest)], check=True)
            with patch.dict('os.environ', {'STAR_WPA_NIX_TOOL_MANIFEST': str(manifest)}), patch('star_wpa.tools.discover_package',
                return_value={'status': 'not-installed', 'executables': []}):
                doc = dispatch_tool('eaphammer', {'dataset': 'lab', 'operation': 'discover'})[0]
                self.assertEqual(doc['extensions'][NS]['installation'], 'nix-pinned')
                self.assertEqual(doc['extensions'][NS]['executables'][0]['name'], 'eaphammer')
                tool.write_text('changed')
                with self.assertRaises(PermissionError):
                    dispatch_tool('eaphammer', {'dataset': 'lab', 'operation': 'discover'})
