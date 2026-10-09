"""Effect adapter CLI. Native StarLang actors call this through star-process-port."""
import argparse
import json
import os
import sys
from pathlib import Path
from .adapters import MAX_BYTES, dispatch
from .tools import CATALOG
from .cli import CORE_ACTORS
from .files import read_bounded


def load_json(path):
    return json.loads(read_bounded(path, MAX_BYTES))


def main(argv=None, *, actor=None, prog=None):
    description = (__doc__ if actor is None else
                   f"Run the {actor} adapter independently using an operator-local JSON request. "
                   "Returns a validated JSON document batch on stdout; local policy still applies.")
    parser = argparse.ArgumentParser(prog=prog, description=description)
    if actor is None:
        parser.add_argument("actor", choices=list(CORE_ACTORS) + ["tool-" + name for name in CATALOG])
    parser.add_argument("--request", required=True, help="operator-local request JSON file")
    args = parser.parse_args(argv)
    try:
        # Policy is deployment configuration, never accepted from the incoming request.
        policy_file = os.environ.get("STAR_WPA_POLICY_FILE")
        policy = load_json(policy_file) if policy_file else None
        docs = dispatch(actor if actor is not None else args.actor, load_json(args.request), policy)
        output = json.dumps(docs, separators=(",", ":"), allow_nan=False)
        if len(output.encode()) > MAX_BYTES:
            raise ValueError("output batch exceeds byte limit")
        print(output)
    except KeyboardInterrupt:
        print("star-wpa adapter interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        # Exceptions may contain credentials, captured keys or request data; emit type only.
        print("star-wpa adapter failed: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
