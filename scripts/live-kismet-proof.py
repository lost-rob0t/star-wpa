#!/usr/bin/env python3
"""Opt-in deployed Kismet acceptance proof.

This script never supplies credentials itself. It requires the deployment to
provide STAR_WPA_KISMET_TOKEN and STAR_WPA_POLICY_FILE, runs the maintained
star-wpa Kismet CLI, validates the returned canonical bundle, and prints only a
sanitized summary unless --documents-out is explicitly requested.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from star_wpa.adapters import MAX_BYTES
from star_wpa.contracts import validate_bundle


REQUIRED_ENV = ("STAR_WPA_KISMET_TOKEN", "STAR_WPA_POLICY_FILE")


def private_write(path, text):
    target = Path(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the maintained Kismet adapter against a deployed endpoint and emit sanitized proof."
    )
    parser.add_argument("--request", required=True, help="operator-local Kismet collection request JSON")
    parser.add_argument("--documents-out", help="optional new private file for canonical documents")
    parser.add_argument("--process-timeout", type=int, default=330,
                        help="outer process deadline in seconds; default 330")
    args = parser.parse_args(argv)

    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        print("live Kismet proof blocked: missing deployment credential or policy", file=sys.stderr)
        return 2
    if args.process_timeout < 1 or args.process_timeout > 360:
        print("live Kismet proof blocked: process timeout must be 1..360", file=sys.stderr)
        return 2

    result = subprocess.run(
        [sys.executable, "-m", "star_wpa", "kismet", "--request", args.request],
        capture_output=True,
        text=True,
        timeout=args.process_timeout,
    )
    if result.returncode:
        message = result.stderr.strip() or "star-wpa adapter failed"
        print("live Kismet proof failed: " + message, file=sys.stderr)
        return result.returncode

    raw = result.stdout.strip()
    if len(raw.encode()) > MAX_BYTES:
        print("live Kismet proof failed: output exceeds byte limit", file=sys.stderr)
        return 1
    try:
        documents = json.loads(raw)
        validate_bundle(documents)
    except Exception as error:
        print("live Kismet proof failed: " + type(error).__name__, file=sys.stderr)
        return 1

    if args.documents_out:
        try:
            private_write(args.documents_out, json.dumps(documents, separators=(",", ":"), allow_nan=False) + "\n")
        except Exception as error:
            print("live Kismet proof failed: " + type(error).__name__, file=sys.stderr)
            return 1

    dtypes = Counter(document["dtype"] for document in documents)
    versions = sorted({document["schemaVersion"] for document in documents})
    datasets = sorted({document["dataset"] for document in documents})
    summary = {
        "ok": True,
        "documents": len(documents),
        "empty": not documents,
        "dtypes": dict(sorted(dtypes.items())),
        "schemaVersions": versions,
        "datasets": datasets,
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
