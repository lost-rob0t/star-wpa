"""Generate every SQLite fixture from invented values; never use operator data."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

from star_wpa.wigle_sqlite import Limits, WigleImportError, main, read_backup


def make_backup(path, count=3):
    """Original synthetic rows in the observed upstream table layout."""
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE network (bssid TEXT PRIMARY KEY NOT NULL, ssid TEXT NOT NULL,
          frequency INT NOT NULL, capabilities TEXT NOT NULL, lasttime LONG NOT NULL,
          lastlat DOUBLE NOT NULL, lastlon DOUBLE NOT NULL, type TEXT NOT NULL DEFAULT 'W',
          bestlevel INTEGER NOT NULL DEFAULT 0, bestlat DOUBLE NOT NULL DEFAULT 0,
          bestlon DOUBLE NOT NULL DEFAULT 0, rcois TEXT NOT NULL DEFAULT '',
          mfgrid INTEGER NOT NULL DEFAULT 0, service TEXT NOT NULL DEFAULT '');
        CREATE TABLE location (_id INTEGER PRIMARY KEY AUTOINCREMENT, bssid TEXT NOT NULL,
          level INTEGER NOT NULL, lat DOUBLE NOT NULL, lon DOUBLE NOT NULL,
          altitude DOUBLE NOT NULL, accuracy FLOAT NOT NULL, time LONG NOT NULL,
          external INTEGER NOT NULL DEFAULT 0, mfgrid INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE route (_id INTEGER PRIMARY KEY, time LONG, lat DOUBLE, lon DOUBLE);
        INSERT INTO network (bssid,ssid,frequency,capabilities,lasttime,lastlat,lastlon,type)
          VALUES ('02:00:00:00:00:01','SYNTHETIC network',2412,'[WPA2]',1700000000999,42,43,'W');
        INSERT INTO route VALUES (1,1700000000000,80,90);
        """)
        db.executemany("INSERT INTO location (bssid,level,lat,lon,altitude,accuracy,time,external) VALUES (?,?,?,?,?,?,?,?)",
                       (("02:00:00:00:00:01", -40 - i % 30, 0, 0, 12.5, 3.25, 1700000000000 + i, i % 2) for i in range(count)))


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="star-wpa-test-wigle-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.sqlite"
        make_backup(self.path)

    def read(self, **kwargs):
        with read_backup(self.path, **kwargs) as rows:
            return list(rows)

    def sql(self, text, params=()):
        with sqlite3.connect(self.path) as db:
            db.execute(text, params)

    def test_mapping_preserves_observation_fields_and_summary_distinction(self):
        rows = self.read(limits=Limits(batch_size=1))
        self.assertEqual([r.observation_id for r in rows], [1, 2, 3])
        self.assertEqual([r.observed_at_ms for r in rows], [1700000000000, 1700000000001, 1700000000002])
        self.assertEqual(len({r.address for r in rows}), 1)
        self.assertEqual([r.signal_dbm for r in rows], [-40, -41, -42])
        self.assertEqual([r.source_signal_level for r in rows], [-40, -41, -42])
        self.assertEqual([r.external for r in rows], [False, True, False])
        self.assertEqual((rows[0].latitude, rows[0].longitude), (0, 0))
        self.assertEqual((rows[0].altitude_m, rows[0].accuracy_m), (12.5, 3.25))
        self.assertEqual((rows[0].network_radio_code, rows[0].network_frequency), ("W", 2412))
        self.assertEqual(rows[0].network_name, "SYNTHETIC network")
        self.assertNotIn("distance", rows[0].__dataclass_fields__)

    def test_source_content_metadata_and_directory_unchanged(self):
        before = self.path.stat()
        digest = hashlib.sha256(self.path.read_bytes()).digest()
        self.read()
        after = self.path.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns, before.st_ctime_ns),
                         (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        self.assertEqual(digest, hashlib.sha256(self.path.read_bytes()).digest())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_temporary_copy_private_and_removed_on_early_exit(self):
        import star_wpa.wigle_sqlite as module
        original = module._schema
        snapshots = []

        def inspect(db):
            target = Path(db.execute("PRAGMA database_list").fetchone()[2])
            snapshots.append(target)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM location")
            return original(db)

        with patch.object(module, "_schema", side_effect=inspect):
            with read_backup(self.path) as rows:
                self.assertEqual(next(rows).observation_id, 1)
        self.assertFalse(snapshots[0].parent.exists())
        with self.assertRaises(StopIteration):
            next(rows)

    def test_sidecars_are_rejected_including_empty_and_dangling_symlink(self):
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.path) + suffix)
            sidecar.touch()
            with self.assertRaisesRegex(WigleImportError, "sidecars"):
                self.read()
            sidecar.unlink()
        sidecar.symlink_to(self.path.parent / "missing")
        with self.assertRaisesRegex(WigleImportError, "sidecars"):
            self.read()

    def test_source_symlink_directory_fifo_and_missing_are_rejected(self):
        link = self.path.parent / "link"
        link.symlink_to(self.path)
        fifo = self.path.parent / "fifo"
        os.mkfifo(fifo)
        for path in (link, fifo, self.path.parent, self.path.parent / "missing"):
            with self.subTest(kind=path.name), self.assertRaises(WigleImportError):
                with read_backup(path) as rows:
                    list(rows)

    def test_live_wal_rejected_and_consistent_backup_accepted(self):
        with sqlite3.connect(self.path) as live:
            self.assertEqual(live.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            live.execute("UPDATE location SET level=-55")
            live.commit()
            with self.assertRaisesRegex(WigleImportError, "sidecars"):
                self.read()
            destination = self.path.parent / "consistent.sqlite"
            with sqlite3.connect(destination) as copied:
                live.backup(copied)
            with read_backup(destination) as rows:
                self.assertEqual([r.signal_dbm for r in rows], [-55, -55, -55])
        live.close()
        self.assertFalse(Path(str(self.path) + "-wal").exists())
        self.assertEqual([r.signal_dbm for r in self.read()], [-55, -55, -55])

    def test_source_change_during_copy_is_rejected(self):
        import star_wpa.wigle_sqlite as module
        original = module._no_sidecars
        calls = 0

        def alter(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                previous = path.stat()
                os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000))
            return original(path)

        with patch.object(module, "_no_sidecars", side_effect=alter), self.assertRaisesRegex(WigleImportError, "changed"):
            self.read()

    def test_byte_limit_and_non_sqlite_or_gzip(self):
        with self.assertRaises(WigleImportError):
            self.read(limits=Limits(max_bytes=self.path.stat().st_size - 1))
        for content in (b"not sqlite" * 100, b"\x1f\x8b" + b"x" * 200):
            self.path.write_bytes(content)
            with self.assertRaises(WigleImportError):
                self.read()

    def test_exact_row_bound_and_late_error(self):
        self.assertEqual(len(self.read(limits=Limits(max_rows=3))), 3)
        with read_backup(self.path, limits=Limits(max_rows=2, batch_size=1)) as rows:
            self.assertEqual(next(rows).observation_id, 1)
            self.assertEqual(next(rows).observation_id, 2)
            with self.assertRaisesRegex(WigleImportError, "row limit"):
                next(rows)

    def test_empty_backup_is_valid(self):
        self.sql("DELETE FROM location")
        self.assertEqual(self.read(), [])

    def test_sqlite_work_and_deadline_budgets(self):
        self.path.unlink()
        make_backup(self.path, 5000)
        with self.assertRaisesRegex(WigleImportError, "budget"):
            self.read(limits=Limits(max_vm_steps=1000))
        with patch("star_wpa.wigle_sqlite.time.monotonic", side_effect=itertools.count()), self.assertRaisesRegex(WigleImportError, "time budget"):
            self.read(limits=Limits(max_seconds=0.5))

    def test_missing_summary_is_not_silently_dropped(self):
        self.sql("DELETE FROM network")
        with self.assertRaisesRegex(WigleImportError, "no matching"):
            self.read()

    def test_all_official_radio_codes_and_non_wifi_frequency(self):
        for radio in ("W", "G", "C", "L", "D", "N", "B", "E", "F"):
            self.sql("UPDATE network SET type=?", (radio,))
            self.assertEqual(self.read()[0].network_radio_code, radio)
        self.sql("UPDATE network SET type='L', frequency=12345")
        self.assertEqual(self.read()[0].network_frequency, 12345)

    def test_bluetooth_missing_rssi_preserves_row_without_inventing_dbm(self):
        # Classic discovery defaults to Short.MIN_VALUE; the network summary
        # can subsequently be marked BLE. Both persisted summary codes occur.
        self.sql("UPDATE location SET level=-32768 WHERE _id=2")
        for radio in ("B", "E"):
            self.sql("UPDATE network SET type=?", (radio,))
            with self.subTest(radio=radio):
                rows = self.read(limits=Limits(batch_size=1))
                self.assertEqual([r.observation_id for r in rows], [1, 2, 3])
                self.assertEqual([r.signal_dbm for r in rows], [-40, None, -42])
                self.assertEqual([r.source_signal_level for r in rows], [-40, -32768, -42])
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(main([str(self.path)]), 0)
                result = json.loads(stdout.getvalue())
                self.assertEqual(result["observations"], 3)
                self.assertEqual(result["unknownSignalObservations"], 1)
                self.assertEqual(result["observationsByNetworkRadioCode"], {radio: 3})
                self.assertEqual(stderr.getvalue(), "")
                self.assertNotIn("-32768", stdout.getvalue())

    def test_missing_rssi_is_only_the_known_bluetooth_sentinel(self):
        for radio, level in (("W", -32768), ("G", -32768), ("F", -32768),
                             ("B", -32767), ("E", -32769), ("B", 32767),
                             ("E", -201), ("E", 101)):
            self.sql("UPDATE network SET type=?", (radio,))
            self.sql("UPDATE location SET level=? WHERE _id=2", (level,))
            with self.subTest(radio=radio, level=level), self.assertRaises(WigleImportError):
                self.read(limits=Limits(batch_size=1))

    def test_invalid_scalar_values_rejected_without_echo(self):
        for table, key, bad in (("location", "level", -201), ("location", "level", "PRIVATE"),
                                ("location", "lat", 91), ("location", "lon", float("inf")),
                                ("location", "time", -1), ("location", "external", 2),
                                ("location", "accuracy", -1), ("network", "frequency", -1),
                                ("network", "type", "PRIVATE"), ("network", "ssid", "PRIVATE\x00value"),
                                ("network", "capabilities", "x" * 4097)):
            with self.subTest(table=table, key=key):
                self.path.unlink()
                make_backup(self.path)
                self.sql(f"UPDATE {table} SET {key}=?", (bad,))
                with self.assertRaises(WigleImportError) as caught:
                    self.read()
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_views_triggers_generated_columns_and_wrong_layout_rejected(self):
        statements = ["CREATE VIEW secret AS SELECT * FROM location",
                      "CREATE TRIGGER secret AFTER INSERT ON location BEGIN DELETE FROM location; END",
                      "ALTER TABLE location ADD COLUMN computed INT GENERATED ALWAYS AS (level + 1)",
                      "ALTER TABLE location RENAME COLUMN time TO renamed"]
        for sql in statements:
            self.path.unlink()
            make_backup(self.path)
            self.sql(sql)
            with self.subTest(sql=sql), self.assertRaises(WigleImportError):
                self.read()

    def test_wrong_primary_key_and_virtual_table_rejected(self):
        self.sql("ALTER TABLE location RENAME TO old_location")
        self.sql("CREATE TABLE location AS SELECT * FROM old_location")
        with self.assertRaises(WigleImportError):
            self.read()
        self.path.unlink()
        make_backup(self.path)
        self.sql("CREATE VIRTUAL TABLE extra USING fts5(value)")
        with self.assertRaises(WigleImportError):
            self.read()

    def test_truncated_and_corrupt_snapshot_rejected(self):
        raw = self.path.read_bytes()
        for corrupt in (raw[:5000], raw[:100] + b"\xff" * 100 + raw[200:]):
            self.path.write_bytes(corrupt)
            with self.assertRaises(WigleImportError):
                self.read()

    def test_cli_prints_counts_only_after_complete_success(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(main([str(self.path)]), 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["observations"], 3)
        self.assertEqual(result["externalObservations"], 1)
        self.assertEqual(result["unknownSignalObservations"], 0)
        self.assertEqual(result["observationsByNetworkRadioCode"], {"W": 3})
        for token in ("02:00", "170000", "SYNTHETIC", str(self.path), "latitude"):
            self.assertNotIn(token, stdout.getvalue() + stderr.getvalue())
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(main([str(self.path), "--max-rows", "2"]), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn(str(self.path), stderr.getvalue())

    def test_limits_validation(self):
        for changes in ({"max_rows": True}, {"max_rows": 0}, {"max_bytes": 99}, {"max_seconds": float("nan")},
                        {"max_seconds": 301}, {"max_seconds": 10**400}, {"max_vm_steps": 999}, {"batch_size": 1001}):
            with self.subTest(changes=changes), self.assertRaises(WigleImportError):
                Limits(**changes)


if __name__ == "__main__":
    unittest.main()
