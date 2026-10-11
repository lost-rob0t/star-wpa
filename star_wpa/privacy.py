"""Offline privacy reduction. No custody ingestion, outbound transport or identity joins."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 100_000
EARTH_METERS = 6_371_008.8
HEADER_14 = tuple("MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,RCOIs,MfgrId,Type".split(","))
HEADER_11 = tuple(x for x in HEADER_14 if x not in ("Frequency", "RCOIs", "MfgrId"))
HEADER_9 = tuple(x for x in HEADER_11 if x not in ("AltitudeMeters", "AccuracyMeters"))
OUTPUT_HEADER = ("latitude", "longitude", "radio", "signal_dbm")
RADIOS = {"WIFI", "BT", "BLE", "CDMA", "GSM", "WCDMA", "LTE", "NR"}
MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\Z")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z", re.ASCII)


class PrivacyError(ValueError):
    """Messages are fixed diagnostics; never include captured values or paths."""


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PrivacyError("Invalid numeric value")
    if isinstance(value, str) and not NUMBER.fullmatch(value):
        raise PrivacyError("Invalid numeric value")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise PrivacyError("Invalid numeric value") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise PrivacyError("Numeric value outside supported range")
    return result


def integer(value, low, high):
    result = number(value, low, high)
    if result != math.trunc(result):
        raise PrivacyError("Expected an integer")
    return int(result)


def coordinates(lat, lon):
    # Zero is a valid coordinate, including (0, 0); never silently treat it as missing.
    return number(lat, -90, 90), number(lon, -180, 180)


def canonical_lon(lon):
    return (lon + 180) % 360 - 180


@dataclass(frozen=True, order=True)
class Observation:
    latitude: float
    longitude: float
    radio: str
    signal_dbm: int


def observation(lat, lon, radio, signal):
    lat, lon = coordinates(lat, lon)
    if not isinstance(radio, str) or radio not in RADIOS:
        raise PrivacyError("Unsupported radio type")
    return Observation(0.0 if lat == 0 else lat, 0.0 if abs(lat) == 90 else canonical_lon(lon), radio,
                       integer(signal, -200, 100))


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PrivacyError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise PrivacyError("Non-finite JSON number")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, RecursionError):
        raise PrivacyError("Invalid JSON document") from None


def keys(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise PrivacyError("Unexpected or missing fields")


def text_field(value):
    if not isinstance(value, str) or any(ord(c) < 32 and c not in "\r\n\t" for c in value):
        raise PrivacyError("Invalid text field")


def parse_warstar(text):
    data = strict_json(text)
    keys(data, {"dataset", "observations"}, {"device_id", "receiverId"})
    text_field(data["dataset"])
    if not any(data.get(k) for k in ("device_id", "receiverId")):
        raise PrivacyError("Missing source receiver identity")
    for key in ("device_id", "receiverId"):
        if key in data:
            text_field(data[key])
    rows = data["observations"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise PrivacyError("Invalid observation count")
    result = []
    for row in rows:
        keys(row, {"id", "address", "time", "latitude", "longitude", "level"},
             {"radio", "name", "security", "frequency"})
        if any(type(row[key]) is not int for key in ("id", "time", "level")):
            raise PrivacyError("WarStar integer fields must be JSON integers")
        if any(type(row[key]) not in (int, float) for key in ("latitude", "longitude")):
            raise PrivacyError("WarStar coordinates must be JSON numbers")
        integer(row["id"], 1, 2**53 - 1)
        integer(row["time"], 0, 2**53 - 1)
        if not isinstance(row["address"], str) or not MAC.fullmatch(row["address"]):
            raise PrivacyError("Invalid source address")
        for key in ("name", "security"):
            if key in row:
                text_field(row[key])
        if "frequency" in row:
            if type(row["frequency"]) is not int:
                raise PrivacyError("WarStar frequency must be a JSON integer")
            integer(row["frequency"], 0, 100_000_000)
        radio = row.get("radio", "WIFI")
        if not isinstance(radio, str):
            raise PrivacyError("Invalid radio type")
        radio = {"W": "WIFI", "B": "BT", "BLUETOOTH": "BT"}.get(radio.upper(), radio.upper())
        if radio not in {"WIFI", "BT", "BLE"}:
            raise PrivacyError("Unsupported WarStar radio")
        result.append(observation(row["latitude"], row["longitude"], radio, row["level"]))
    return tuple(result)


def validate_csv_quotes(text):
    # csv.reader(strict=True) still accepts stray quotes inside unquoted fields.
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                raise PrivacyError("Malformed CSV quoting")
        elif char in ",\r\n":
            state = "start"
        elif char == '"':
            if state != "start":
                raise PrivacyError("Malformed CSV quoting")
            state = "quoted"
        else:
            state = "bare"
    if state == "quoted":
        raise PrivacyError("Unterminated CSV quote")


def parse_wigle(text):
    validate_csv_quotes(text)
    try:
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(rows)
        version = None
        if header and header[0].startswith("WigleWifi-"):
            version = header[0]
            if version not in {"WigleWifi-1.4", "WigleWifi-1.6"}:
                raise PrivacyError("Unsupported WiGLE preamble version")
            names = set()
            for entry in header[1:]:
                key, sep, value = entry.partition("=")
                if not sep or key in names or key not in {"appRelease", "model", "release", "device", "display", "board", "brand", "star", "body", "subBody"}:
                    raise PrivacyError("Invalid WiGLE preamble")
                names.add(key)
                if key in {"star", "body", "subBody"} and value != {"star": "Sol", "body": "3", "subBody": "0"}[key]:
                    raise PrivacyError("Only Earth coordinates are supported")
            header = next(rows)
        if tuple(header) not in {HEADER_14, HEADER_11, HEADER_9}:
            raise PrivacyError("Unsupported or duplicate CSV header")
        if (version == "WigleWifi-1.4" and tuple(header) == HEADER_14) or (version == "WigleWifi-1.6" and tuple(header) != HEADER_14):
            raise PrivacyError("Preamble and header versions disagree")
        result = []
        for values in rows:
            if len(values) != len(header) or len(result) >= MAX_ROWS:
                raise PrivacyError("Invalid CSV row count or width")
            row = dict(zip(header, values))
            radio = row["Type"]
            if radio not in RADIOS:
                raise PrivacyError("Unsupported radio type")
            if radio in {"WIFI", "BT", "BLE"}:
                valid_address = MAC.fullmatch(row["MAC"])
            else:
                valid_address = re.fullmatch(r"[0-9]+_[0-9]+_[0-9]+", row["MAC"], re.ASCII)
            if not valid_address:
                raise PrivacyError("Invalid source address")
            if not re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", row["FirstSeen"], re.ASCII):
                raise PrivacyError("Invalid source timestamp")
            try:
                datetime.strptime(row["FirstSeen"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise PrivacyError("Invalid source timestamp") from None
            for name in ("Channel", "Frequency", "MfgrId"):
                if row.get(name):
                    integer(row[name], -1, 100_000_000)
            if not row["Channel"] and radio in {"WIFI", "BT", "BLE"}:
                raise PrivacyError("Missing channel")
            for name in ("AltitudeMeters", "AccuracyMeters"):
                if name in row:
                    number(row[name], 0 if name == "AccuracyMeters" else -100_000, 100_000_000)
            result.append(observation(row["CurrentLatitude"], row["CurrentLongitude"], radio, row["RSSI"]))
        if not result:
            raise PrivacyError("No observations")
        return tuple(result)
    except (csv.Error, StopIteration):
        raise PrivacyError("Malformed CSV document") from None


def parse_source(raw, format):
    if not raw or len(raw) > MAX_BYTES:
        raise PrivacyError("Invalid input size")
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise PrivacyError("Input must be UTF-8") from None
    text_field(text)
    if format == "wigle":
        return parse_wigle(text)
    if format == "warstar":
        return parse_warstar(text)
    raise PrivacyError("Select wigle or warstar input format")


@dataclass(frozen=True)
class Box:
    south: float
    west: float
    north: float
    east: float
    buffer_m: float = 100.0

    def __post_init__(self):
        south, west = coordinates(self.south, self.west)
        north, east = coordinates(self.north, self.east)
        if south > north:
            raise PrivacyError("South must not exceed north")
        for key, value in (("south", south), ("west", west), ("north", north), ("east", east),
                           ("buffer_m", number(self.buffer_m, 0, math.pi * EARTH_METERS))):
            object.__setattr__(self, key, value)

    def expanded(self):
        """Conservative spherical bounding expansion, not a precise polygon offset.

        Any radius-buffered point of the box is within this larger rectangle.
        Reaching either pole intentionally protects every longitude.
        """
        delta = math.degrees(self.buffer_m / EARTH_METERS)
        south, north = max(-90.0, self.south - delta), min(90.0, self.north + delta)
        span = 360.0 if self.east - self.west == 360 else (self.east - self.west) % 360
        if south <= -90 or north >= 90:
            return south, north, -180.0, 360.0
        ratio = math.sin(math.radians(delta)) / math.cos(math.radians(max(abs(self.south), abs(self.north))))
        longitude_delta = math.degrees(math.asin(min(1.0, ratio)))
        return south, north, self.west - longitude_delta, min(360.0, span + 2 * longitude_delta)

    def contains(self, lat, lon):
        south, north, west, width = self.expanded()
        offset = (lon - west) % 360
        return south - 1e-10 <= lat <= north + 1e-10 and (
            width >= 360 or offset <= width + 1e-10 or abs(offset - 360) <= 1e-10)


def sanitize(observations, boxes=(), decimals=2):
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 6:
        raise PrivacyError("Precision must be an integer from 0 to 6")
    if len(boxes) > 100 or not all(isinstance(box, Box) for box in boxes):
        raise PrivacyError("At most 100 exclusion boxes are supported")
    retained = set()
    excluded = 0
    for row in observations:
        coarse = observation(round(row.latitude, decimals), round(row.longitude, decimals), row.radio, row.signal_dbm)
        if any(box.contains(row.latitude, row.longitude) or box.contains(coarse.latitude, coarse.longitude) for box in boxes):
            excluded += 1
        else:
            retained.add(coarse)
    return tuple(sorted(retained)), excluded


def render_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(OUTPUT_HEADER)
    for row in rows:
        writer.writerow((format(row.latitude, ".6f"), format(row.longitude, ".6f"), row.radio, row.signal_dbm))
    return stream.getvalue().encode("utf-8")


@contextmanager
def safe_parent(path):
    """Walk every component by descriptor: reject symlinks and '..', including parents."""
    path = Path(path)
    if ".." in path.parts or not path.name or path.name in {".", ".."}:
        raise PrivacyError("Invalid local path")
    parts = (Path.cwd() / path if not path.is_absolute() else path).parts
    fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, parts[-1]
    finally:
        os.close(fd)


def read_source(path):
    with safe_parent(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise PrivacyError("Source must be a regular file")
            data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise PrivacyError("Input exceeds byte limit")
    return data


def export_new(path, rows):
    payload = render_csv(rows)
    with safe_parent(path) as (parent, name):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline privacy preview and new sanitized analysis CSV (not WiGLE upload).")
    parser.add_argument("source", help="local input; never modified")
    parser.add_argument("--format", choices=("wigle", "warstar"), required=True)
    parser.add_argument("--output", required=True, help="new CSV path; existing paths are refused")
    parser.add_argument("--port", type=int, default=0, help="loopback port; default chooses a free port")
    args = parser.parse_args(argv)
    try:
        rows = parse_source(read_source(args.source), args.format)
        from .privacy_ui import make_server
        with make_server(rows, args.output, args.port) as server:
            print(f"Open http://127.0.0.1:{server.server_port}/ locally. Ctrl-C stops preview.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as error:
        print("Privacy export failed: " + (str(error) if isinstance(error, PrivacyError) else type(error).__name__), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
