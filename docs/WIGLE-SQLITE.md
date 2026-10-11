# Local WiGLE SQLite backup reader

This slice reads completed SQLite backups offline. It does not collect packets,
write StarIntel records, fit radio models, or use the held Prolog simulator source.
No operator file was used to implement or test it. All fixtures are generated from
invented data into temporary directories; no database is checked in.

The incoming `.csv.gz` mentioned during development is a different format. This
reader rejects gzip and CSV. Existing `privacy.parse_wigle` parses bounded,
uncompressed WiGLE CSV for the privacy preview, while `ingest.ingest_wardrive`
accepts JSON observations. Neither is a gzip decoder or this SQLite reader.

## Use

Requires Python 3.11+, POSIX and SQLite 3.37+. The module is included in the normal
wheel; it adds no dependencies or actor command. Set `TMPDIR` to a private local
directory outside any repository, shared folder or automatically published area.
Keep the input backup there as well. Do not point this at an active app database.

```sh
python -m star_wpa.wigle_sqlite /private/path/completed-backup.sqlite \
  --max-rows 1000000 --max-bytes 536870912 --max-seconds 30
```

The CLI prints only observation counts (total, external, and by network radio
code), after a complete successful read. Failure prints a fixed diagnostic to
stderr with no input paths, row values or SQL error text. These local counts are
still private derivatives, not an approved public export.

```python
from star_wpa.wigle_sqlite import Limits, read_backup

with read_backup("/private/path/completed-backup.sqlite",
                 limits=Limits(max_rows=100_000, batch_size=256)) as readings:
    for reading in readings:
        # Consume in a private, transactional sink; never log the raw record.
        pass
```

The iterator must be used inside the context. A bad later row or exceeded budget
raises an error after earlier rows may have been yielded. Consumers must discard
or roll back partial work. There is no automatic calibration or ingestion bridge.

## Schema and field meaning

Primary sources were inspected on 2026-10-11 at official WiGLE Android commit
`c7b87114f9c4d8a269673fedacc675c5b3cf94be`:

