# Local privacy export

Use this tool to review and reduce your own WiGLE CSV or WarStar JSON observations before sharing a **new sanitized analysis CSV**. It never changes the input or sends it to a service. It does not call the StarIntel ingestion/custody adapters.

```sh
python3 -m star_wpa.privacy /absolute/path/run.csv --format wigle \
  --output /absolute/path/new-sanitized-analysis.csv
# WarStar envelope:
python3 -m star_wpa.privacy /absolute/path/run.json --format warstar \
  --output /absolute/path/new-sanitized-analysis.csv
```

Open the printed `http://127.0.0.1:PORT/` in your local browser. The default selects an available loopback port; `--port 8765` selects a fixed port. There is no remote bind option. Python 3.11+ on POSIX is required for descriptor-relative no-follow file access. The modules are included in the existing star-wpa Python package; no additional runtime dependency is needed.

1. Press **Update preview** to see source coordinates on an offline coordinate plot. No basemap, tiles, geocoding or external assets are loaded.
2. Add exclusion boxes by entering south/west/north/east coordinates, or drag on the source plot to fill the fields and press **Add exclusion**. Choose a buffer for each box (default 100 meters). Increase buffers around sensitive locations and approaches. West greater than east crosses the antimeridian; `-180` to `180` covers all longitudes. Boundaries are included.
3. Choose coordinate precision (default two decimal places, about 1.1 km of latitude). Press **Update preview** after changes. Compare source and sanitized locations and review the source/excluded/retained/collapsed counts. World and fit controls change the plot extent.
4. Press **Create new sanitized CSV** to write exactly the current preview to the destination chosen at launch. All-excluded input produces a header-only CSV. Existing destinations—including the input itself, hard links and dangling symlinks—are refused. To export again, restart with a fresh destination.
5. Close the page and stop the process with Ctrl-C when finished. Source and exclusion state remain in process/browser memory only; there is no browser storage or auto-save.

## What leaves the tool

The fixed output allowlist is `latitude,longitude,radio,signal_dbm`. Coordinates are rounded; identical output rows are collapsed and rows are sorted by retained values so input sequence and duplicate multiplicity cannot determine output order. The preview's counts and exclusion geometry are not included in the saved file.

MAC/BSSID, SSID/device names, source IDs, dataset/receiver identity, timestamps, frequency/channel, security strings, altitude/accuracy, manufacturer/RCOI fields, file names/hashes, metadata preamble, raw blobs and session/track metadata are never copied. Original text is never used as an output CSV cell. The preview shows coordinates and reduction counts, not source names or identifiers.

**This does not provide anonymity.** Remaining coordinates can still reveal visits and spatial routes. Coarse locations and signals can still correlate with other information; sorting does not prevent spatial inference. Rounding is not a guaranteed uncertainty radius, and longitude grid spacing decreases toward the poles. Wider exclusions, coarser precision or withholding the export may be appropriate. The tool never associates wireless observations with people.

**The output is not WiGLE re-upload compatible:** required addresses/timestamps and the WiGLE header have deliberately been removed. Do not feed sanitized output through a raw-retaining custody importer as a substitute for this workflow.

## Supported inputs and strictness

Input is explicitly selected with `--format`, limited to 16 MiB and 100,000 observations, and decoded as strict UTF-8 (optional BOM). Malformed input rejects the entire run; no partial salvage or silent invalid-row skipping occurs. CSV supports quoted commas, quotes and embedded newlines.

Supported CSV headers are these exact, ordered variants, with no duplicate or additional columns:

- WiGLE v1.6: `MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,RCOIs,MfgrId,Type`.
- Historical 11-column: the above without `Frequency,RCOIs,MfgrId`.
- Quasar synthetic 9-column subset: the 11-column header without `AltitudeMeters,AccuracyMeters`.

Headers may appear without a preamble. When present, `WigleWifi-1.6` requires the 14-column header and `WigleWifi-1.4` accepts the 11/9-column variants. Preamble fields are recognized, duplicate keys rejected and the entire preamble discarded. Non-Earth planetary values are refused. The parser supports WiFi, Bluetooth/BLE and the documented cell radio types, validates addresses for their type and validates timestamps/numeric fields even when those fields are discarded. No local-time reconstruction occurs.

WarStar uses the existing envelope in `star_wpa/ingest.py` and `tests/fixtures/wardrive.json`: `dataset`, `observations`, and `device_id` and/or `receiverId`. Observation fields are `id,address,time,latitude,longitude,level`, plus optional `radio,name,security,frequency`. Radio aliases match the existing importer. Unknown keys and duplicate JSON keys are rejected, so undocumented raw/track metadata cannot slip into a copy. Numeric JSON fields must be numbers; ID/time/level/frequency must be integers.

Coordinates must be finite and within latitude ±90 and longitude ±180. Zero, including `(0,0)`, is valid and is not treated as an absent fix. ±180 are equivalent. At the poles longitude is canonicalized to zero. Callers should explicitly exclude placeholder locations if their source uses `(0,0)` that way.

Buffers use a mean-radius sphere (6,371,008.8 m) and **conservative rectangular expansion**, not a precise GIS polygon offset. Extra points near corners may be removed. If an expansion reaches a pole it covers all longitudes. Points are checked both before and after coordinate rounding, preventing rounding back into an exclusion. This is not a survey-grade geodesic boundary calculation.

## Local security and limitations

Every source/destination path component is opened relative to a directory descriptor with `O_NOFOLLOW`. Parent traversal (`..`), symlink parents/targets, nonregular sources and oversized sources are refused. Output uses `O_CREAT|O_EXCL|O_NOFOLLOW` with mode `0600`, flush and fsync. An I/O failure can leave an incomplete new output file; the tool reports failure, preserves the original and refuses to overwrite that partial file on retry. Choose a fresh destination after checking disk state.

HTTP is bound to `127.0.0.1`, requires an exact Host and same Origin for POSTs, rejects cross-site fetches, and requires an in-memory unpredictable session token. There is no CORS, request-body logging, URL-based data, outbound fetch, browser persistence or path selection API. Responses are no-store and use a restrictive Content Security Policy. This protects the browser boundary, not a hostile local account, browser extension, compromised OS or process-memory inspection. Stop the server after use. Preview/export is single-session and does not claim protection against filesystem mutations by a hostile same-user process.

## Evidence and checks

Format evidence inspected 2026-10-11:

- [Official WiGLE v1.6 specification](https://api.wigle.net/csvFormat-1_6.html).
- [WarStar ObservationUploader.java at d75eca3](https://github.com/lost-rob0t/wigle-wifi-wardriving-starintel-/blob/d75eca3e07ffbd4a7b598d5367bc6fd2d72ddafa/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/background/ObservationUploader.java), header and RFC4180 metadata preamble; its CSV reader compatibility comments document the older form.
- Existing star-wpa `ingest_wardrive` envelope and synthetic fixture. No Quasar importer code is changed.

Run the synthetic parser, geometry, filesystem, CLI and loopback HTTP tests:

```sh
python3 -m unittest discover -s tests -p 'test_privacy.py' -v
```

For a real Chromium UI check, install the optional Playwright test dependency/browser in a development environment and run `python3 scripts/check-privacy-preview.py`. Pass `--browser /usr/bin/chromium` to use an existing Chromium installation. This check uses only bundled synthetic data, verifies no non-loopback requests, exercises exclusion/preview/export, checks original bytes and writes an optional screenshot only when `--screenshot` is explicitly supplied. It is not a live-user-data test or deployment.
