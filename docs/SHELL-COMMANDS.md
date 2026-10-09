# Standalone shell commands

Install Python 3.11+ and the package into your chosen environment:

```sh
python3 -m pip install .
# Or, for development:
python3 -m pip install -e .
```

The installer places the commands in that environment's `bin` directory. Activate
its virtual environment or put that directory on `PATH`. Commands work from any
working directory; they do not require a checkout, SBCL, or an actor supervisor.
These are the same effect adapters used by the native StarLang actors, not a
second native runtime. The Nix `star-wpa`/default package includes the same commands:

```sh
nix build .
./result/bin/sa-listener --help
```

## Request and result contract

```sh
sa-listener --help
sa-listener --request /absolute/path/listener-request.json > documents.json
sa-tool-kismet --request /absolute/path/discovery-request.json > discovery.json
# The original interface remains supported:
star-wpa listener --request /absolute/path/listener-request.json
```

Every command requires `--request FILE`: one operator-local regular file containing
one JSON object with a nonempty `dataset`. Relative filenames resolve from the
calling shell's current directory. There is no implicit stdin input (`-` is a
literal filename), no arbitrary executable/argument passthrough, and no automatic
publication of results. `--help` needs neither a request nor tool installation.

Success writes one compact, validated JSON document array and a newline to stdout.
Failures write a sanitized diagnostic to stderr with no exception details, request
content, credentials, or tool output. Exit statuses are:

- `0`: successful validated result, or help
- `1`: input, policy, dependency, tool, or output failure (including a missing file)
- `2`: invalid command-line usage
- `130`: keyboard interruption; an admitted active attempt remains uncertain

The existing 8 MiB JSON input/output bounds and regular-file requirement apply.
Use a separate private policy file through `STAR_WPA_POLICY_FILE`; request JSON
cannot grant permission. Kismet bearer tokens still require the exact destination
in local `kismetTokenUrls`, HTTP redirects are refused, and active effects require
the private, owned mode-0600 `STAR_WPA_EFFECT_DB` ledger. Execution remains gated by
the existing core or exact tool-command policy. Commands do not install radio
tools, change monitor mode, elevate privileges, or authorize a target.

## Core actors

| Command | Existing actor | Request documentation |
|---|---|---|
| `sa-kismet` | `kismet` | Kismet ingestion/collection |
| `sa-gpsd` | `gpsd` | GPSD ingestion/collection |
| `sa-listener` | `listener` | airodump/receiver observations |
| `sa-aircrack` | `aircrack` | Existing scoped effect |
| `sa-deauth` | `deauth` | Existing scoped effect |
| `sa-trilateration` | `trilateration` | Receiver multilateration |
| `sa-wardrive` | `wardrive` | Wardrive export ingestion |

