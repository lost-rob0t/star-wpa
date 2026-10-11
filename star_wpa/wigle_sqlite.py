"""Bounded local reader for completed WiGLE SQLite backups; no ingestion effects.

Rows and even derived summaries remain private. See docs/WIGLE-SQLITE.md for
the supported upstream schema, observation/summary distinction and limitations.
"""
import argparse
from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
import time


class WigleImportError(ValueError):
    """A fixed diagnostic that contains no source values or paths."""


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 512 * 1024 * 1024
    max_rows: int = 1_000_000
    max_seconds: float = 30.0
    max_vm_steps: int = 50_000_000
    batch_size: int = 256

    def __post_init__(self):
        for value, low, high in ((self.max_bytes, 100, 4 * 1024**3),
                                 (self.max_rows, 1, 10_000_000),
                                 (self.max_vm_steps, 1000, 1_000_000_000),
                                 (self.batch_size, 1, 1000)):
            if type(value) is not int or not low <= value <= high:
                raise WigleImportError("Invalid importer limit")
        if type(self.max_seconds) not in (int, float) or not 0 < self.max_seconds <= 300 or not math.isfinite(self.max_seconds):
            raise WigleImportError("Invalid importer time limit")


@dataclass(frozen=True)
class Reading:
    observation_id: int
    address: str
    signal_dbm: int | None
    latitude: float
    longitude: float
    altitude_m: float
    accuracy_m: float
    observed_at_ms: int
    external: bool
    network_radio_code: str
    network_name: str
    network_frequency: int
    network_capabilities: str
    source_signal_level: int


_MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\Z")
_RADIOS = frozenset({"W", "G", "C", "L", "D", "N", "B", "E", "F"})
_NETWORK = {"bssid": "TEXT", "ssid": "TEXT", "frequency": "INT", "capabilities": "TEXT", "type": "TEXT"}
_LOCATION = {"_id": "INTEGER", "bssid": "TEXT", "level": "INTEGER", "lat": "DOUBLE", "lon": "DOUBLE",
             "altitude": "DOUBLE", "accuracy": "FLOAT", "time": "LONG", "external": "INTEGER"}
_QUERY = """SELECT l._id, l.bssid, l.level, l.lat, l.lon, l.altitude,
 l.accuracy, l.time, l.external, n.type, n.ssid, n.frequency, n.capabilities
 FROM location AS l LEFT JOIN network AS n ON n.bssid = l.bssid
 ORDER BY l._id LIMIT ?"""


def _check_time(deadline):
    if time.monotonic() >= deadline:
        raise WigleImportError("Importer time budget exceeded")


def _stamp(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)


