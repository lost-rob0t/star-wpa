"""External effects: bounded protocols and exact argv; no actor supervisor here."""
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import Request
from .http import open_http
from urllib.parse import urlparse
from .contracts import NS, document, stable_id, validate_bundle
from .ingest import ingest_airodump, ingest_gpsd, ingest_kismet, ingest_wardrive, mac, observations
from .trilateration import trilaterate

MAX_BYTES = 8 * 1024 * 1024


def bounded_int(value, label, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(label + f" must be an integer in 1..{maximum}")
    return value


def duration(request):
    return bounded_int(request.get("timeoutSeconds", 30), "timeoutSeconds", 300)


def command(actor, request, policy):
    policy = policy or {}
    if actor not in ("listener", "aircrack", "deauth"):
        raise ValueError("actor has no subprocess command")
    bssid = mac(request["bssid"]) if request.get("bssid") else None
    if actor in ("aircrack", "deauth") or bssid is not None:
        if bssid is None or bssid not in {mac(v) for v in policy.get("bssids", [])}:
            raise PermissionError("target BSSID is outside local operator scope")
    if actor in ("listener", "deauth"):
        interface = request["interface"]
        if not isinstance(interface, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", interface):
            raise ValueError("invalid interface")
        if interface not in policy.get("interfaces", []):
            raise PermissionError("interface is outside local operator scope")
    if actor == "deauth":
        if policy.get("allowDeauth") is not True:
            raise PermissionError("local policy does not authorize deauthentication")
        count = bounded_int(request.get("count", 1), "count", 100)
        argv = ["aireplay-ng", "--deauth", str(count), "-a", bssid]
        if request.get("station"):
            argv.extend(["-c", mac(request["station"])])
        return argv + [interface]
    if actor == "aircrack":
        if policy.get("allowAircrack") is not True:
            raise PermissionError("local policy does not authorize aircrack")
        # Local filenames are absolute argv tokens, never options or shell expressions.
        capture = str(Path(request["capture"]).resolve())
        wordlist = str(Path(request["wordlist"]).resolve())
        return ["aircrack-ng", "-b", bssid, "-w", wordlist, capture]
    if policy.get("allowListening") is not True:
        raise PermissionError("local policy does not authorize listening")
    argv = ["airodump-ng", "--output-format", "csv", "--write-interval", "1"]
    if bssid:
        argv.extend(["--bssid", bssid])
    if request.get("channel") is not None:
        argv.extend(["--channel", str(bounded_int(request["channel"], "channel", 233))])
    return argv + [interface]


def kismet_devices(request, policy=None):
    url = request["url"]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Kismet URL must be HTTP(S), without embedded credentials")
    # Operator supplies a concrete Kismet JSON endpoint; auth stays in environment.
    headers = {"Accept": "application/json"}
    env_name = "STAR_WPA_KISMET_TOKEN"
    if request.get("tokenEnv", env_name) != env_name:
        raise PermissionError("requests cannot select environment secrets")
    if os.environ.get(env_name):
        approved = (policy or {}).get("kismetTokenUrls", [])
        if not isinstance(approved, list) or url not in approved:
            raise PermissionError("credential destination is outside local operator scope")
        token = os.environ[env_name]
        auth = (policy or {}).get("kismetTokenAuth", "bearer")
        if auth == "bearer":
            headers["Authorization"] = "Bearer " + token
        elif auth == "cookie":
            # RFC 6265 cookie-octet; reject separators/control bytes before I/O.
            if any(ord(char) < 0x21 or ord(char) > 0x7e or char in '",;\\' for char in token):
                raise ValueError("invalid Kismet cookie token")
            headers["Cookie"] = "KISMET=" + token
        else:
            raise ValueError("unknown deployment Kismet token authentication")
    with open_http(Request(url, headers=headers), timeout=duration(request)) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Kismet response exceeds byte limit")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Kismet endpoint must return a device array")
    return data


def gpsd_reports(request):
    maximum = bounded_int(request.get("maxReports", 10), "maxReports", 1000)
    budget = duration(request)
    deadline = time.monotonic() + budget
    reports, total = [], 0
    with socket.create_connection((request.get("host", "127.0.0.1"), request.get("port", 2947)), timeout=budget) as sock:
        sock.sendall(b'?WATCH={"enable":true,"json":true};\n')
        with sock.makefile("rb") as stream:
            while len(reports) < maximum:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("GPSD collection deadline expired")
                sock.settimeout(remaining)
                line = stream.readline(MAX_BYTES + 1)
                if not line:
                    break
                total += len(line)
                if total > MAX_BYTES or not line.endswith(b"\n"):
                    raise ValueError("GPSD response exceeds byte limit or is truncated")
                report = json.loads(line)
                if report.get("class") == "TPV" and report.get("mode", 0) >= 2:
                    reports.append(report)
    if not reports:
        raise ValueError("GPSD returned no valid fixes")
    return reports


def capture(request, policy):
    argv = command("listener", request, policy)
    seconds = bounded_int(request.get("durationSeconds", 10), "durationSeconds", 300)
    # Own the entire tool process group. Session interruption also reaps the child.
    with tempfile.TemporaryDirectory(prefix="star-wpa-listener-") as directory:
        prefix = str(Path(directory) / "capture")
        argv[1:1] = ["--write", prefix]
        with open(os.devnull, 'wb') as errors:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True)
            try:
                try:
                    code = proc.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGINT)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=3)
                    code = 0  # Planned stop of a long-lived capture, not a tool failure.
                if code != 0:
                    raise RuntimeError("airodump-ng failed")
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if proc.poll() is None:
                    proc.wait(timeout=3)
            path = Path(prefix + "-01.csv")
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                raise ValueError("capture CSV is missing or exceeds limit")
            return path.read_text()


