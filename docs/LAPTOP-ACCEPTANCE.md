# One hour Ubuntu laptop acceptance

Use this checklist to verify the installed shell commands on the Ubuntu
laptop in one hour. The required run is offline and uses synthetic data. It
does not build or install packages, contact services, use radios, or require
`sudo`. No Ubuntu package-manager changes are made by this check; use the
existing prepared environment, including a suitable Nix environment when available.

## Before arriving home

On an already prepared development machine, the repository tests and default
`python3 scripts/check-installed-cli.py` can establish the offline wheel and
command behavior described in [SHELL-COMMANDS.md](SHELL-COMMANDS.md). That default
mode builds and installs into a temporary environment; it is separate from the
installed-only laptop check below. Record actual results rather than assuming
that a checked-in script or merged change passed.

Have the approved checkout/revision, Python 3.11+, and its matching `star-wpa`
installation with runtime dependencies ready before the hour starts. A wheel
proof elsewhere cannot establish the laptop's current installation or hardware
readiness. The standalone check does not require SBCL, a native actor runtime,
radio tools, Kismet, or GPSD.

## Minutes 0 to 10 check the environment

Open the prepared checkout and activate the existing Python environment you
intend to test. Inspect its state without switching branches or replacing work:

```sh
git status --short
git branch --show-current
git rev-parse HEAD
python3 --version
python3 -c 'import sys; assert sys.version_info >= (3, 11); from importlib.metadata import version; print("star-wpa", version("star-wpa")); print("jsonschema", version("jsonschema"))'
python3 scripts/check-installed-cli.py --help
```

Confirm the branch/revision is the approved one and the script offers
`--installed` and `--summary`. The selected Python must have `star-wpa` and its
dependencies already installed. If anything is missing or mismatched, record
that blocker. Installation, upgrades, network configuration, and privilege
changes need a separately agreed plan; this checklist does not perform them.

## Minutes 10 to 25 run the offline smoke check

Run from the checkout, using the selected environment's Python:

```sh
python3 scripts/check-installed-cli.py --installed --summary /tmp/star-wpa-smoke-summary.json
```

If launchers are in a different directory from the interpreter's scripts
directory, add `--bin-directory PATH` with the existing launcher directory.
Do not substitute launchers from an unrelated installation to make a check pass.

The check runs commands from outside the checkout and covers:

- Installed command inventory, bindings, packaged schema, and every command's help
- Five synthetic core ingests: Kismet, GPSD, listener, wardrive, and trilateration
- Schema-valid output and compatibility with the original CLI and module entry
- Safe error paths and rejection of an unapproved active effect

A policy-denial pass means the operation was refused; it is not an active radio
test. The run uses no live networks, radios, services, or real credentials.

## Minutes 25 to 40 resolve one blocker

Inspect the failed check and optional `failureCode`/`command` in the sanitized
summary. `command-directory-missing` or `command-missing` means the selected
launcher directory is incomplete; `command-inventory-mismatch` means the
installation differs from this checkout. Fix only a small, understood problem
within the agreed scope, such as selecting the intended existing Python
environment or launcher directory. If the fix needs installation, a policy change, a service
startup, or an interface change, stop and report the prerequisite instead.

If the offline check passes and time remains, an optional collector check may
read from an already-running local Kismet/GPSD deployment only after the exact
URL or endpoint, device, permitted data scope, and local policy are explicitly
agreed. Keep credentials local. Do not start services, alter interfaces, enable
monitor mode, or expand permissions as part of this session. Skip this optional
step when its scope or prerequisites are unclear.

## Minutes 40 to 55 repeat and retain evidence

After any permitted correction, repeat the same check with a new output name:

```sh
python3 scripts/check-installed-cli.py --installed --summary /tmp/star-wpa-smoke-summary-repeat.json
```

The summary is sanitized for sharing and newly created with mode `0600`.
Existing output paths are refused, not overwritten; use another unused name on
later runs. Exit `0` means all checks passed, `1` means a failed check/report write,
`2` means usage or report creation failed, and `130` means interrupted. Retain the latest summary and its exit status, including failures.
Do not reinterpret an incomplete run as a pass. Copy wanted summaries into your
private evidence storage before temporary files are cleaned up.

## Minutes 55 to 60 report the result

Share the sanitized summary, tested revision, Python/package versions, overall
pass or fail, and the first remaining blocker or next prerequisite. Identify an
optional collector check separately as passed, failed, or not run. Do not share
raw requests, environment dumps, logs, credentials, SSIDs, MAC addresses, real
endpoint URLs, or local filesystem paths.

An offline pass establishes installed shell behavior on this laptop. It does
not prove radio/driver support, physical capture, GPS reception or fix quality,
a real Kismet deployment, RF location accuracy, native runtime integration,
CouchDB publication, or successful active effects. Those need separately scoped
integration evidence.