def _no_sidecars(path):
    if any(os.path.lexists(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal")):
        raise WigleImportError("Use a completed standalone backup without SQLite sidecars")


def _copy_snapshot(path, target, limits, deadline):
    # Never ask SQLite to open the operator's original or recover its journals.
    _no_sidecars(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not 100 <= before.st_size <= limits.max_bytes:
            raise WigleImportError("Backup must be a regular file within the byte limit")
        header = source.read(16)
        if header[:2] == b"\x1f\x8b":
            raise WigleImportError("Compressed input is not a SQLite backup; CSV gzip is a separate format")
        if header != b"SQLite format 3\x00":
            raise WigleImportError("Expected a SQLite backup")
        source.seek(0)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            total = 0
            while True:
                _check_time(deadline)
                chunk = source.read(min(1024 * 1024, limits.max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_bytes:
                    raise WigleImportError("Backup exceeds the byte limit")
                output.write(chunk)
        _no_sidecars(path)
        if total != before.st_size or _stamp(before) != _stamp(os.fstat(source.fileno())) or _stamp(before) != _stamp(os.stat(path, follow_symlinks=False)):
            raise WigleImportError("Backup changed while copying; use a completed stable export")


def _schema(db):
    objects = db.execute("SELECT type, name FROM sqlite_schema LIMIT 257").fetchall()
    if len(objects) > 256 or any(kind not in {"table", "index"} for kind, _ in objects):
        raise WigleImportError("Unsupported SQLite schema objects")
    tables = db.execute("PRAGMA table_list").fetchall()
    if any(row[2] in {"virtual", "shadow"} for row in tables):
        raise WigleImportError("Virtual tables are unsupported")
    for table, expected, key in (("network", _NETWORK, "bssid"), ("location", _LOCATION, "_id")):
        if not any(row[0] == "main" and row[1] == table and row[2] == "table" and row[4] == 0 for row in tables):
            raise WigleImportError("Missing supported WiGLE tables")
        # Only these literal, code-owned table names enter SQL.
        columns = db.execute(f"PRAGMA table_xinfo({table})").fetchall()
        fields = {row[1]: row for row in columns}
        if any(row[6] != 0 for row in columns) or any(name not in fields or fields[name][2].upper() != kind for name, kind in expected.items()):
            raise WigleImportError("Unsupported WiGLE column layout")
        if [row[1] for row in columns if row[5]] != [key] or fields[key][5] != 1:
            raise WigleImportError("Unsupported WiGLE primary key")
    if db.execute("PRAGMA integrity_check(1)").fetchall() != [("ok",)]:
        raise WigleImportError("SQLite integrity check failed")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise WigleImportError("Invalid observation integer")
    return value


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise WigleImportError("Invalid observation number")
    return float(value)


def _text(value, limit):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise WigleImportError("Invalid network text")
    return value


def _signal_dbm(value, radio):
    # WiGLE BluetoothReceiver uses Short.MIN_VALUE for missing EXTRA_RSSI.
    # Network summaries can later change from BT (B) to BLE (E).
    if type(value) is int and value == -32768 and radio in {"B", "E"}:
        return None
    return _integer(value, -200, 100)


def _reading(row):
    ident, address, signal, lat, lon, altitude, accuracy, at, external, radio, name, frequency, capabilities = row
    if radio is None:
        raise WigleImportError("Observation has no matching network summary")
    if radio not in _RADIOS:
        raise WigleImportError("Unsupported network radio code")
    address = _text(address, 128)
    if not address or (radio in {"W", "B", "E"} and not _MAC.fullmatch(address)):
        raise WigleImportError("Invalid source address")
    return Reading(_integer(ident, 1, 2**63 - 1), address, _signal_dbm(signal, radio),
                   _number(lat, -90, 90), _number(lon, -180, 180), _number(altitude, -100_000, 100_000_000),
                   _number(accuracy, 0, 100_000_000), _integer(at, 0, 2**63 - 1), bool(_integer(external, 0, 1)),
                   radio, _text(name, 4096), _integer(frequency, 0, 100_000_000), _text(capabilities, 4096), signal)


def _rows(db, limits, deadline):
    count = 0
    cursor = db.execute(_QUERY, (limits.max_rows + 1,))
    while True:
        _check_time(deadline)
        batch = cursor.fetchmany(limits.batch_size)
        if not batch:
            return
        for row in batch:
            _check_time(deadline)
            count += 1
            if count > limits.max_rows:
                raise WigleImportError("Observation row limit exceeded; no complete import")
            yield _reading(row)


@contextmanager
def read_backup(path, *, limits=Limits()):
    """Yield a bounded iterator over a private stable copy, then remove that copy.

    Consume only inside the context. Iteration can fail late; callers must not
    publish or commit partial results. No receiver identity or distance is inferred.
    Requires POSIX and SQLite >= 3.37 (table_list support).
    """
    if os.name != "posix" or sqlite3.sqlite_version_info < (3, 37, 0):
        raise WigleImportError("Importer requires POSIX and SQLite 3.37 or newer")
    if not isinstance(limits, Limits):
        raise WigleImportError("Expected importer Limits")
    deadline = time.monotonic() + limits.max_seconds
    try:
        with tempfile.TemporaryDirectory(prefix="star-wpa-wigle-") as directory:
            target = Path(directory) / "snapshot.sqlite"
            _copy_snapshot(Path(path).absolute(), target, limits, deadline)
            # immutable is safe here because only our completed private copy is opened.
            with closing(sqlite3.connect(target.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)) as db:
                db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 262_144)
                db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 65_536)
                db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 128)
                db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
                steps = 0

                def progress():
                    nonlocal steps
                    steps += 1000
                    return int(steps > limits.max_vm_steps or time.monotonic() >= deadline)

                db.set_progress_handler(progress, 1000)
                db.execute("PRAGMA query_only=ON")
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA temp_store=MEMORY")
                db.execute("PRAGMA cache_size=-2048")
                _schema(db)

                def authorize(action, table, column, database, trigger):
                    allowed = action == sqlite3.SQLITE_SELECT or (action == sqlite3.SQLITE_READ and database == "main" and table in {"location", "network"} and trigger is None)
                    return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY

                db.set_authorizer(authorize)
                iterator = _rows(db, limits, deadline)
                try:
                    yield iterator
                finally:
                    iterator.close()
    except (OSError, sqlite3.Error):
        # Never include sqlite errors, paths, schema content or row values.
        raise WigleImportError("Backup unreadable, invalid, or query budget exceeded") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read a completed local WiGLE SQLite backup; print private counts only.")
    parser.add_argument("source")
    parser.add_argument("--max-rows", type=int, default=Limits.max_rows)
    parser.add_argument("--max-bytes", type=int, default=Limits.max_bytes)
    parser.add_argument("--max-seconds", type=float, default=Limits.max_seconds)
    args = parser.parse_args(argv)
    try:
        limits = Limits(max_rows=args.max_rows, max_bytes=args.max_bytes, max_seconds=args.max_seconds)
        total, external, unknown_signal, codes = 0, 0, 0, {}
        with read_backup(args.source, limits=limits) as rows:
            for row in rows:
                total += 1
                external += row.external
                unknown_signal += row.signal_dbm is None
                codes[row.network_radio_code] = codes.get(row.network_radio_code, 0) + 1
        print(json.dumps({"format": "star-wpa-wigle-sqlite-summary-v1", "observations": total,
                          "externalObservations": external, "unknownSignalObservations": unknown_signal,
                          "observationsByNetworkRadioCode": codes}, sort_keys=True))
    except WigleImportError as error:
        print("WiGLE import failed: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("WiGLE import interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
