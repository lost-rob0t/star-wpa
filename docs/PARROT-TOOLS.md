# Parrot wireless tool actors

The pinned `parrot-tools-wireless` stanza from ParrotSec/parrot-tools commit `a5c278bc04319cf8b0b9e377edd7a46084e63f87` is the coverage authority. All **31** recommended packages have actors. Architecture exclusions are preserved. The catalog adds **26** explicit supplemental packages, for **57 tool actors** plus the seven specialized actors.

Baseline packages: aircrack-ng, airgeddon, asleap, bluelog, blueranger, bluesnarfer, bluez-hcidump, btscanner, bully, cowpatty, crackle, eapmd5pass, fern-wifi-cracker, hackrf, inspectrum, king-phisher, libfreefare-bin, libnfc-bin, mdk3, mfcuk, mfoc, mfterm, pixiewps, reaver, redfang, rfcat, rtlsdr-scanner, ubertooth, wifi-honey, wifite and yersinia.

Supplemental packages: bettercap, bluez, eaphammer, gnuradio, gpsd, gqrx-sdr, gr-gsm, gr-osmosdr, hcxdumptool, hcxtools, hostapd, hostapd-wpe, iw, kismet, mdk4, multimon-ng, rfkill, rtl-433, rtl-sdr, soapysdr-tools, tshark, uhd-host, wifiphisher, wireless-tools, wireshark and wpasupplicant.

**Wifiphisher** is the likely evil-twin Wi-Fi phishing tool from the request. Airgeddon, EAPHammer and hostapd-wpe are also included. Their adapters use the same bounded execution and exact-command policy as the rest of the catalog. King Phisher remains because Parrot lists it, although it is not a radio tool. Web/session tools such as Evilginx are outside this wireless catalog.

## What support means

Each `wpa-tool-PACKAGE` declaration is compiled and run by the existing native StarLang runtime. `tool-PACKAGE` is its dispatch capability. Every catalog entry has discovery and bounded execution support. Specialized Kismet, GPSD, airodump and wardrive adapters still own radio observation normalization; generic tool execution produces canonical completion/provenance events, not inferred wireless records or successful-attack claims.

Support here is package-level executable invocation. Tool-specific flags, GUI workflows, full interactive auditing sessions, radio permissions, physical hardware and every upstream output format have not been integration-tested. The pinned metapackage is a reproducible baseline, not a timeless claim that every radio-related executable ever shipped by Parrot has been enumerated. Installations report missing packages and architecture exclusions explicitly.

## Discover executables

```sh
nix run . -- tool-wifiphisher --request tests/fixtures/tool-discovery.json
nix run .#native -- tool-wifiphisher "$PWD/tests/fixtures/tool-discovery.json"
```

On Parrot/Debian, discovery uses dpkg status, version and file lists, then verifies executable ownership after resolving symlinks. Any binary in the package's bin/sbin directories is eligible, including suite commands rather than just the package's primary name. Unowned PATH overrides are never selected. Discovery reports real installed state and does not install packages or start radios.

Nix tools are available through `nix develop .#wireless`. That shell supplies `STAR_WPA_NIX_TOOL_MANIFEST`, containing versioned, hash-checked executable bindings generated from the available immutable nixpkgs package roots. This optional shell/tool bundle can be large. `nix build .#tool-coverage` emits a JSON availability report; missing nixpkgs packages are labelled unavailable and are not replaced by a different application. `nix build .#tool-bindings` builds the explicit bindings. The default application does not pull in the entire wireless suite.

Source-installed tools can be explicitly bound in deployment-local `toolInstallations`:

```json
{"toolInstallations":{"eaphammer":{"version":"YOUR_PINNED_REVISION","executables":{"eaphammer":{"path":"/opt/eaphammer/eaphammer","sha256":"SHA256_OF_EXECUTABLE"}}}}}
```

Executable hashes are checked on each dispatch. This binds the entrypoint, not all Python modules, configuration or host dependencies. `preferPinned: true` selects an explicit binding even if a Debian package exists. No secret values belong in catalog files or committed policy.

## Execute an approved command

The operator's `STAR_WPA_POLICY_FILE` contains exact descriptors. For example, to approve a tool's local help invocation:

```json
{"toolCommands":{"wifiphisher":[{"executable":"wifiphisher","argv":["--help"],"workingDirectory":"/tmp/wireless-lab","stdinFile":null,"uiMode":"headless"}]}}
```

The request mirrors the descriptor and adds `dataset`, `operation: "execute"`, a unique `requestId` and optional `timeoutSeconds` (1–300). The working directory must exist and be absolute. `STAR_WPA_EFFECT_DB` supplies the existing at-most-once ledger. Incoming requests cannot approve themselves. Exact argv tokens, working directory, stdin file and UI mode must match local policy. Changing a completed request's payload under the same ID is rejected; uncertain effects remain blocked for operator reconciliation.

A package can contain shell-based orchestration tools. Their internal subprocesses/options are not separately sandboxed or reauthorized; the operator must approve the whole exact invocation and its scope. Arguments and raw stdout/stderr are excluded from receipts; hashes and byte counts are retained. Tool-created files stay in the approved working directory or paths explicitly named in argv. This is an invocation port, not a filesystem sandbox.

`headless` supports CLI tools and bounded stdin files. `terminal` allocates a real controlling PTY and optionally replays an approved input file up to 1 MiB; it is a bounded scripted session, not a persistent human console. PTY output streams are merged. `desktop` requires an existing DISPLAY or WAYLAND_DISPLAY and host GUI access. A display variable alone does not establish that a particular GUI can launch. All modes bound output to 1 MiB per stream, own/drain/reap process groups, and fail on timeouts or nonzero exits rather than claim completion.

## Nix workflow

```sh
nix develop
nix flake check -L
nix build .#star-wpa .#native
nix run . -- --help
```

The flake locks nixpkgs, StarLang and Parrot source revisions. Both x86_64-linux and aarch64-linux are exposed; only x86_64-linux is exercised in the current CI. `nix flake check --all-systems --no-build` evaluates both systems; it is not a cross-hardware runtime test. The Python build checks schema closure and unit tests. The native check verifies the exact runtime export hashes, all declarations, real actor/process execution against a substituted external-tool fixture, view generation and research records. The Docker CouchDB proof remains a separate host integration check.

To update coverage, first repin the upstream source and refresh the stanza/catalog with evidence. `scripts/build-tool-actors.py --check --source /path/to/parrot-tools` proves exact baseline coverage; the generator owns `actors/tools/`. Generated declarations must not be hand-edited. `scripts/lock-runtime-source.py --check --source /path/to/star-lang` verifies the runtime export lock against the canonical Git commit.
