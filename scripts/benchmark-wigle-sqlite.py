#!/usr/bin/env python3
"""Benchmark complete reads of a temporary, entirely synthetic SQLite backup."""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from star_wpa.wigle_sqlite import Limits, read_backup
from test_wigle_sqlite import make_backup


def consume(path, count):
    with read_backup(path, limits=Limits(max_rows=count)) as rows:
        actual = sum(1 for _ in rows)
    if actual != count:
        raise AssertionError("Synthetic benchmark row count mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.rows <= 1_000_000 or not 1 <= args.repetitions <= 100:
        parser.error("rows must be 1..1000000; repetitions must be 1..100")
    with tempfile.TemporaryDirectory(prefix="star-wpa-benchmark-wigle-") as directory:
        path = Path(directory) / "synthetic.sqlite"
        make_backup(path, args.rows)
        consume(path, args.rows)  # Exclude fixture creation and one warm-up.
        cpu, wall = [], []
        for _ in range(args.repetitions):
            start_cpu, start_wall = time.process_time(), time.perf_counter()
            consume(path, args.rows)
            cpu.append((time.process_time() - start_cpu) * 1000)
            wall.append((time.perf_counter() - start_wall) * 1000)
        tracemalloc.start()
        consume(path, args.rows)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        print(json.dumps({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                          "architecture": platform.machine(), "rows": args.rows, "repetitions": args.repetitions,
                          "scope": "copy, integrity/schema validation and complete streamed read; synthetic only",
                          "sourceBytes": path.stat().st_size, "pythonTracedPeakBytes": peak,
                          "medianCpuMs": round(statistics.median(cpu), 3),
                          "medianWallMs": round(statistics.median(wall), 3)}, indent=2))


if __name__ == "__main__":
    main()
