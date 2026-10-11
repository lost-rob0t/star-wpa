"""Planar baseline proof: bounded cost, unchanged exact max-receiver separation."""
import math
import random
import unittest
from unittest.mock import patch

from star_wpa.contracts import NS
from star_wpa.trilateration import EARTH_RADIUS, farthest_baseline, fit


class ReceiverBaselineTests(unittest.TestCase):
    def test_diameter_matches_quadratic_reference(self):
        rng = random.Random(14107)
        fixtures = [
            [(0.0, 0.0)],
            [(1.0, 2.0)] * 10,
            [(0.0, 0.0), (3.0, 4.0)],
            [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)],
            [(-10.0, -10.0), (10.0, 10.0), (-10.0, 10.0), (10.0, -10.0)],
        ]
        for size in (3, 10, 40, 150):
            fixtures.extend([
                [(rng.uniform(-5000, 5000), rng.uniform(-5000, 5000))
                 for _ in range(size)]
                for _ in range(5)
            ])
        for points in fixtures:
            with self.subTest(size=len(points)):
                expected = max(math.hypot(a[0] - b[0], a[1] - b[1])
                               for a in points for b in points)
                self.assertAlmostEqual(farthest_baseline(points), expected, delta=1e-8)

    def test_large_receiver_group_avoids_quadratic_baseline(self):
        count = 1800
        rows = []
        for index in range(count):
            angle = 2 * math.pi * (index + 0.25) / count
            x, y = 200.0 * math.cos(angle), 200.0 * math.sin(angle)
            rows.append({"extensions": {NS: {
                "latitude": math.degrees(y / EARTH_RADIUS),
                "longitude": math.degrees(x / EARTH_RADIUS),
                "distanceMeters": math.hypot(x, y),
                "rangeAccuracyMeters": 1.0,
            }}})
        original_hypot = math.hypot
        invocations = 0

        def count_hypot(*args):
            nonlocal invocations
            invocations += 1
            return original_hypot(*args)

        with patch("star_wpa.trilateration.math.hypot", side_effect=count_hypot):
            latitude, longitude, uncertainty, residual = fit(rows, None, 5000)
        self.assertAlmostEqual(latitude, 0, delta=0.00001)
        self.assertAlmostEqual(longitude, 0, delta=0.00001)
        self.assertGreaterEqual(uncertainty, 1)
        self.assertLess(residual, 0.01)
        self.assertLess(invocations, count * 20,
                        "baseline evaluation must not enumerate receiver pairs")


if __name__ == "__main__":
    unittest.main()
