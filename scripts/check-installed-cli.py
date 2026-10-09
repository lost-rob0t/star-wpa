#!/usr/bin/env python3
"""Offline shell smoke test: --installed checks your current installation without changes.

Without --installed, build/install a temporary wheel and exercise it outside the checkout.

Installed mode requires only Python 3.11+ and an existing star-wpa installation.
Default wheel mode additionally requires pip, setuptools, wheel and venv. A fresh virtual environment inherits those already installed
runtime dependencies; package code and scripts must come from the built wheel.
No package index, tool installation, radio, network service, or real credentials
are used. Run separately from unit tests: python3 scripts/check-installed-cli.py.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib

ROOT = Path(__file__).resolve().parents[1]


class SmokeFailure(RuntimeError):
    """An internal fixed failure code; never stores subprocess output or paths."""
    def __init__(self, code, command=None):
        super().__init__(code)
        self.code = code
        self.command = command


def run(argv, *, cwd, env, expected=0, timeout=120):
    try:
        result = subprocess.run([str(value) for value in argv], cwd=cwd, env=env,
                                text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise SmokeFailure('command-could-not-complete') from None
    if result.returncode != expected:
        # Child output and argv may contain local paths or sensitive data.
        raise SmokeFailure('unexpected-exit-status')
    return result


def require(condition, message, *, code='check-failed', command=None):
    if not condition:
        raise SmokeFailure(code, command)


def build_wheel_installation(base, environment, unrelated):
    source = base / 'source'
    source.mkdir()
    # Build a clean source copy so even build/egg-info never touch the checkout.
    for name in ('pyproject.toml', 'README.md', 'LICENSE'):
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(ROOT / 'star_wpa', source / 'star_wpa',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    wheels = base / 'wheels'
    run([sys.executable, '-m', 'pip', '--isolated', 'wheel', '--no-index', '--no-deps',
         '--no-build-isolation', '--no-cache-dir', '--wheel-dir', wheels, source],
        cwd=unrelated, env=environment)
    built = list(wheels.glob('star_wpa-*.whl'))
    require(len(built) == 1, 'Expected exactly one freshly built star-wpa wheel')
    virtualenv = base / 'venv'
    run([sys.executable, '-m', 'venv', '--system-site-packages', virtualenv], cwd=unrelated, env=environment)
    binaries = virtualenv / 'bin'
    python = binaries / 'python'
    run([python, '-m', 'pip', '--isolated', 'install', '--no-index', '--no-deps',
         '--no-cache-dir', '--ignore-installed', built[0]], cwd=unrelated, env=environment)
    # Remove the build input before proof: success cannot rely on that source.
    shutil.rmtree(source)
    return python, binaries, virtualenv


def verify_installation(python, binaries, environment, unrelated, expected_scripts,
                        expected_prefix=None, progress=None):
    progress = progress or (lambda name, status: None)
    progress('installation', 'running')
    require(binaries.is_dir(), 'command directory is unavailable', code='command-directory-missing')
    inspect = run([python, '-c', textwrap.dedent('''
    import importlib.metadata
    import json
    from pathlib import Path
    import sys
    import star_wpa
    from star_wpa import cli
    from star_wpa.contracts import SCHEMA
    from star_wpa.tools import CATALOG
    dist = importlib.metadata.distribution('star-wpa')
    if sys.argv[1]:
        prefix = Path(sys.argv[1]).resolve()
        assert Path(star_wpa.__file__).resolve().is_relative_to(prefix)
        assert Path(dist.locate_file('star_wpa')).resolve().is_relative_to(prefix)
    print(json.dumps({'scripts': {ep.name: ep.value for ep in dist.entry_points if ep.group == 'console_scripts'},
              'bindings': cli.COMMAND_ACTORS, 'tools': sorted(CATALOG),
              'schemaAvailable': bool(SCHEMA['$defs'])}))
    '''), str(expected_prefix or '')], cwd=unrelated, env=environment)
    installed = json.loads(inspect.stdout)
    require(installed['scripts'] == expected_scripts, 'Installed console-script metadata drift',
            code='command-inventory-mismatch')
    require(installed['schemaAvailable'], 'Installed wheel is missing its canonical schema', code='schema-unavailable')
    progress('installation', 'passed')
    progress('command-help', 'running')
    standalone = {name for name in expected_scripts if name.startswith('sa-')}
    require(set(installed['bindings']) == standalone, 'Installed registry does not cover the generated commands')
    for name in sorted(expected_scripts):
        executable = binaries / name
        require(executable.is_file(), 'Missing installed executable', code='command-missing', command=name)
        try:
            result = run([executable, '--help'], cwd=unrelated, env=environment, timeout=30)
        except SmokeFailure as error:
            raise SmokeFailure(error.code, name) from None
        require('--request' in result.stdout and result.stdout.startswith('usage: '),
                'Incomplete command help', code='command-help-invalid', command=name)
        require(not result.stderr, 'Unexpected stderr from help', code='command-help-stderr', command=name)
        if name.startswith('sa-'):
            require(result.stdout.startswith('usage: ' + name + ' '), 'Incorrect bound help name',
                    code='command-help-name-mismatch', command=name)
    progress('command-help', 'passed')
    print(f'PASS: installed package exposes all {len(standalone)} sa-* commands and star-wpa outside the checkout', flush=True)

    progress('offline-ingestion', 'running')

    def invoke(name, request, expected=0):
        path = unrelated / 'request.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        executable = binaries / name
        try:
            return run([executable, '--request', path], cwd=unrelated, env=environment, expected=expected)
        except SmokeFailure as error:
            raise SmokeFailure(error.code, name) from None

    common = {'dataset': 'lab', 'receiverId': 'offline-fixture'}
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
        request = {'dataset': 'lab', 'receiverId': 'r' + str(i), 'observations': [{
            'bssid': 'aa:bb:cc:dd:ee:ff', 'observedAt': 100 + i,
            'latitude': math.degrees(y / 6371008.8), 'longitude': math.degrees(x / 6371008.8),
            'distanceMeters': math.hypot(30 - x, 40 - y)}]}
        inputs.extend(json.loads(invoke('sa-listener', request).stdout))
    requests['trilateration'] = {'dataset': 'lab', 'documents': list({doc['id']: doc for doc in inputs}.values()),
                                 'windowSeconds': 10}
    bundles = []
    for actor, request in requests.items():
        result = invoke('sa-' + actor, request)
        require(not result.stderr, 'Unexpected ingestion stderr: ' + actor)
        documents = json.loads(result.stdout)
        require(isinstance(documents, list) and documents, 'Empty/non-array ingestion result: ' + actor)
        bundles.append(documents)
        generic = run([binaries / 'star-wpa', actor, '--request', unrelated / 'request.json'],
                      cwd=unrelated, env=environment)
        require(result.stdout == generic.stdout and not generic.stderr, 'Legacy CLI parity failure: ' + actor)
    evidence = unrelated / 'bundles.json'
    evidence.write_text(json.dumps(bundles), encoding='utf-8')
    run([python, '-c', textwrap.dedent('''
    import json, sys
    from star_wpa.contracts import validate_bundle
    with open(sys.argv[1]) as source:
        for bundle in json.load(source):
            validate_bundle(bundle)
    '''), evidence], cwd=unrelated, env=environment)
    # Renaming a launcher can change argv[0]; actor selection stays bound.
    wrapped = unrelated / '.sa-listener-wrapped'
    shutil.copy2(binaries / 'sa-listener', wrapped)
    (unrelated / 'request.json').write_text(json.dumps(requests['listener']), encoding='utf-8')
    result = run([wrapped, '--request', unrelated / 'request.json'], cwd=unrelated, env=environment)
    require(json.loads(result.stdout) == bundles[2] and not result.stderr, 'Wrapped script changed its actor')
    module = run([python, '-m', 'star_wpa', 'listener', '--request', unrelated / 'request.json'],
                 cwd=unrelated, env=environment)
    require(json.loads(module.stdout) == bundles[2], 'Installed python -m star_wpa compatibility failure')
    progress('offline-ingestion', 'passed')
    print('PASS: five offline core actors emit schema-valid batches; legacy CLI, module, and wrapped script remain compatible', flush=True)

    progress('error-and-policy-paths', 'running')
    secret = 'fixture-private-request-content'
    (unrelated / 'invalid.json').write_text('{"secret": "' + secret + '" invalid}', encoding='utf-8')
    malformed = run([binaries / 'sa-listener', '--request', unrelated / 'invalid.json'],
                    cwd=unrelated, env=environment, expected=1)
    require(not malformed.stdout and malformed.stderr == 'star-wpa adapter failed: JSONDecodeError\n',
            'Malformed input was not safely rejected')
    missing = run([binaries / 'sa-listener'], cwd=unrelated, env=environment, expected=2)
    require(not missing.stdout and '--request' in missing.stderr, 'Missing --request did not fail with usage')
    blocked = invoke('sa-deauth', {'dataset': 'lab', 'requestId': 'offline-proof',
        'bssid': 'aa:bb:cc:dd:ee:ff', 'interface': 'fixture0', 'allowDeauth': True,
        'policy': {'allowDeauth': True, 'interfaces': ['fixture0'], 'bssids': ['aa:bb:cc:dd:ee:ff']}}, expected=1)
    require(not blocked.stdout and blocked.stderr == 'star-wpa adapter failed: PermissionError\n',
            'Unapproved active effect was not safely rejected')
    require(secret not in malformed.stdout + malformed.stderr, 'Error exposed request contents')
    progress('error-and-policy-paths', 'passed')
    print('PASS: installed commands retain file-only usage, sanitized failures, and policy denial', flush=True)

def clean_environment():
    environment = {key: value for key, value in os.environ.items()
                   if key not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV') and not key.startswith('STAR_WPA_')}
    environment.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1',
                       PIP_NO_INDEX='1', PIP_NO_INPUT='1', PYTHONDONTWRITEBYTECODE='1')
    return environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed', action='store_true',
                        help='test the current Python installation without building or installing anything')
    parser.add_argument('--bin-directory', type=Path,
                        help='installed command directory (default: current Python executable directory); requires --installed')
    parser.add_argument('--summary', type=Path,
                        help='create a new private sanitized JSON report; existing files are never overwritten')
    args = parser.parse_args(argv)
    if args.bin_directory is not None and not args.installed:
        parser.error('--bin-directory requires --installed')
    report = None
    if args.summary is not None:
        try:
            fd = os.open(args.summary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            report = os.fdopen(fd, 'w', encoding='utf-8')
        except OSError as error:
            print('Cannot create summary: ' + type(error).__name__, file=sys.stderr)
            return 2
    summary = {'format': 'star-wpa-smoke-v1', 'mode': 'installed' if args.installed else 'wheel',
               'status': 'failed', 'checks': {}}
    def progress(name, status):
        summary['checks'][name] = status
    code = 1
    expected_scripts = {}
    try:
        progress('preflight', 'running')
        require(os.name == 'posix', 'This proof requires the project POSIX runtime')
        with (ROOT / 'pyproject.toml').open('rb') as source:
            expected_scripts = tomllib.load(source)['project']['scripts']
        environment = clean_environment()
        progress('preflight', 'passed')
        with tempfile.TemporaryDirectory(prefix='star-wpa-installed-cli-') as directory:
            base = Path(directory)
            unrelated = base / 'unrelated-working-directory'
            unrelated.mkdir()
            if args.installed:
                python = Path(sys.executable)
                binaries = (args.bin_directory or python.parent).absolute()
                expected_prefix = None
            else:
                progress('wheel-build-install', 'running')
                python, binaries, expected_prefix = build_wheel_installation(base, environment, unrelated)
                progress('wheel-build-install', 'passed')
            verify_installation(python, binaries, environment, unrelated, expected_scripts,
                                expected_prefix=expected_prefix, progress=progress)
        summary['status'] = 'passed'
        code = 0
    except KeyboardInterrupt:
        summary['errorType'] = 'KeyboardInterrupt'
        code = 130
        print('Smoke checks interrupted', file=sys.stderr)
    except Exception as error:
        # Never include child output, request data, paths, environment, or exception details.
        summary['errorType'] = type(error).__name__
        if isinstance(error, SmokeFailure):
            summary['failureCode'] = error.code
            if error.command in expected_scripts:
                summary['command'] = error.command
            print('Smoke checks failed: ' + error.code, file=sys.stderr)
        else:
            print('Smoke checks failed: ' + type(error).__name__, file=sys.stderr)
    finally:
        for name, status in summary['checks'].items():
            if status == 'running':
                summary['checks'][name] = 'failed'
        if report is not None:
            try:
                with report:
                    json.dump(summary, report, indent=2, sort_keys=True)
                    report.write('\n')
            except OSError as error:
                print('Cannot write summary: ' + type(error).__name__, file=sys.stderr)
                code = 1
    return code


if __name__ == '__main__':
    raise SystemExit(main())
