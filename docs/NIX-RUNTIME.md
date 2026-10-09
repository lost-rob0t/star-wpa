# Nix runtime on Ubuntu

Nix provides user-space programs and libraries on an existing Ubuntu host. It
is not a NixOS installation and does not configure the host. Keep the committed
`flake.lock`: `catalog/nix-tools.json` is tied to that exact nixpkgs revision.

## Profiles

From a checkout, with Nix flakes already enabled:

```sh
# All actor launchers, Python/jsonschema, and the three aircrack core binaries.
nix develop
sa-listener --request tests/fixtures/listener.json
nix run . -- listener --request tests/fixtures/listener.json
nix run .#native -- listener "$PWD/tests/fixtures/listener.json"

# Larger profile: every supported catalog provider and all actor launchers.
nix develop .#wireless
sa-tool-aircrack-ng --request tests/fixtures/tool-discovery.json
nix run .#wireless -- tool-aircrack-ng --request tests/fixtures/tool-discovery.json
nix run .#wireless-native -- tool-aircrack-ng "$PWD/tests/fixtures/tool-discovery.json"

# Package installation in a Nix profile is optional, and includes the wrappers.
nix profile install .#wireless
```

The default profile deliberately avoids downloading the complete GUI/SDR tool
collection just to process fixture data. Native launchers include SBCL, Bordeaux
Threads, the pinned StarLang source and installed Python dependencies. Both
shells include installed `star_wpa`, `jsonschema`, and the standalone `sa-*`
commands, so the installed offline laptop proof can import the same package.
The `adapters` package is the explicitly unbundled Python package for embedders.

## Exact coverage, including gaps

The explicit inventory maps all **57 catalog package actors**. Currently **43**
have declared pinned providers, including Debian-to-Nix name differences and
GNU Radio's wrapped OsmoSDR programs. Platform restrictions are reported at
flake evaluation; command presence is verified against built outputs.

These **14** do not have a supported provider in this pin:

- bluelog, blueranger, bluez-hcidump, btscanner
- eaphammer, eapmd5pass, fern-wifi-cracker, gr-gsm
- hostapd-wpe, king-phisher, mfterm, rtlsdr-scanner
- wifi-honey, wifiphisher

This is therefore **not yet a complete 57-tool Nix distribution**. These actors
remain installed, but Nix discovery returns `nix-unavailable` with a reason.
Adding one requires a reviewed source-and-hash-pinned derivation, a matching
inventory entry, and a passing executable discovery build. No unpinned pip,
apt, Git checkout, substitute program, or implicit download fills these gaps.

`bluez-hcidump` is intentionally unavailable: the pinned BlueZ 5.87 does not
install `hcidump`; `btmon` is not silently substituted. `mdk3` uses nixpkgs'
`mdk3-master` fork, `reaver` uses `reaverwps-t6x`, and `wifite` uses `wifite2`.
`rfcat` uses the pinned Python 3.12 scope because its `future` dependency does
not support the pin's default Python 3.14. `gr-osmosdr` uses GNU Radio with the OsmoSDR module, so its scripts receive the
matching Python module environment. `tshark` binds only the tshark executable
from the same Wireshark output used by the GUI actor; `rfkill` similarly binds
only rfkill from util-linux. This avoids unrelated executables in split-package
actors and conflicting Wireshark providers in the tool bundle.

Inspect evaluation coverage and build actual bindings separately:

```sh
nix build .#tool-coverage -o result-coverage
cat result-coverage
nix build .#tool-bindings -o result-bindings
cat result-bindings
nix build .#checks.x86_64-linux.runtime -L
nix flake check -L
```

`tool-coverage` is a declaration, not proof that a build succeeded. Building
`tool-bindings` fails if a declared provider is empty or lacks required
executables. Hash-verified manifests enumerate actual executable paths in
`/nix/store`. Executable hashing streams in 1 MiB chunks with a separate
512 MiB executable limit (large Go tools such as bettercap exceed 64 MiB);
request, manifest, and output limits remain unchanged. Every packaged actor wrapper sets the manifest and dependency
PATH, including `nix run` outside a development shell. A selected Nix manifest
wins over any host dpkg installation; missing packages stay visibly missing.
Explicit deployment-local pinned overrides remain available through policy.

The runtime check imports the installed package outside the checkout, clears
PATH and inherited manifest for each packaged `sa-tool-*` launcher, discovers
all 57 actors, and verifies actual store executable paths and required names.
It does **not** run the radio tools. CI builds and runs this check on x86_64
Ubuntu. aarch64 expressions are exposed, but an x86_64 CI pass is not evidence
of an aarch64 build or device test.

## Host prerequisites and safety boundary

Nix supplies user-space dependencies, not a working radio deployment. The host
still owns:

- Linux kernel, compatible wireless/Bluetooth/SDR drivers, firmware and hardware
- Device permissions, capabilities, groups, udev rules and monitor-mode setup
- Running GPSD/Kismet/Bluetooth/system D-Bus services and their configuration
- A working display/session for GUI tools; non-NixOS graphics/OpenGL integration
  can require host-specific setup
- Network endpoints, local policy, private effect-ledger directory and credentials

Nothing here installs host services/drivers, grants capabilities, changes groups,
starts daemons, downloads device firmware at runtime, or authorizes an RF action.
Tool presence does not imply any of those prerequisites are satisfied. Desktop
and live hardware behavior require separate operator-approved acceptance tests.
Keep exact command policy, credential destination and effect-replay protections
in force; use only your owned/authorized lab equipment.

## Provider evidence

Mappings were checked against the pinned [nixpkgs source](https://github.com/NixOS/nixpkgs/tree/e5bdc4a41d4c072fe1e3787eaa0320a384741d44),
including GNU Radio's wrapper and module scope. Exact unusual commands can be
cross-checked against upstream [OsmoSDR 0.2.6](https://github.com/osmocom/gr-osmosdr/blob/v0.2.6/apps/CMakeLists.txt),
[rfcat 2.0.1](https://github.com/atlas0fd00m/rfcat/blob/v2.0.1/setup.py),
[libfreefare 0.4.0](https://github.com/nfc-tools/libfreefare/blob/libfreefare-0.4.0/examples/Makefile.am),
and [BlueZ 5.87](https://github.com/bluez/bluez/blob/5.87/Makefile.tools).
Source inspection is distinct from the executable build check above.
