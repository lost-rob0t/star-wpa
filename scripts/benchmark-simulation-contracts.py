#!/usr/bin/env python3
"""Measure only scene contracts and synthetic calibration, not the Prolog engine."""
import argparse
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from star_wpa.simulation_scene import synthetic_scene
from star_wpa.simulation_calibration import FORMAT, fit_synthetic_calibration


def measure(call, repetitions):
    call()  # Warm-up is excluded.
    cpu, wall = [], []
    for _ in range(repetitions):
        start_cpu, start_wall = time.process_time(), time.perf_counter()
        call()
        cpu.append((time.process_time() - start_cpu) * 1000)
        wall.append((time.perf_counter() - start_wall) * 1000)
    return {'repetitions': repetitions, 'medianCpuMs': round(statistics.median(cpu), 3),
            'medianWallMs': round(statistics.median(wall), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 1000:
        parser.error('--repetitions must be 1..1000')
    request = {'format': FORMAT, 'provenance': 'synthetic', 'observations': [], 'knownDistancesMeters': []}
    for index in range(10000):
        distance = 10 ** ((index % 1000) / 250)
        request['observations'].append({'id': index + 1, 'address': '02:00:00:00:00:01', 'radio': 'WIFI',
                                        'frequency': 2412, 'level': -40 - 20 * math.log10(distance)})
        request['knownDistancesMeters'].append({'id': index + 1, 'distanceMeters': distance})
    report = {'python': platform.python_version(), 'architecture': platform.machine(),
              'scope': 'contract generation/validation and synthetic OLS only; not coverage engine',
              'scene256Buildings': measure(lambda: synthetic_scene('brick-residential', seed=104, building_count=256), args.repetitions),
              'calibration10000Rows': measure(lambda: fit_synthetic_calibration(request), args.repetitions)}
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
