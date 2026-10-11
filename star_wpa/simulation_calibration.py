"""Synthetic-only prototype for the future private WiGLE calibration boundary.

No SQLite, KML, capture, network, or file access. Receiver GPS is never used to
infer transmitter distance. Fits use independently supplied synthetic truth.
"""
import math

from .ingest import mac

FORMAT = 'star-wpa-synthetic-calibration-v1'
MAX_SAMPLES = 10000


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high or not math.isfinite(value):
        raise ValueError('invalid calibration number')
    return float(value)


def _identifier(value):
    if type(value) is not int or value < 1:
        raise ValueError('expected positive synthetic observation identity')
    return value


def fit_synthetic_calibration(request):
    """Fit RSSI = A - 10 n log10(distance metres), independently per frequency.

    This prototype accepts only declared synthetic inputs from one transmitter.
    The source-row subset follows the existing wardrive export adapter, not an
    assumed WiGLE SQLite layout. Returns aggregates without source identifiers.
    """
    fields = {'format', 'provenance', 'observations', 'knownDistancesMeters'}
    if not isinstance(request, dict) or set(request) != fields or request['format'] != FORMAT or request['provenance'] != 'synthetic':
        raise ValueError('only the synthetic calibration contract is supported')
    observations, distances = request['observations'], request['knownDistancesMeters']
    if not isinstance(observations, list) or not 3 <= len(observations) <= MAX_SAMPLES or not isinstance(distances, list) or len(distances) != len(observations):
        raise ValueError('expected bounded observations and matching distance truth')
    truth = {}
    for row in distances:
        if not isinstance(row, dict) or set(row) != {'id', 'distanceMeters'}:
            raise ValueError('invalid synthetic distance truth')
        identity = _identifier(row['id'])
        if identity in truth:
            raise ValueError('duplicate synthetic distance identity')
        truth[identity] = _number(row['distanceMeters'], 1, 100000)
    required = {'id', 'address', 'level', 'frequency', 'radio'}
    optional = {'time', 'latitude', 'longitude', 'name', 'security'}
    seen, transmitters, groups = set(), set(), {}
    for row in observations:
        if not isinstance(row, dict) or not required <= row.keys() or row.keys() - required - optional:
            raise ValueError('invalid synthetic observation fields')
        identity = _identifier(row['id'])
        if identity in seen or identity not in truth:
            raise ValueError('duplicate observation or missing distance truth')
        seen.add(identity)
        transmitters.add(mac(row['address']))
        if row['radio'] not in ('W', 'WIFI'):
            raise ValueError('calibration requires WiFi observations')
        frequency = _number(row['frequency'], 100, 100000)
        signal = _number(row['level'], -200, 100)
        groups.setdefault(frequency, []).append((math.log10(truth[identity]), signal))
    if len(transmitters) != 1 or seen != truth.keys():
        raise ValueError('calibration requires one transmitter and exact distance matching')
    fitted = []
    for frequency, points in sorted(groups.items()):
        # Canonical order makes fitting invariant to provider row order.
        points.sort()
        count = len(points)
        if count < 3 or len({x for x, _ in points}) < 3:
            raise ValueError('each frequency needs three distinct known distances')
        mean_x, mean_y = math.fsum(x for x, _ in points) / count, math.fsum(y for _, y in points) / count
        sxx = math.fsum((x - mean_x)**2 for x, _ in points)
        if sxx / count < 1e-6:
            raise ValueError('distance range is too narrow for a stable fit')
        slope = math.fsum((x - mean_x) * (y - mean_y) for x, y in points) / sxx
        exponent = -slope / 10
        # The inclusive upper bound can be exceeded by floating-point OLS
        # roundoff (amplified near the accepted distance-spread floor). Snap only
        # a 1e-11 absolute overage, then use that same slope
        # for the reported intercept and residuals. Larger overages still fail.
        if 10 < exponent <= 10 + 1e-11:
            exponent, slope = 10.0, -100.0
        if not 0 < exponent <= 10:
            raise ValueError('fit does not describe decreasing signal in the supported range')
        intercept = mean_y - slope * mean_x
        rmse = math.sqrt(math.fsum((y - intercept - slope * x)**2 for x, y in points) / count)
        fitted.append({'frequencyMhz': frequency, 'sampleCount': count,
                       'referenceDistanceMeters': 1.0, 'referenceSignalDbm': intercept,
                       'pathLossExponent': exponent, 'residualRmseDb': rmse})
    return {'format': 'star-wpa-synthetic-calibration-fit-v1', 'provenance': 'synthetic',
            'method': 'ordinary-least-squares-log10-distance', 'fits': fitted}