See [the main request and policy documentation](../README.md#use-the-actors).
Fixture requests for passive ingestion are in `tests/fixtures/`; active actors
have no permission by default. Only use effects within your authorized scope.

## All package tool actors

Each of the 57 package actors has the unambiguous `sa-tool-<package>` spelling.
The short `sa-<package>` spelling is also installed except for `kismet` and `gpsd`,
whose short names select the core actors above. This resolves collisions without
silently changing the behavior of either actor.

| Package | Short command | Qualified command |
|---|---|---|
| `aircrack-ng` | `sa-aircrack-ng` | `sa-tool-aircrack-ng` |
| `airgeddon` | `sa-airgeddon` | `sa-tool-airgeddon` |
| `asleap` | `sa-asleap` | `sa-tool-asleap` |
| `bettercap` | `sa-bettercap` | `sa-tool-bettercap` |
| `bluelog` | `sa-bluelog` | `sa-tool-bluelog` |
| `blueranger` | `sa-blueranger` | `sa-tool-blueranger` |
| `bluesnarfer` | `sa-bluesnarfer` | `sa-tool-bluesnarfer` |
| `bluez` | `sa-bluez` | `sa-tool-bluez` |
| `bluez-hcidump` | `sa-bluez-hcidump` | `sa-tool-bluez-hcidump` |
| `btscanner` | `sa-btscanner` | `sa-tool-btscanner` |
| `bully` | `sa-bully` | `sa-tool-bully` |
| `cowpatty` | `sa-cowpatty` | `sa-tool-cowpatty` |
| `crackle` | `sa-crackle` | `sa-tool-crackle` |
| `eaphammer` | `sa-eaphammer` | `sa-tool-eaphammer` |
| `eapmd5pass` | `sa-eapmd5pass` | `sa-tool-eapmd5pass` |
| `fern-wifi-cracker` | `sa-fern-wifi-cracker` | `sa-tool-fern-wifi-cracker` |
| `gnuradio` | `sa-gnuradio` | `sa-tool-gnuradio` |
| `gpsd` | (core actor owns this name) | `sa-tool-gpsd` |
| `gqrx-sdr` | `sa-gqrx-sdr` | `sa-tool-gqrx-sdr` |
| `gr-gsm` | `sa-gr-gsm` | `sa-tool-gr-gsm` |
| `gr-osmosdr` | `sa-gr-osmosdr` | `sa-tool-gr-osmosdr` |
| `hackrf` | `sa-hackrf` | `sa-tool-hackrf` |
| `hcxdumptool` | `sa-hcxdumptool` | `sa-tool-hcxdumptool` |
| `hcxtools` | `sa-hcxtools` | `sa-tool-hcxtools` |
| `hostapd` | `sa-hostapd` | `sa-tool-hostapd` |
| `hostapd-wpe` | `sa-hostapd-wpe` | `sa-tool-hostapd-wpe` |
| `inspectrum` | `sa-inspectrum` | `sa-tool-inspectrum` |
| `iw` | `sa-iw` | `sa-tool-iw` |
| `king-phisher` | `sa-king-phisher` | `sa-tool-king-phisher` |
| `kismet` | (core actor owns this name) | `sa-tool-kismet` |
| `libfreefare-bin` | `sa-libfreefare-bin` | `sa-tool-libfreefare-bin` |
| `libnfc-bin` | `sa-libnfc-bin` | `sa-tool-libnfc-bin` |
| `mdk3` | `sa-mdk3` | `sa-tool-mdk3` |
| `mdk4` | `sa-mdk4` | `sa-tool-mdk4` |
| `mfcuk` | `sa-mfcuk` | `sa-tool-mfcuk` |
| `mfoc` | `sa-mfoc` | `sa-tool-mfoc` |
| `mfterm` | `sa-mfterm` | `sa-tool-mfterm` |
| `multimon-ng` | `sa-multimon-ng` | `sa-tool-multimon-ng` |
| `pixiewps` | `sa-pixiewps` | `sa-tool-pixiewps` |
| `reaver` | `sa-reaver` | `sa-tool-reaver` |
| `redfang` | `sa-redfang` | `sa-tool-redfang` |
| `rfcat` | `sa-rfcat` | `sa-tool-rfcat` |
| `rfkill` | `sa-rfkill` | `sa-tool-rfkill` |
| `rtl-433` | `sa-rtl-433` | `sa-tool-rtl-433` |
| `rtl-sdr` | `sa-rtl-sdr` | `sa-tool-rtl-sdr` |
| `rtlsdr-scanner` | `sa-rtlsdr-scanner` | `sa-tool-rtlsdr-scanner` |
| `soapysdr-tools` | `sa-soapysdr-tools` | `sa-tool-soapysdr-tools` |
| `tshark` | `sa-tshark` | `sa-tool-tshark` |
| `ubertooth` | `sa-ubertooth` | `sa-tool-ubertooth` |
| `uhd-host` | `sa-uhd-host` | `sa-tool-uhd-host` |
| `wifi-honey` | `sa-wifi-honey` | `sa-tool-wifi-honey` |
| `wifiphisher` | `sa-wifiphisher` | `sa-tool-wifiphisher` |
| `wifite` | `sa-wifite` | `sa-tool-wifite` |
| `wireless-tools` | `sa-wireless-tools` | `sa-tool-wireless-tools` |
| `wireshark` | `sa-wireshark` | `sa-tool-wireshark` |
| `wpasupplicant` | `sa-wpasupplicant` | `sa-tool-wpasupplicant` |
| `yersinia` | `sa-yersinia` | `sa-tool-yersinia` |

Tool discovery uses a request such as `{"dataset":"lab","operation":"discover"}`.
A missing package is a successful discovery result with `status: "not-installed"`,
not an execution success. Execute requests preserve the documented package-owned
executable binding, exact argv/UI policy, time/output bounds, and replay ledger.
See [tool requests and policy](PARROT-TOOLS.md). No live wireless effects are
required to verify the commands.

## Maintenance and offline verification

`python3 scripts/build-tool-actors.py` regenerates tool declarations and the
`[project.scripts]` table from the catalog and core actor inventory. Commit generated
changes together with source changes. `--check` rejects stale entry points.

```sh
python3 scripts/build-tool-actors.py --check
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check-installed-cli.py
```

The installed-package proof builds a wheel without network access, installs it in
a fresh environment, and runs every command from outside the source tree. Its
prerequisites are the package dependencies plus setuptools, wheel, pip and venv.
All behavior checks use offline data or mocked effects; native runtime and physical
hardware checks remain separate.
