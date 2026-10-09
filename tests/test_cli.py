"""Offline contract coverage for generated standalone console scripts."""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from star_wpa import __main__ as adapter_cli
from star_wpa import cli
from star_wpa.contracts import NS, document, validate_bundle
from star_wpa.ingest import observations
from star_wpa.tools import CATALOG

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'fixture-private-request-content'


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / 'pyproject.toml').open('rb') as source:
            cls.scripts = tomllib.load(source)['project']['scripts']

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='star-wpa-cli-test-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.request = {'dataset': 'lab', 'receiverId': 'fixture', 'observations': []}
        self.request_path = self.write_json('request.json', self.request)
        self.docs = [document('event', 'lab', 'wpa:fixture')]

    def write_json(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def invoke(self, command, argv, *, generic=False, implicit_argv=False, argv0=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        # An installed console script has an absolute argv[0], not just its name.
        with patch.object(sys, 'argv', [argv0 or str(self.directory / 'bin' / command), *argv]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                entry = adapter_cli.main if generic else getattr(cli, self.scripts[command].split(':', 1)[1])
                code = entry() if implicit_argv else entry(argv)
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_failure(self, result, error_type):
        code, stdout, stderr = result
        self.assertEqual(code, 1, stderr)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, f'star-wpa adapter failed: {error_type}\n')
        self.assertNotIn(SECRET, stderr)
        self.assertNotIn('Traceback', stderr)

    def test_registry_matches_core_actors_catalog_and_generated_scripts(self):
        core = {path.stem for path in (ROOT / 'actors').glob('*.star')}
        self.assertEqual(set(cli.CORE_ACTORS), core)
        self.assertEqual(len(cli.CORE_ACTORS), len(core))
        self.assertEqual({path.stem for path in (ROOT / 'actors/tools').glob('*.star')}, set(CATALOG))
        expected = {'sa-' + actor: actor for actor in core}
        expected.update({'sa-tool-' + tool: 'tool-' + tool for tool in CATALOG})
        expected.update({'sa-' + tool: 'tool-' + tool for tool in CATALOG if tool not in core})
        self.assertEqual(cli.COMMAND_ACTORS, expected)
        self.assertEqual(self.scripts, {name: 'star_wpa.cli:run_' + name.replace('-', '_') for name in expected} |
                         {'star-wpa': 'star_wpa.__main__:main'})
        for name in expected:
            self.assertTrue(callable(getattr(cli, self.scripts[name].split(':', 1)[1])))

    def test_colliding_short_names_keep_core_and_qualified_tools_accessible(self):
        for name in ('kismet', 'gpsd'):
            with self.subTest(name=name):
                self.assertEqual(cli.COMMAND_ACTORS['sa-' + name], name)
                self.assertEqual(cli.COMMAND_ACTORS['sa-tool-' + name], 'tool-' + name)

    def test_every_alias_dispatches_exactly_its_bound_actor(self):
        for command, actor in cli.COMMAND_ACTORS.items():
            with self.subTest(command=command), patch.object(adapter_cli, 'dispatch', return_value=self.docs) as dispatch:
                code, stdout, stderr = self.invoke(command, ['--request', str(self.request_path)])
                self.assertEqual(code, 0, stderr)
                self.assertEqual(stderr, '')
                self.assertEqual(json.loads(stdout), self.docs)
                self.assertEqual(stdout.count('\n'), 1)
                dispatch.assert_called_once_with(actor, self.request, None)

    def test_every_alias_has_standalone_help_without_dispatch(self):
        for command, actor in cli.COMMAND_ACTORS.items():
            with self.subTest(command=command), patch.object(adapter_cli, 'dispatch') as dispatch:
                code, stdout, stderr = self.invoke(command, ['--help'])
                self.assertEqual(code, 0)
                self.assertEqual(stderr, '')
                self.assertTrue(stdout.startswith('usage: ' + command + ' '), stdout)
                self.assertIn('--request', stdout)
                self.assertIn(actor, stdout)
                self.assertNotIn('positional arguments:', stdout)
                dispatch.assert_not_called()

    def test_every_alias_requires_a_request_file(self):
        for command in cli.COMMAND_ACTORS:
            with self.subTest(command=command), patch.object(adapter_cli, 'dispatch') as dispatch:
                code, stdout, stderr = self.invoke(command, [])
                self.assertEqual(code, 2)
                self.assertEqual(stdout, '')
                self.assertIn('--request', stderr)
                dispatch.assert_not_called()

    def test_standalone_command_rejects_actor_override_and_unknown_options(self):
        for argv in (["gpsd", '--request', str(self.request_path)],
                     ['--actor', 'gpsd', '--request', str(self.request_path)],
                     ['--request'], ['--unknown']):
            with self.subTest(argv=argv), patch.object(adapter_cli, 'dispatch') as dispatch:
                code, stdout, stderr = self.invoke('sa-listener', argv)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, '')
                self.assertIn('usage:', stderr)
                dispatch.assert_not_called()

    def test_every_entrypoint_preserves_its_binding_when_wrapped_or_renamed(self):
        for command, actor in cli.COMMAND_ACTORS.items():
            for invoked_as in ('.' + command + '-wrapped', 'renamed-command'):
                with self.subTest(command=command, invoked_as=invoked_as), \
                        patch.object(adapter_cli, 'dispatch', return_value=self.docs) as dispatch:
                    code, stdout, stderr = self.invoke(command, ['--request', str(self.request_path)],
                        implicit_argv=True, argv0=str(self.directory / 'bin' / invoked_as))
                    self.assertEqual(code, 0, stderr)
                    self.assertEqual(json.loads(stdout), self.docs)
                    dispatch.assert_called_once_with(actor, self.request, None)

    def test_console_and_generic_cli_accept_real_sys_argv(self):
        for command, argv, generic in (
                ('sa-listener', ['--request', str(self.request_path)], False),
                ('star-wpa', ['listener', '--request', str(self.request_path)], True)):
            with self.subTest(command=command), patch.object(adapter_cli, 'dispatch', return_value=self.docs) as dispatch:
                code, stdout, stderr = self.invoke(command, argv, generic=generic, implicit_argv=True)
                self.assertEqual(code, 0, stderr)
                self.assertEqual(json.loads(stdout), self.docs)
                dispatch.assert_called_once_with('listener', self.request, None)

    def test_generic_cli_keeps_every_actor_and_tool_choice(self):
        for actor in [*cli.CORE_ACTORS, *('tool-' + name for name in CATALOG)]:
            with self.subTest(actor=actor), patch.object(adapter_cli, 'dispatch', return_value=self.docs) as dispatch:
                result = self.invoke('star-wpa', [actor, '--request', str(self.request_path)], generic=True)
                self.assertEqual(result[0], 0, result[2])
                dispatch.assert_called_once_with(actor, self.request, None)
        code, stdout, stderr = self.invoke('star-wpa', ['--help'], generic=True)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, '')
        self.assertIn('positional arguments:', stdout)
        self.assertEqual(self.invoke('star-wpa', ['not-an-actor'], generic=True)[0], 2)

    def test_policy_only_comes_from_environment_file(self):
        requested = dict(self.request, policy={'allowDeauth': True}, allowDeauth=True,
                         STAR_WPA_POLICY_FILE=SECRET)
        request_path = self.write_json('untrusted.json', requested)
        configured = {'allowDeauth': False, 'fixture': SECRET}
        policy_path = self.write_json('policy.json', configured)
        for env, expected in (({}, None), ({'STAR_WPA_POLICY_FILE': str(policy_path)}, configured)):
            with self.subTest(configured=bool(env)), patch.dict(os.environ, env, clear=True), \
                    patch.object(adapter_cli, 'dispatch', return_value=self.docs) as dispatch:
                code, stdout, stderr = self.invoke('sa-listener', ['--request', str(request_path)])
                self.assertEqual(code, 0, stderr)
                dispatch.assert_called_once_with('listener', requested, expected)
                self.assertNotIn(SECRET, stdout + stderr)

    def test_bad_policy_fails_before_dispatch_without_exposing_contents(self):
        invalid = self.directory / (SECRET + '.json')
        invalid.write_text('{"secret": "' + SECRET + '" invalid}', encoding='utf-8')
        for path, error in ((invalid, 'JSONDecodeError'), (self.directory / SECRET, 'FileNotFoundError')):
            with self.subTest(error=error), patch.dict(os.environ, {'STAR_WPA_POLICY_FILE': str(path)}), \
                    patch.object(adapter_cli, 'dispatch') as dispatch:
                self.assert_failure(self.invoke('sa-listener', ['--request', str(self.request_path)]), error)
                dispatch.assert_not_called()

    def test_missing_malformed_and_nonregular_requests_fail_closed(self):
        malformed = self.directory / 'malformed.json'
        malformed.write_text('{"secret": "' + SECRET + '" invalid}', encoding='utf-8')
        cases = [(self.directory / SECRET, 'FileNotFoundError'),
                 (malformed, 'JSONDecodeError'), (self.directory, 'IsADirectoryError')]
        if hasattr(os, 'mkfifo'):
            fifo = self.directory / 'fifo'
            os.mkfifo(fifo)
            cases.append((fifo, 'ValueError'))
        for path, error in cases:
            with self.subTest(path=path.name), patch.object(adapter_cli, 'dispatch') as dispatch:
                self.assert_failure(self.invoke('sa-listener', ['--request', str(path)]), error)
                dispatch.assert_not_called()

    def test_request_file_byte_limit_is_enforced_before_dispatch(self):
        oversized = self.directory / 'oversized.json'
        oversized.write_text(json.dumps({'fixture': SECRET * 20}), encoding='utf-8')
        with patch.object(adapter_cli, 'MAX_BYTES', 100), patch.object(adapter_cli, 'dispatch') as dispatch:
            self.assert_failure(self.invoke('sa-listener', ['--request', str(oversized)]), 'ValueError')
            dispatch.assert_not_called()

    def test_dash_is_a_literal_filename_and_never_reads_stdin(self):
        with contextlib.chdir(self.directory), patch.object(sys, 'stdin') as stdin, \
                patch.object(adapter_cli, 'dispatch', return_value=self.docs) as dispatch:
            self.assert_failure(self.invoke('sa-listener', ['--request', '-']), 'FileNotFoundError')
            dispatch.assert_not_called()
            self.write_json('-', self.request)
            code, stdout, stderr = self.invoke('sa-listener', ['--request', '-'])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(stdout), self.docs)
            dispatch.assert_called_once_with('listener', self.request, None)
            stdin.read.assert_not_called()
            stdin.buffer.read.assert_not_called()

    def test_adapter_errors_only_reveal_the_exception_type(self):
        for error in (PermissionError(SECRET), ValueError(SECRET), OSError(SECRET), RuntimeError(SECRET)):
            with self.subTest(error=type(error).__name__), patch.object(adapter_cli, 'dispatch', side_effect=error):
                self.assert_failure(self.invoke('sa-listener', ['--request', str(self.request_path)]), type(error).__name__)

    def test_nonfinite_unserializable_and_oversized_output_never_reaches_stdout(self):
        for output, error in (([float('nan')], 'ValueError'), ([float('inf')], 'ValueError'),
                              ([object()], 'TypeError'), ([SECRET * 20], 'ValueError')):
            with self.subTest(error=error, output_type=type(output[0]).__name__), \
                    patch.object(adapter_cli, 'MAX_BYTES', 100), \
                    patch.object(adapter_cli, 'dispatch', return_value=output):
                self.assert_failure(self.invoke('sa-listener', ['--request', str(self.request_path)]), error)

    def test_keyboard_interrupt_returns_conventional_exit_code_without_traceback(self):
        with patch.object(adapter_cli, 'dispatch', side_effect=KeyboardInterrupt(SECRET)):
            code, stdout, stderr = self.invoke('sa-listener', ['--request', str(self.request_path)])
            self.assertEqual(code, 130)
            self.assertEqual(stdout, '')
            self.assertEqual(stderr, 'star-wpa adapter interrupted\n')
            self.assertNotIn(SECRET, stderr)

    def test_offline_ingestion_emits_valid_documents_and_matches_generic_cli(self):
        common = {'dataset': 'lab', 'receiverId': 'fixture'}
        requests = {
            'kismet': dict(common, devices=[{'kismet.device.base.macaddr': 'aa:bb:cc:dd:ee:ff',
                'kismet.device.base.type': 'Wi-Fi AP', 'kismet.device.base.last_time': 123}]),
            'gpsd': dict(common, reports=[{'class': 'TPV', 'mode': 3, 'lat': 0, 'lon': 0,
                                         'time': '2026-01-01T00:00:00Z'}]),
            'listener': dict(common, observations=[{'bssid': 'aa:bb:cc:dd:ee:ff', 'observedAt': 123}]),
            'wardrive': dict(common, observations=[{'id': 1, 'time': 123000,
                'address': 'aa:bb:cc:dd:ee:ff', 'level': -50, 'latitude': 0, 'longitude': 0}]),
        }
        inputs = []
        for i, (x, y) in enumerate(((0, 0), (100, 0), (0, 100), (100, 100))):
            inputs.extend(observations({'dataset': 'lab', 'receiverId': 'r' + str(i), 'observations': [{
                'bssid': 'aa:bb:cc:dd:ee:ff', 'observedAt': 100 + i,
                'latitude': math.degrees(y / 6371008.8), 'longitude': math.degrees(x / 6371008.8),
                'distanceMeters': math.hypot(30 - x, 40 - y)}]}))
        requests['trilateration'] = {'dataset': 'lab', 'documents': list({doc['id']: doc for doc in inputs}.values()),
                                     'windowSeconds': 10}
        with patch('star_wpa.adapters.open_http', side_effect=AssertionError('unexpected network access')), \
                patch('star_wpa.adapters.socket.create_connection', side_effect=AssertionError('unexpected GPS access')), \
                patch('star_wpa.tools.run_tool', side_effect=AssertionError('unexpected executable launch')):
            for actor, request in requests.items():
                with self.subTest(actor=actor):
                    path = self.write_json(actor + '.json', request)
                    standalone = self.invoke('sa-' + actor, ['--request', str(path)])
                    generic = self.invoke('star-wpa', [actor, '--request', str(path)], generic=True)
                    self.assertEqual(standalone[0], 0, standalone[2])
                    self.assertEqual(standalone[2], '')
                    self.assertEqual(standalone, generic)
                    docs = json.loads(standalone[1])
                    self.assertTrue(docs)
                    validate_bundle(docs)
                    self.assertTrue(all(doc['schemaVersion'] == '0.10.1' for doc in docs))
        proof = next(doc for doc in json.loads(standalone[1]) if doc.get('extensions', {}).get(NS, {}).get('geography') == 'derived')
        self.assertEqual(len(proof['extensions'][NS]['evidenceIds']), 4)

    def test_real_validation_failures_do_not_emit_partial_document_batches(self):
        requests = [[], {'dataset': 'lab', 'receiverId': 'fixture', 'observations': [
            {'bssid': 'aa:bb:cc:dd:ee:ff', 'observedAt': 123},
            {'bssid': SECRET, 'observedAt': 124}]}]
        for request in requests:
            with self.subTest(request_type=type(request).__name__):
                path = self.write_json('invalid.json', request)
                self.assert_failure(self.invoke('sa-listener', ['--request', str(path)]), 'ValueError')

    def test_active_core_commands_cannot_self_authorize_from_request(self):
        request = {'dataset': 'lab', 'requestId': 'fixture', 'bssid': 'aa:bb:cc:dd:ee:ff',
                   'interface': 'fixture0', 'count': 1, 'capture': SECRET, 'wordlist': SECRET,
                   'allowAircrack': True, 'allowDeauth': True,
                   'policy': {'allowAircrack': True, 'allowDeauth': True,
                              'bssids': ['aa:bb:cc:dd:ee:ff'], 'interfaces': ['fixture0']}}
        path = self.write_json('self-authorized.json', request)
        with patch('star_wpa.tools.run_tool') as launch, patch('star_wpa.effects.run_once') as ledger:
            for actor in ('aircrack', 'deauth'):
                with self.subTest(actor=actor):
                    self.assert_failure(self.invoke('sa-' + actor, ['--request', str(path)]), 'PermissionError')
            launch.assert_not_called()
            ledger.assert_not_called()


if __name__ == '__main__':
    unittest.main()
