"""Package-backed Parrot wireless tool adapters, sharing the native actor effect port."""
import hashlib
import fcntl
import termios
import json
import os
import pty
import re
import selectors
import shutil
import signal
import subprocess
import time
from pathlib import Path
from .contracts import NS, document, stable_id, validate_bundle
from .effects import run_once

CATALOG_DATA = json.loads((Path(__file__).parent / 'tool_catalog.json').read_text())
CATALOG = {row['package']: row for row in CATALOG_DATA['packages']}
MAX_OUTPUT = 1024 * 1024


def package_query(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
    if len(result.stdout.encode()) > 8 * MAX_OUTPUT:
        raise ValueError('package query exceeded observation limit')
    return result


def owns(package, path):
    result = package_query(['dpkg-query', '--search', str(path)])
    for line in result.stdout.splitlines():
        if ': ' not in line:
            continue
        owners, filename = line.rsplit(': ', 1)
        if Path(filename) == path and any(owner.split(':')[0] == package for owner in owners.split(', ')):
            return True
    return False


def discover_package(package):
    if package not in CATALOG:
        raise ValueError('unknown catalog package')
    if not shutil.which('dpkg-query') or not shutil.which('dpkg'):
        return {'status': 'package-manager-unavailable', 'executables': []}
    architecture = package_query(['dpkg', '--print-architecture']).stdout.strip()
    restrictions = CATALOG[package]['architectureRestrictions']
    if '!' + architecture in restrictions:
        return {'status': 'architecture-excluded', 'architecture': architecture, 'executables': []}
    status = package_query(['dpkg-query', '--show', '--showformat=${db:Status-Status}\t${Version}', package])
    if status.returncode or not status.stdout.startswith('installed\t'):
        return {'status': 'not-installed', 'architecture': architecture, 'executables': []}
    executables = []
    listing = package_query(['dpkg-query', '--listfiles', package])
    if listing.returncode:
        raise RuntimeError('installed package file inventory unavailable')
    for value in listing.stdout.splitlines():
        path = Path(value)
        if path.parent not in (Path('/usr/bin'), Path('/usr/sbin'), Path('/bin'), Path('/sbin')):
            continue
        if path.is_file() and os.access(path, os.X_OK):
            resolved = path.resolve()
            if owns(package, resolved):
                executables.append({'name': path.name, 'path': str(resolved)})
    return {'status': 'installed', 'architecture': architecture, 'version': status.stdout.split('\t', 1)[1],
            'installation': 'dpkg', 'executables': sorted(executables, key=lambda item: (item['name'], item['path']))}


def pinned_installation(package, policy):
    binding = (policy or {}).get('toolInstallations', {}).get(package)
    if not binding:
        return None
    executables = []
    for name, entry in binding['executables'].items():
        if not re.fullmatch('[A-Za-z0-9_.+-]+', name):
            raise ValueError('invalid pinned executable name')
        path = Path(entry['path'])
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise FileNotFoundError('pinned tool executable is unavailable')
        if path.stat().st_size > 64 * MAX_OUTPUT:
            raise ValueError('pinned executable exceeds hashing bound')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise PermissionError('pinned tool executable has changed')
        executables.append({'name': name, 'path': str(path.resolve())})
    return {'status': 'installed', 'installation': binding.get('installation', 'operator-pinned'), 'version': binding['version'],
            'executables': sorted(executables, key=lambda item: item['name'])}


def descriptor(request):
    executable = request['executable']
    argv = request.get('argv', [])
    if not isinstance(executable, str) or not re.fullmatch('[A-Za-z0-9_.+-]+', executable):
        raise ValueError('executable must be a discovered basename')
    if not isinstance(argv, list) or len(argv) > 256 or any(not isinstance(arg, str) or '\0' in arg or len(arg) > 8192 for arg in argv):
        raise ValueError('argv must be a bounded array of literal tokens')
    working = Path(request['workingDirectory'])
    if not working.is_absolute() or not working.is_dir():
        raise ValueError('workingDirectory must be an existing absolute directory')
    stdin = request.get('stdinFile')
    if stdin is not None:
        path = Path(stdin)
        if not path.is_absolute() or not path.is_file() or path.stat().st_size > MAX_OUTPUT:
            raise ValueError('stdinFile must be an existing absolute file up to 1 MiB')
        stdin = str(path.resolve())
    mode = request.get('uiMode', 'headless')
    if mode not in ('headless', 'terminal', 'desktop'):
        raise ValueError('unknown UI mode')
    return {'executable': executable, 'argv': argv, 'workingDirectory': str(working.resolve()),
            'stdinFile': stdin, 'uiMode': mode}


def kill_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def run_tool(path, invocation, seconds):
    """Own/drain/reap a real process group; redact content and bound retained work."""
    selector = selectors.DefaultSelector()
    process = None
    handles, master, slave = [], None, None
    streams = {'stdout': {'bytes': 0, 'hash': hashlib.sha256()}, 'stderr': {'bytes': 0, 'hash': hashlib.sha256()}}
    terminal_input = b''
    try:
        if invocation['uiMode'] == 'terminal':
            master, slave = pty.openpty()
            os.set_blocking(master, False)
            if invocation['stdinFile']:
                terminal_input = Path(invocation['stdinFile']).read_bytes()
            process = subprocess.Popen([path, *invocation['argv']], cwd=invocation['workingDirectory'],
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
                preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
            os.close(slave); slave = None
            selector.register(master, selectors.EVENT_READ | (selectors.EVENT_WRITE if terminal_input else 0), 'stdout')
        else:
            source = open(invocation['stdinFile'], 'rb') if invocation['stdinFile'] else subprocess.DEVNULL
            if source != subprocess.DEVNULL:
                handles.append(source)
            process = subprocess.Popen([path, *invocation['argv']], cwd=invocation['workingDirectory'],
                stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            for label, stream in [('stdout', process.stdout), ('stderr', process.stderr)]:
                handles.append(stream)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
        deadline = time.monotonic() + seconds
        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(path, seconds)
            for key, mask in selector.select(min(remaining, 0.1)):
                if mask & selectors.EVENT_WRITE:
                    written = os.write(master, terminal_input[:4096])
                    terminal_input = terminal_input[written:]
                    if not terminal_input:
                        selector.modify(master, selectors.EVENT_READ, 'stdout')
                if mask & selectors.EVENT_READ:
                    try:
                        data = os.read(key.fd, 65536)
                    except OSError as error:
                        if master is not None and error.errno == 5:  # PTY EOF on Linux.
                            data = b''
                        else:
                            raise
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    stream = streams[key.data]
                    stream['bytes'] += len(data)
                    if stream['bytes'] > MAX_OUTPUT:
                        raise ValueError('tool output exceeded per-stream limit')
                    stream['hash'].update(data)
        code = process.wait(timeout=1)
        if code != 0:
            raise subprocess.CalledProcessError(code, path)
        return {'exitCode': code, 'stdoutBytes': streams['stdout']['bytes'], 'stderrBytes': streams['stderr']['bytes'],
                'stdoutSha256': streams['stdout']['hash'].hexdigest(), 'stderrSha256': streams['stderr']['hash'].hexdigest(),
                'streamsMerged': invocation['uiMode'] == 'terminal'}
    finally:
        if process is not None:
            kill_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                kill_group(process, signal.SIGKILL)
                process.wait(timeout=2)
            kill_group(process, signal.SIGKILL)  # Reap/fence same-group descendants retaining pipes.
        selector.close()
        for handle in handles:
            handle.close()
        if master is not None:
            os.close(master)
        if slave is not None:
            os.close(slave)


def dispatch_tool(package, request, policy=None):
    if package not in CATALOG:
        raise ValueError('unknown catalog package')
    dataset = request['dataset']
    document('event', dataset, 'wpa:tool-preflight')
    discovered = discover_package(package)
    manifest = os.environ.get('STAR_WPA_NIX_TOOL_MANIFEST')
    if discovered['status'] != 'installed' and manifest:
        raw = Path(manifest).read_bytes()
        if len(raw) > 8 * MAX_OUTPUT:
            raise ValueError('Nix tool manifest exceeds byte limit')
        discovered = pinned_installation(package, json.loads(raw)) or discovered
    binding = (policy or {}).get('toolInstallations', {}).get(package, {})
    if discovered['status'] != 'installed' or binding.get('preferPinned') is True:
        discovered = pinned_installation(package, policy) or discovered
    operation = request.get('operation', 'discover')
    if operation == 'discover':
        receipt = document('event', dataset, stable_id('tool-discovery', dataset, package, discovered),
                           eventKind='wireless-tool-discovery', extensions={NS: dict(discovered, package=package,
                           family=CATALOG[package]['family'], source=CATALOG[package]['source'], ui=CATALOG[package]['ui'])})
        return validate_bundle([receipt])
    if operation != 'execute':
        raise ValueError('tool operation must be discover or execute')
    if discovered['status'] != 'installed':
        raise FileNotFoundError('tool package is unavailable: ' + discovered['status'])
    invocation = descriptor(request)
    approved = (policy or {}).get('toolCommands', {}).get(package, [])
    if invocation not in approved:
        raise PermissionError('exact command is not authorized by deployment-local policy')
    matching = [entry for entry in discovered['executables'] if entry['name'] == invocation['executable']]
    if len(matching) != 1:
        raise PermissionError('requested executable has no unique package-owned binding')
    if invocation['uiMode'] == 'desktop' and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise RuntimeError('desktop display is unavailable')
    seconds = request.get('timeoutSeconds', 30)
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 300:
        raise ValueError('timeoutSeconds must be an integer in 1..300')
    identity = request.get('requestId')
    if not isinstance(identity, str) or not identity:
        raise ValueError('execute needs a nonempty requestId')
    def execute():
        result = run_tool(matching[0]['path'], invocation, seconds)
        receipt = document('event', dataset, stable_id('tool-execution', dataset, package, identity),
                           eventKind='wireless-tool-execution', extensions={NS: dict(result, package=package,
                           executable=invocation['executable'], packageVersion=discovered['version'],
                           installation=discovered.get('installation', 'dpkg'), requestId=identity,
                           uiMode=invocation['uiMode'], argvSha256=hashlib.sha256(json.dumps(invocation['argv']).encode()).hexdigest())})
        return validate_bundle([receipt])
    return run_once('tool-' + package, request, execute)