- [DatabaseHelper](https://github.com/wiglenet/wigle-wifi-wardriving/blob/c7b87114f9c4d8a269673fedacc675c5b3cf94be/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/db/DatabaseHelper.java)
  defines `network`, `location`, and optional `route`, writes location times from
  Android `Location.getTime()`, and checkpoints before copying a database backup.
- [NetworkType](https://github.com/wiglenet/wigle-wifi-wardriving/blob/c7b87114f9c4d8a269673fedacc675c5b3cf94be/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/model/NetworkType.java)
  maps W/G/C/L/D/N/B/E/F to Wi-Fi/GSM/CDMA/LTE/WCDMA/NR/Bluetooth/BLE/NFC.
- [ObservationUploader](https://github.com/wiglenet/wigle-wifi-wardriving/blob/c7b87114f9c4d8a269673fedacc675c5b3cf94be/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/background/ObservationUploader.java)
  writes the separate version 1.6 CSV export with 14 columns and UTC timestamps.

The supported profile requires ordinary rowid `network` and `location` tables,
the declared column types below, and single-column primary keys `network.bssid`
and `location._id`. Extra ordinary columns/tables/indexes are ignored; views,
triggers, generated columns in consumed tables, and virtual tables are refused.
This is structural compatibility, not a claim that every historical/future
WiGLE release is supported. No database version number is guessed.

| Source | Required declared types | Reader meaning |
| --- | --- | --- |
| `location._id`, `level`, `external` | INTEGER | Source observation ID, RSSI dBm, external flag |
| `location.bssid` | TEXT | Observed address; not a physical-device identity |
| `location.lat`, `lon`, `altitude` | DOUBLE | Receiver location/fix values, not transmitter coordinates |
| `location.accuracy` | FLOAT | Source receiver-location accuracy, not RSSI/range uncertainty |
| `location.time` | LONG | Source location timestamp in milliseconds, preserved exactly |
| `network.bssid`, `ssid`, `capabilities`, `type` | TEXT | Join key and **summary metadata**, exposed as `network_*` fields |
| `network.frequency` | INT | Summary frequency; units/interpretation depend on radio type |

Rows are returned in `_id` order, which need not be chronological. Repeated
readings remain separate; `external=1` rows are included and flagged. A missing
network join is an error, never silently dropped. Network summary fields may
have changed since a historical reading. Wi-Fi/Bluetooth/BLE addresses are
validated as MAC syntax; other radio addresses remain bounded opaque strings.
Zero coordinates and zero timestamps are preserved, not treated as missing.
No `route` records, network best/last coordinates, receiver identity or computed
distance are returned. Reused location-fix times need not be exact scan times.

Observation counts are not packet counts or emission rates. Address counts do
not guarantee distinct physical devices. Radio calibration needs separately
established transmitter/receiver positions or distances, receiver/source metadata,
and an explicit sampling model. This reader supplies none of those assumptions.

## Snapshot and resource checks

The source is opened read-only, with no final-component symlinks or special
files. WAL/SHM/journal sidecars, even empty ones, are refused before and after
copying. A private mode-0600 snapshot is copied in bounded chunks inside a
mode-0700 temporary directory. Size, inode/device and change timestamps are
checked around copying. Source file contents are never written; normal filesystem
access-time updates are possible.

Only the completed private copy is opened by SQLite, using
[`mode=ro&immutable=1`](https://www.sqlite.org/uri.html), `query_only`, disabled
trusted schema, restricted SQLite limits and an authorizer for the final query.
The entire copy must pass [integrity_check](https://www.sqlite.org/pragma.html#pragma_integrity_check)
before rows are exposed. The full snapshot includes private source tables for
that integrity check, although only observation/network fields are returned.
The temporary directory is removed on normal exit and exceptions, including
early iterator exit. Abrupt process termination may leave private temporary
files. Unlinking is not secure erasure; use an appropriate private volume.

These checks establish readable structure and a stable copied file. They cannot
prove that a previously lost WAL had no missing committed observations, that an
export was complete, or that a location fix is accurate. Obtain a completed app
backup from a quiescent source or a consistent SQLite backup. Do not strip
sidecars from an active database to make it pass. SQLite documents
[WAL persistence](https://www.sqlite.org/wal.html) and its
[consistent backup API](https://www.sqlite.org/backup.html).

Defaults: 512 MiB source, 1,000,000 rows, 30 elapsed seconds including consumption,
50 million approximate SQLite VM steps, and 256 rows per batch. Configurable
ceilings: 4 GiB, 10 million rows, 300 seconds, 1 billion VM steps, 1,000-row batches.
The time limit is cooperative, checked between copy chunks/rows and every 1,000
VM steps, not an OS-level interrupt for a stalled filesystem operation. SQLite
cache is configured to 2 MiB; the row/text limits and streaming query avoid
collecting all observations in Python. Resource limits are not a hardened parser
sandbox for arbitrary hostile database exploits.

## Reproducible validation

```sh
python3 -m unittest discover -s tests -p test_wigle_sqlite.py -v
python3 scripts/benchmark-wigle-sqlite.py --rows 100000 --repetitions 5
```

The benchmark measures copy, schema/integrity checks and complete streaming;
fixture creation and one warm-up are excluded. Its separate traced-memory pass
reports Python allocations only, excluding SQLite native memory and filesystem
cache. It does not measure Prolog coverage, radio capture or real backup quality.

Measured locally with Python 3.12.14, SQLite 3.53.1 and x86_64: a 5,787,648-byte,
100,000-row synthetic backup took 399.950 ms median CPU and 399.964 ms median wall
time over five runs. The separate memory pass peaked at 2,109,736 traced Python
bytes. This is an example measurement, not a CI threshold or portable guarantee.
