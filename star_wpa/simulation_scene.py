"""Provider-neutral, local-metre scene inputs; no coverage or radio simulation."""
import copy
import hashlib
import json
import math
from datetime import date
from urllib.parse import urlsplit

FORMAT = 'star-wpa-scene-v1'
SCENE_TYPES = ('brick-residential', 'supermarket', 'field', 'highway')
MAX_FEATURES = 256
MAX_VERTICES = 64


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('invalid object fields')


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high or not math.isfinite(value):
        raise ValueError('number outside finite scene bounds')
    return float(value)


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside scene bounds')
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError('invalid scene text')


def _https(value):
    _text(value)
    try:
        parsed = urlsplit(value)
        valid = (not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
                 and parsed.scheme == 'https' and parsed.hostname
                 and parsed.username is None and parsed.password is None
                 and not parsed.query and not parsed.fragment
                 and (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('source URL must be valid HTTPS without credentials, whitespace, query, or fragment')


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    # Inclusive: non-adjacent edges touching also invalidate a simple ring.
    def on(p, q, r):
        return _cross(p, q, r) == 0 and all(min(p[i], q[i]) <= r[i] <= max(p[i], q[i]) for i in (0, 1))
    ac, ad, ca, cb = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    return (ac * ad < 0 and ca * cb < 0) or on(a, b, c) or on(a, b, d) or on(c, d, a) or on(c, d, b)


def _validate_ring(ring, width, height):
    if not isinstance(ring, list) or not 4 <= len(ring) <= MAX_VERTICES + 1:
        raise ValueError('expected a bounded closed polygon ring')
    for point in ring:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError('expected two local-metre coordinates')
        _number(point[0], 0, width)
        _number(point[1], 0, height)
    if ring[0] != ring[-1] or len({tuple(p) for p in ring[:-1]}) != len(ring) - 1:
        raise ValueError('polygon must close with otherwise distinct vertices')
    edges = list(zip(ring, ring[1:]))
    # Translate before summing: global-coordinate shoelace terms can cancel at
    # large offsets even when the small polygon's area is above the threshold.
    area = math.fsum(_cross(ring[0], a, b) for a, b in edges) / 2
    if abs(area) < 0.000001:
        raise ValueError('degenerate polygon')
    for i, (a, b) in enumerate(edges):
        previous = ring[i - 1] if i else ring[-2]
        if _cross(previous, a, b) == 0 and sum((previous[k] - a[k]) * (b[k] - a[k]) for k in (0, 1)) > 0:
            raise ValueError('polygon edge doubles back')
        for j in range(i + 1, len(edges)):
            if j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if _intersects(a, b, *edges[j]):
                raise ValueError('polygon is not simple')


def validate_scene(scene):
    """Return a detached validated scene. Provenance declarations are not verified."""
    _keys(scene, ('format', 'sceneType', 'seed', 'extentMeters', 'features', 'provenance'))
    if scene['format'] != FORMAT or scene['sceneType'] not in SCENE_TYPES:
        raise ValueError('unsupported scene format or type')
    _integer(scene['seed'], 0, 2**63 - 1)
    size = scene['extentMeters']
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError('extent must give width and height')
    width, height = (_number(v, 1, 10000) for v in size)
    features = scene['features']
    if not isinstance(features, list) or len(features) > MAX_FEATURES:
        raise ValueError('feature count exceeds scene bounds')
    identities = set()
    for feature in features:
        _keys(feature, ('id', 'kind', 'material', 'polygonMeters'))
        _text(feature['id'])
        _text(feature['material'])
        if feature['id'] in identities or feature['kind'] not in ('building', 'road', 'open-area'):
            raise ValueError('duplicate feature identity or unsupported feature kind')
        identities.add(feature['id'])
        _validate_ring(feature['polygonMeters'], width, height)
    provenance = scene['provenance']
    if not isinstance(provenance, dict):
        raise ValueError('expected scene provenance')
    if provenance.get('kind') == 'synthetic':
        _keys(provenance, ('kind', 'generator'))
        _text(provenance['generator'])
    elif provenance.get('kind') == 'public-open':
        _keys(provenance, ('kind', 'sourceUrl', 'licenseUrl', 'attribution', 'retrievedDate',
                          'sourceSha256', 'coordinateTransform', 'verification'))
        for key in ('sourceUrl', 'licenseUrl'):
            _https(provenance[key])
        for key in ('attribution', 'coordinateTransform'):
            _text(provenance[key])
        try:
            valid_date = isinstance(provenance['retrievedDate'], str) and date.fromisoformat(provenance['retrievedDate']).isoformat() == provenance['retrievedDate']
        except ValueError:
            valid_date = False
        if not valid_date:
            raise ValueError('expected ISO retrieval date')
        digest = provenance['sourceSha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('expected source SHA-256')
        if provenance['verification'] != 'declaration-only':
            raise ValueError('this adapter cannot assert provenance verification')
    else:
        raise ValueError('unsupported geometry provenance')
    return copy.deepcopy(scene)


def adapt_open_geometry(projected, provenance, *, scene_type, seed):
    """Accept a provider adapter's projected metre geometry and source declaration.

    The provider owns projection and license review. No URLs are fetched, and no
    claim is made that the referenced dataset or its license was verified.
    """
    _keys(projected, ('units', 'extentMeters', 'features'))
    if projected['units'] != 'metres':
        raise ValueError('provider must project geometry into local metres')
    _keys(provenance, ('sourceUrl', 'licenseUrl', 'attribution', 'retrievedDate',
                       'sourceSha256', 'coordinateTransform'))
    return validate_scene({'format': FORMAT, 'sceneType': scene_type, 'seed': seed,
                           'extentMeters': projected['extentMeters'], 'features': projected['features'],
                           'provenance': dict(provenance, kind='public-open', verification='declaration-only')})


def scene_digest(scene):
    """Stable identity for a validated local contract; never a public export."""
    raw = json.dumps(validate_scene(scene), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def synthetic_scene(scene_type, *, seed=1, width_meters=240, height_meters=180, building_count=None):
    """Generate original illustrative geometry with platform-stable keyed jitter."""
    if scene_type not in SCENE_TYPES:
        raise ValueError('unsupported scene type')
    _integer(seed, 0, 2**63 - 1)
    width, height = _number(width_meters, 10, 10000), _number(height_meters, 10, 10000)
    default = {'brick-residential': 12, 'supermarket': 1, 'field': 0, 'highway': 0}[scene_type]
    count = default if building_count is None else _integer(building_count, 0, MAX_FEATURES)
    if scene_type in ('field', 'highway') and count:
        raise ValueError('open scene presets do not place buildings')
    features = []

    def rectangle(identity, kind, material, left, bottom, right, top):
        features.append({'id': identity, 'kind': kind, 'material': material,
                         'polygonMeters': [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]})

    if count:
        columns = min(count, max(1, math.ceil(math.sqrt(count * width / height))))
        rows = math.ceil(count / columns)
        cw, ch = width / columns, height / rows
        for index in range(count):
            raw = hashlib.sha256(f'scene-v1:{seed}:{index}'.encode()).digest()
            dx = (int.from_bytes(raw[:8], 'big') / 2**64 - 0.5) * 0.1 * cw
            dy = (int.from_bytes(raw[8:16], 'big') / 2**64 - 0.5) * 0.1 * ch
            left = (index % columns + 0.18) * cw + dx
            bottom = (index // columns + 0.18) * ch + dy
            rectangle(f'building-{index + 1}', 'building', 'brick' if scene_type == 'brick-residential' else 'unspecified',
                      left, bottom, left + 0.64 * cw, bottom + 0.64 * ch)
    elif scene_type == 'field':
        rectangle('open-1', 'open-area', 'unspecified', 0, 0, width, height)
    elif scene_type == 'highway':
        rectangle('road-1', 'road', 'unspecified', 0, height * 0.4, width, height * 0.6)
    return validate_scene({'format': FORMAT, 'sceneType': scene_type, 'seed': seed,
                           'extentMeters': [width, height], 'features': features,
                           'provenance': {'kind': 'synthetic', 'generator': 'star-wpa-scene-v1'}})