def dispatch(actor, request, policy=None):
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")
    # Validate the dataset before any external effect.
    document("event", request["dataset"], "wpa:preflight")
    if actor.startswith("tool-"):
        from .tools import dispatch_tool
        return dispatch_tool(actor[5:], request, policy)
    operation = request.get("operation", "ingest")
    if actor == "kismet":
        if operation == "collect":
            request = dict(request, devices=kismet_devices(request, policy))
        elif operation != "ingest":
            raise ValueError("unknown Kismet operation")
        return ingest_kismet(request)
    if actor == "gpsd":
        if operation == "collect":
            request = dict(request, reports=gpsd_reports(request))
        elif operation != "ingest":
            raise ValueError("unknown GPSD operation")
        return ingest_gpsd(request)
    if actor == "listener":
        if operation == "collect":
            request = dict(request, csv=capture(request, policy))
        elif operation != "ingest":
            raise ValueError("unknown listener operation")
        return ingest_airodump(request) if "csv" in request else observations(request)
    if actor == "wardrive":
        return ingest_wardrive(request)
    if actor == "trilateration":
        return trilaterate(request)
    if actor not in ("aircrack", "deauth"):
        raise ValueError("unknown wireless actor")
    identity = request.get("requestId")
    if not isinstance(identity, str) or not identity:
        raise ValueError("active effect needs a nonempty requestId for its receipt")
    argv = command(actor, request, policy)
    def execute():
        # Do not publish keys or subprocess output. Receipt proves process completion only.
        from .tools import run_tool
        result = run_tool(argv[0], {'argv': argv[1:], 'workingDirectory': str(Path.cwd()),
                          'stdinFile': None, 'uiMode': 'headless'}, duration(request))
        receipt = document("event", request["dataset"], stable_id("effect", request["dataset"], actor, identity),
                           eventKind="wireless-" + actor, extensions={NS: {"requestId": identity, "bssid": mac(request["bssid"]),
                           "exitCode": result['exitCode'], "outcome": "completed"}})
        return validate_bundle([receipt])
    from .effects import run_once
    return run_once(actor, request, execute)
