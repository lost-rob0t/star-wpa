"""Offline regression coverage for the installed laptop smoke-check mode."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'check_installed_cli', ROOT / 'scripts' / 'check-installed-cli.py')
smoke_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke_cli)
SECRET = 'private-smoke-fixture-do-not-report'
CHECK_PHASES = ('installation', 'command-help', 'offline-ingestion', 'error-and-policy-paths')


class SmokeCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / 'pyproject.toml').open('rb') as source:
            cls.scripts = tomllib.load(source)['project']['scripts']

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='star-wpa-smoke-test-')
        self.addCleanup(self.temporary.cleanup)
        self.real_subprocess_run = subprocess.run
        children = patch.object(smoke_cli.subprocess, 'run',
                                side_effect=AssertionError('A real child must not run'))
        children.start()
        self.addCleanup(children.stop)
        self.directory = Path(self.temporary.name)
        self.binaries = self.directory / 'installed-bin'
        self.binaries.mkdir()
        for name in self.scripts:
            launcher = self.binaries / name
            launcher.write_text('#!/bin/sh\nexit 99\n', encoding='utf-8')
            launcher.chmod(0o555)
        self.summary = self.directory / 'summary.json'

    def invoke(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = smoke_cli.main(list(arguments))
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def installed_arguments(self, summary=None):
        return ('--installed', '--summary', str(summary or self.summary),
                '--bin-directory', str(self.binaries))

    def assert_private_text(self, text):
        for value in (SECRET, str(self.directory), 'Traceback', 'STAR_WPA_', 'PYTHONPATH'):
            self.assertNotIn(value, text)

    def binary_snapshot(self):
        return {path.name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.binaries.iterdir()}

    def successful_verification(self, python, binaries, environment, unrelated,
                                expected_scripts, expected_prefix=None, progress=None):
        self.assertEqual(binaries, self.binaries)
        self.assertEqual(expected_scripts, self.scripts)
        self.assertIsNone(expected_prefix)
        self.assertTrue(unrelated.is_dir())
        self.assertFalse(unrelated.is_relative_to(ROOT))
        for phase in CHECK_PHASES:
            progress(phase, 'running')
            progress(phase, 'passed')

    def read_summary(self):
        self.assertEqual(stat.S_IMODE(self.summary.stat().st_mode), 0o600)
        text = self.summary.read_text(encoding='utf-8')
        self.assert_private_text(text)
        summary = json.loads(text)
        self.assertEqual(summary['format'], 'star-wpa-smoke-v1')
        self.assertEqual(summary['mode'], 'installed')
        self.assertLessEqual(set(summary),
                             {'format', 'mode', 'status', 'checks', 'errorType', 'failureCode', 'command'})
        self.assertLessEqual(set(summary['checks']), {'preflight', *CHECK_PHASES})
        self.assertLessEqual(set(summary['checks'].values()), {'passed', 'failed'})
        if 'command' in summary:
            self.assertIn(summary['command'], self.scripts)
        return summary

    def installed_metadata(self):
        return json.dumps({
            'scripts': self.scripts,
            'bindings': {name: name[3:] for name in self.scripts if name.startswith('sa-')},
            'tools': [],
            'schemaAvailable': True,
        })

    def test_installed_mode_skips_build_install_and_scrubs_inherited_environment(self):
        environment = {
            'PATH': '/usr/bin:/bin',
            'HOME': str(self.directory),
            'ORDINARY_VALUE': 'preserved',
            'STAR_WPA_CONFIG': SECRET,
            'STAR_WPA_POLICY': SECRET,
            'STAR_WPA_UNRECOGNIZED_FUTURE_SETTING': SECRET,
            'PYTHONPATH': str(self.directory / SECRET),
            'PYTHONHOME': str(self.directory / SECRET),
            'VIRTUAL_ENV': str(self.directory / SECRET),
        }
        before = self.binary_snapshot()
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(smoke_cli, 'verify_installation',
                             side_effect=self.successful_verification) as verify, \
                patch.object(smoke_cli, 'build_wheel_installation',
                             side_effect=AssertionError('Installed mode cannot build')) as build, \
                patch.object(smoke_cli, 'run',
                             side_effect=AssertionError('Installed orchestration cannot run children')) as run:
            code, stdout, stderr = self.invoke(*self.installed_arguments())
            self.assertEqual(dict(os.environ), environment)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, '')
        self.assert_private_text(stdout)
        build.assert_not_called()
        run.assert_not_called()
        verify.assert_called_once()
        actual_environment = verify.call_args.args[2]
        self.assertEqual(actual_environment['ORDINARY_VALUE'], 'preserved')
        self.assertFalse(any(key.startswith('STAR_WPA_') for key in actual_environment))
        for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
            self.assertNotIn(key, actual_environment)
        for key in ('PIP_NO_INDEX', 'PIP_NO_INPUT', 'PIP_DISABLE_PIP_VERSION_CHECK',
                    'PYTHONDONTWRITEBYTECODE'):
            self.assertEqual(actual_environment[key], '1')
        self.assertEqual(actual_environment['PIP_CONFIG_FILE'], os.devnull)
        self.assertEqual(self.binary_snapshot(), before)
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'passed',
            'checks': {phase: 'passed' for phase in ('preflight', *CHECK_PHASES)},
        })

    def test_installed_mode_defaults_to_current_interpreter_binary_directory(self):
        python = self.binaries / 'python'
        with patch.object(smoke_cli.sys, 'executable', str(python)), \
                patch.object(smoke_cli, 'verify_installation',
                             side_effect=self.successful_verification) as verify, \
                patch.object(smoke_cli, 'build_wheel_installation') as build:
            code, stdout, stderr = self.invoke('--installed', '--summary', str(self.summary))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(verify.call_args.args[0], python)
        build.assert_not_called()
        self.assertEqual(self.read_summary()['status'], 'passed')

    def test_existing_summary_is_not_overwritten_and_no_checks_run(self):
        original = ('existing private report: ' + SECRET).encode()
        self.summary.write_bytes(original)
        self.summary.chmod(0o640)
        with patch.object(smoke_cli, 'verify_installation') as verify, \
                patch.object(smoke_cli, 'build_wheel_installation') as build:
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 2)
        self.assertEqual(self.summary.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.summary.stat().st_mode), 0o640)
        self.assert_private_text(stdout + stderr)
        verify.assert_not_called()
        build.assert_not_called()

    def test_summary_symlink_is_not_followed_and_no_checks_run(self):
        target = self.directory / 'existing-report.json'
        target.write_text(SECRET, encoding='utf-8')
        self.summary.symlink_to(target)
        with patch.object(smoke_cli, 'verify_installation') as verify, \
                patch.object(smoke_cli, 'build_wheel_installation') as build:
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 2)
        self.assertEqual(target.read_text(encoding='utf-8'), SECRET)
        self.assertTrue(self.summary.is_symlink())
        self.assert_private_text(stdout + stderr)
        verify.assert_not_called()
        build.assert_not_called()

    def test_uncreatable_summary_prevents_smoke_checks(self):
        missing = self.directory / SECRET / 'summary.json'
        with patch.object(smoke_cli, 'verify_installation') as verify, \
                patch.object(smoke_cli, 'build_wheel_installation') as build:
            code, stdout, stderr = self.invoke(*self.installed_arguments(missing))
        self.assertEqual(code, 2)
        self.assertFalse(missing.exists())
        self.assert_private_text(stdout + stderr)
        verify.assert_not_called()
        build.assert_not_called()

    def test_failed_preflight_leaves_private_sanitized_failure_summary(self):
        with patch.object(smoke_cli, 'ROOT', self.directory / SECRET), \
                patch.object(smoke_cli, 'verify_installation') as verify, \
                patch.object(smoke_cli, 'build_wheel_installation') as build:
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 1)
        self.assert_private_text(stdout + stderr)
        verify.assert_not_called()
        build.assert_not_called()
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
            'checks': {'preflight': 'failed'}, 'errorType': 'FileNotFoundError',
        })

    def test_verification_failure_summary_contains_phase_and_type_only(self):
        def fail(*args, progress, **kwargs):
            progress('installation', 'passed')
            progress('command-help', 'running')
            raise RuntimeError(SECRET + ' ' + str(self.directory))

        with patch.object(smoke_cli, 'verify_installation', side_effect=fail):
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 1)
        self.assert_private_text(stdout + stderr)
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
            'checks': {'preflight': 'passed', 'installation': 'passed', 'command-help': 'failed'},
            'errorType': 'RuntimeError',
        })

    def test_missing_binary_directory_fails_before_running_installed_commands(self):
        missing = self.directory / SECRET / 'missing-bin'
        with patch.object(smoke_cli, 'run') as run:
            code, stdout, stderr = self.invoke('--installed', '--summary', str(self.summary),
                                               '--bin-directory', str(missing))
        self.assertEqual(code, 1)
        self.assert_private_text(stdout + stderr)
        run.assert_not_called()
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
            'checks': {'preflight': 'passed', 'installation': 'failed'},
            'errorType': 'SmokeFailure', 'failureCode': 'command-directory-missing',
        })

    def test_missing_command_summary_names_only_the_known_command(self):
        command = min(self.scripts)
        (self.binaries / command).unlink()
        metadata = subprocess.CompletedProcess([], 0, self.installed_metadata(), '')
        with patch.object(smoke_cli, 'run', return_value=metadata) as run:
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 1)
        self.assert_private_text(stdout + stderr)
        run.assert_called_once()
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
            'checks': {'preflight': 'passed', 'installation': 'passed', 'command-help': 'failed'},
            'errorType': 'SmokeFailure', 'failureCode': 'command-missing', 'command': command,
        })

    def test_failed_help_summary_has_fixed_code_and_known_command_without_child_output(self):
        for failure_code in ('unexpected-exit-status', 'command-could-not-complete'):
            with self.subTest(failure_code=failure_code):
                def child(argv, **kwargs):
                    if '-c' in argv:
                        return subprocess.CompletedProcess(argv, 0, self.installed_metadata(), '')
                    self.assertEqual(Path(argv[0]).name, min(self.scripts))
                    self.assertIn('--help', argv)
                    if failure_code == 'command-could-not-complete':
                        raise subprocess.TimeoutExpired(argv, 30, output=SECRET, stderr=SECRET)
                    return subprocess.CompletedProcess(argv, 9, SECRET, SECRET)

                with patch.object(smoke_cli.subprocess, 'run', side_effect=child):
                    code, stdout, stderr = self.invoke(*self.installed_arguments())
                self.assertEqual(code, 1)
                self.assert_private_text(stdout + stderr)
                self.assertEqual(self.read_summary(), {
                    'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
                    'checks': {'preflight': 'passed', 'installation': 'passed', 'command-help': 'failed'},
                    'errorType': 'SmokeFailure', 'failureCode': failure_code, 'command': min(self.scripts),
                })
                self.summary.unlink()

    def test_failure_summary_does_not_report_unrecognized_command_or_path(self):
        failure = smoke_cli.SmokeFailure('check-failed', str(self.directory / SECRET))
        with patch.object(smoke_cli, 'verify_installation', side_effect=failure):
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 1)
        self.assert_private_text(stdout + stderr)
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
            'checks': {'preflight': 'passed'}, 'errorType': 'SmokeFailure', 'failureCode': 'check-failed',
        })

    def test_interrupt_leaves_failure_summary_instead_of_running_status(self):
        def interrupt(*args, progress, **kwargs):
            progress('installation', 'running')
            raise KeyboardInterrupt(SECRET)

        with patch.object(smoke_cli, 'verify_installation', side_effect=interrupt):
            code, stdout, stderr = self.invoke(*self.installed_arguments())
        self.assertEqual(code, 130)
        self.assert_private_text(stdout + stderr)
        self.assertEqual(self.read_summary(), {
            'format': 'star-wpa-smoke-v1', 'mode': 'installed', 'status': 'failed',
            'checks': {'preflight': 'passed', 'installation': 'failed'},
            'errorType': 'KeyboardInterrupt',
        })

    def test_bin_directory_requires_installed_mode(self):
        with patch.object(smoke_cli, 'verify_installation') as verify, \
                patch.object(smoke_cli, 'build_wheel_installation') as build:
            code, stdout, stderr = self.invoke('--bin-directory', str(self.binaries),
                                               '--summary', str(self.summary))
        self.assertEqual(code, 2)
        self.assertIn('--bin-directory requires --installed', stderr)
        self.assertFalse(self.summary.exists())
        verify.assert_not_called()
        build.assert_not_called()

    def test_run_does_not_expose_failed_child_output_or_command(self):
        command = [self.directory / SECRET, '--credential', SECRET]
        result = subprocess.CompletedProcess(command, 9, SECRET, SECRET)
        with patch.object(smoke_cli.subprocess, 'run', return_value=result) as run:
            with self.assertRaises(smoke_cli.SmokeFailure) as failure:
                smoke_cli.run(command, cwd=self.directory, env={'PRIVATE': SECRET})
        self.assert_private_text(str(failure.exception))
        self.assertEqual(failure.exception.code, 'unexpected-exit-status')
        self.assertIsNone(failure.exception.command)
        run.assert_called_once()

    def test_run_does_not_expose_timeout_or_os_error_details(self):
        command = [self.directory / SECRET]
        failures = [
            subprocess.TimeoutExpired(command, 1, output=SECRET, stderr=SECRET),
            FileNotFoundError(2, SECRET, str(command[0])),
        ]
        for failure in failures:
            with self.subTest(error_type=type(failure).__name__), \
                    patch.object(smoke_cli.subprocess, 'run', side_effect=failure):
                with self.assertRaises(smoke_cli.SmokeFailure) as raised:
                    smoke_cli.run(command, cwd=self.directory, env={})
                self.assert_private_text(str(raised.exception))
                self.assertEqual(raised.exception.code, 'command-could-not-complete')
                self.assertIsNone(raised.exception.command)

    def test_run_accepts_the_explicit_expected_exit_code(self):
        command = [self.binaries / 'sa-listener']
        result = subprocess.CompletedProcess(command, 2, '', 'usage: --request\n')
        with patch.object(smoke_cli.subprocess, 'run', return_value=result) as run:
            self.assertIs(smoke_cli.run(command, cwd=self.directory, env={},
                                       expected=2, timeout=30), result)
        self.assertEqual(run.call_args.kwargs['timeout'], 30)
        self.assertTrue(run.call_args.kwargs['capture_output'])

    def test_verification_copies_wrapped_launcher_only_into_temporary_workspace(self):
        unrelated = self.directory / 'unrelated'
        unrelated.mkdir()
        before = self.binary_snapshot()
        documents = [{'id': 'offline-smoke-fixture'}]
        payload = json.dumps(documents)
        metadata = self.installed_metadata()
        wrapped_paths, commands = [], []

        def fake_run(argv, *, cwd, env, expected=0, timeout=120):
            argv = [str(value) for value in argv]
            commands.append(argv)
            self.assertEqual(Path(cwd), unrelated)
            executable = Path(argv[0])
            stdout, stderr = '', ''
            if '-c' in argv:
                code = argv[argv.index('-c') + 1]
                if 'import importlib.metadata' in code:
                    stdout = metadata
            elif '--help' in argv:
                stdout = 'usage: ' + executable.name + ' --request REQUEST\n'
            elif '--request' in argv:
                request = Path(argv[argv.index('--request') + 1])
                if request.name == 'invalid.json':
                    self.assertEqual(expected, 1)
                    stderr = 'star-wpa adapter failed: JSONDecodeError\n'
                elif executable.name == 'sa-deauth':
                    self.assertEqual(expected, 1)
                    stderr = 'star-wpa adapter failed: PermissionError\n'
                else:
                    stdout = payload
                    if '-m' not in argv and executable.parent != self.binaries:
                        wrapped_paths.append(executable)
                        self.assertTrue(executable.is_relative_to(unrelated))
                        self.assertEqual(executable.read_bytes(),
                                         (self.binaries / 'sa-listener').read_bytes())
            elif executable.name == 'sa-listener' and len(argv) == 1:
                self.assertEqual(expected, 2)
                stderr = 'usage: sa-listener --request REQUEST\n'
            else:
                self.fail('Unexpected smoke verifier subprocess: ' + repr(argv))
            return subprocess.CompletedProcess(argv, expected, stdout, stderr)

        with patch.object(smoke_cli, 'run', side_effect=fake_run), \
                patch.object(smoke_cli.subprocess, 'run',
                             side_effect=AssertionError('A real child must not run')), \
                contextlib.redirect_stdout(io.StringIO()):
            smoke_cli.verify_installation(
                Path('/offline/python'), self.binaries, {}, unrelated, self.scripts)
        self.assertEqual(len(wrapped_paths), 1)
        self.assertEqual(self.binary_snapshot(), before)
        self.assertFalse((self.binaries / '.sa-listener-wrapped').exists())
        self.assertEqual({Path(argv[0]).name for argv in commands if '--help' in argv},
                         set(self.scripts))
        for actor in ('listener', 'gpsd', 'kismet', 'wardrive', 'trilateration', 'deauth'):
            self.assertTrue(any(Path(argv[0]).name == 'sa-' + actor and '--request' in argv
                                for argv in commands), actor)
        python_commands = [argv for argv in commands if argv[0] == '/offline/python']
        self.assertEqual(len(python_commands), 3)
        for argv in python_commands:
            self.assertNotIn('-I', argv)
        self.assert_user_site_imports(python_commands, unrelated)

    def assert_user_site_imports(self, python_commands, unrelated):
        # An import-only child verifies the actual verifier flags against a
        # synthetic user installation. No pip, package install, or product
        # command runs, and the user's real home/site-packages are never used.
        userbase = self.directory / 'synthetic-user-base'
        scheme = sysconfig.get_preferred_scheme('user')
        usersite = Path(sysconfig.get_path('purelib', scheme=scheme,
                                          vars={'userbase': str(userbase)}))
        self.assertTrue(usersite.is_relative_to(userbase))
        usersite.mkdir(parents=True)
        (usersite / '_star_wpa_user_site_fixture.py').write_text(
            "VALUE = 'offline-user-site'\n", encoding='utf-8')
        environment = smoke_cli.clean_environment()
        environment.update(PYTHONUSERBASE=str(userbase), HOME=str(self.directory))
        environment.pop('PYTHONNOUSERSITE', None)
        flag_sets = set()
        for argv in python_commands:
            operation = '-c' if '-c' in argv else '-m'
            flag_sets.add(tuple(argv[1:argv.index(operation)]))
        for flags in sorted(flag_sets):
            result = self.real_subprocess_run([
                getattr(sys, '_base_executable', sys.executable), *flags, '-c',
                "import pathlib, sys; import _star_wpa_user_site_fixture as fixture; "
                "assert fixture.VALUE == 'offline-user-site'; "
                "assert pathlib.Path(fixture.__file__).resolve().is_relative_to("
                "pathlib.Path(sys.argv[1]).resolve()); print('user-site-import-ok')",
                str(userbase),
            ], cwd=unrelated, env=environment, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'user-site-import-ok\n')
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
