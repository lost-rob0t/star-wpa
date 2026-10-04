"""Effect adapter CLI. Native StarLang actors call this through star-process-port."""
import argparse
import json
import os
import sys
from pathlib import Path
from .adapters import MAX_BYTES, dispatch
from .tools import CATALOG


def load_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input exceeds byte limit")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actor", choices=["kismet", "gpsd", "listener", "aircrack", "deauth", "trilateration", "wardrive"] + ["tool-" + name for name in CATALOG])
    parser.add_argument("--request", required=True, help="operator-local request JSON file")
    args = parser.parse_args()
    try:
        # Policy is deployment configuration, never accepted from the incoming request.
        policy_file = os.environ.get("STAR_WPA_POLICY_FILE")
        policy = load_json(policy_file) if policy_file else None
        docs = dispatch(args.actor, load_json(args.request), policy)
        output = json.dumps(docs, separators=(",", ":"), allow_nan=False)
        if len(output.encode()) > MAX_BYTES:
            raise ValueError("output batch exceeds byte limit")
        print(output)
    except Exception as error:
        # Exceptions may contain credentials, captured keys or request data; emit type only.
        print("star-wpa adapter failed: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
