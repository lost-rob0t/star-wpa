"""Analytic fits and privacy invariants using only original synthetic rows."""
import copy
import json
import unittest
from fractions import Fraction
from pathlib import Path
import random

from star_wpa.simulation_calibration import FORMAT, fit_synthetic_calibration


def fixture(signals=(-40, -60, -80), distances=(1, 10, 100), frequency=2412):
    return {'format':FORMAT, 'provenance':'synthetic',
            'observations':[{'id':i+1, 'address':'02:00:00:00:00:01', 'radio':'WIFI',
                             'frequency':frequency, 'level':signal, 'name':'SYNTHETIC-ONLY',
                             'latitude':0, 'longitude':0, 'time':i}
                            for i, signal in enumerate(signals)],
            'knownDistancesMeters':[{'id':i+1, 'distanceMeters':d} for i,d in enumerate(distances)]}


class CalibrationTests(unittest.TestCase):
    def test_known_log_distance_equation_recovers_exact_coefficients(self):
        result = fit_synthetic_calibration(fixture())['fits'][0]
        self.assertEqual(result['sampleCount'], 3)
        self.assertEqual(result['referenceSignalDbm'], -40)
        self.assertEqual(result['pathLossExponent'], 2)
        self.assertEqual(result['residualRmseDb'], 0)

    def test_known_orthogonal_residuals_have_unit_rmse(self):
        # Residuals [1,-1,-1,1] have zero sum and zero dot product with
        # log-distances [0,1,2,3], preserving the hand-derived A=-40, n=2.
        result = fit_synthetic_calibration(fixture((-39,-61,-81,-99), (1,10,100,1000)))['fits'][0]
        self.assertEqual(result['referenceSignalDbm'], -40)
        self.assertEqual(result['pathLossExponent'], 2)
        self.assertEqual(result['residualRmseDb'], 1)

    def test_fits_match_an_exact_rational_normal_equation_oracle(self):
        # An independent uncentered closed form with exact integer arithmetic,
        # unlike the production centered floating-point covariance calculation.
        rng = random.Random(20403)
        for count in range(4, 36):
            xs = [0, 2, 5] + [rng.randrange(6) for _ in range(count - 3)]
            ys = [-30 - 15 * x + rng.randrange(-3, 4) for x in xs]
            sx, sy, sxx, sxy = sum(xs), sum(ys), sum(x*x for x in xs), sum(x*y for x,y in zip(xs,ys))
            denominator = count * sxx - sx * sx
            intercept = Fraction(sy * sxx - sx * sxy, denominator)
            slope = Fraction(count * sxy - sx * sy, denominator)
            result = fit_synthetic_calibration(fixture(ys, [10**x for x in xs]))['fits'][0]
            with self.subTest(count=count):
                self.assertAlmostEqual(result['referenceSignalDbm'], float(intercept), places=11)
                self.assertAlmostEqual(result['pathLossExponent'], float(-slope / 10), places=12)

    def test_frequencies_are_fit_separately_not_pooled_by_band(self):
        request = fixture()
        second = fixture((-45,-75,-105), frequency=2437)
        for row in second['observations'] + second['knownDistancesMeters']:
            row['id'] += 3
        request['observations'] += second['observations']
        request['knownDistancesMeters'] += second['knownDistancesMeters']
        results = fit_synthetic_calibration(request)['fits']
        self.assertEqual([r['pathLossExponent'] for r in results], [2,3])
        self.assertEqual([r['referenceSignalDbm'] for r in results], [-40,-45])

    def test_deterministic_order_translation_and_distance_scaling_invariants(self):
        request = fixture()
        original = fit_synthetic_calibration(request)
        request['observations'].reverse()
        request['knownDistancesMeters'].reverse()
        self.assertEqual(original, fit_synthetic_calibration(request))
        for row in request['observations']:
            row['level'] += 7
        shifted = fit_synthetic_calibration(request)['fits'][0]
        self.assertEqual(shifted['referenceSignalDbm'], -33)
        self.assertEqual(shifted['pathLossExponent'], 2)
        for row in request['knownDistancesMeters']:
            row['distanceMeters'] *= 10
        rescaled = fit_synthetic_calibration(request)['fits'][0]
        self.assertEqual(rescaled['referenceSignalDbm'], -13)
        self.assertEqual(rescaled['pathLossExponent'], 2)

    def test_gps_is_ignored_and_private_fields_do_not_leave_aggregate(self):
        request = fixture()
        before = copy.deepcopy(request)
        result = fit_synthetic_calibration(request)
        self.assertEqual(request, before)
        for row in request['observations']:
            row.update(latitude=88, longitude=-170, name='SYNTHETIC-PRIVATE-MARKER')
        self.assertEqual(fit_synthetic_calibration(request), result)
        rendered = json.dumps(result)
        for private in ('address', 'latitude', 'longitude', 'time', 'name', 'SYNTHETIC', '02:00:00', 'distanceMeters'):
            self.assertNotIn(private, rendered)

    def test_non_synthetic_and_unknown_contract_fields_are_rejected(self):
        for change in ({'provenance':'private-wigle'}, {'format':'unknown'}, {'inputPath':'fixture.sqlite'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                fit_synthetic_calibration(dict(fixture(), **change))

    def test_invalid_sample_pairing_and_geometry_never_produce_a_fit(self):
        for mode in ('duplicate-row', 'duplicate-truth', 'unmatched-id', 'missing-truth', 'other-transmitter',
                     'one-frequency-row', 'bad-radio', 'unknown-field', 'bool-id', 'nonfinite', 'zero-distance'):
            request = fixture()
            if mode == 'duplicate-row': request['observations'][1]['id'] = 1
            if mode == 'duplicate-truth': request['knownDistancesMeters'][1]['id'] = 1
            if mode == 'unmatched-id': request['knownDistancesMeters'][1]['id'] = 99
            if mode == 'missing-truth': request['knownDistancesMeters'].pop()
            if mode == 'other-transmitter': request['observations'][1]['address'] = '02:00:00:00:00:02'
            if mode == 'one-frequency-row': request['observations'][1]['frequency'] = 5200
            if mode == 'bad-radio': request['observations'][1]['radio'] = 'BLE'
            if mode == 'unknown-field': request['observations'][1]['capture'] = 'synthetic'
            if mode == 'bool-id': request['observations'][1]['id'] = True
            if mode == 'nonfinite': request['observations'][1]['level'] = float('nan')
            if mode == 'zero-distance': request['knownDistancesMeters'][1]['distanceMeters'] = 0
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                fit_synthetic_calibration(request)

    def test_nonidentifiable_or_nonattenuating_models_are_rejected(self):
        for request in (fixture(distances=(10,10,10)), fixture(distances=(1,1.0001,1.0002)),
                        fixture(signals=(-40,-40,-40)), fixture(signals=(-80,-60,-40))):
            with self.subTest(request=request), self.assertRaises(ValueError):
                fit_synthetic_calibration(request)

    def test_documented_synthetic_fixture_recovers_known_model(self):
        example = Path(__file__).resolve().parents[1] / 'examples/simulation-calibration-synthetic.json'
        result = fit_synthetic_calibration(json.loads(example.read_text()))['fits'][0]
        self.assertEqual((result['referenceSignalDbm'], result['pathLossExponent'], result['residualRmseDb']), (-40,2,0))

    def test_extreme_number_fails_with_value_error(self):
        request = fixture()
        request['knownDistancesMeters'][0]['distanceMeters'] = 10**10000
        with self.assertRaises(ValueError):
            fit_synthetic_calibration(request)


if __name__ == '__main__':
    unittest.main()
