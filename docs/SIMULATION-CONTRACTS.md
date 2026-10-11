# Scene and synthetic calibration contracts

These Python interfaces prepare local inputs for a future bridge to the
producer-owned Prolog coverage engine. They do not run that engine, add an
`sa-*` command, simulate packets, implement RF reception, or consume private
WiGLE databases. No engine source is duplicated here.

## Original synthetic scenes

`star_wpa.simulation_scene.synthetic_scene(scene_type, *, seed=1,
width_meters=240, height_meters=180, building_count=None)` produces the
`star-wpa-scene-v1` operator-local input contract. This is not a new portable
StarIntel document type. The four original illustrative presets are:

| Type | Default geometry | Material label |
|---|---|---|
| `brick-residential` | Twelve separated rectangular footprints | `brick` |
| `supermarket` | One rectangular footprint | `unspecified` |
| `field` | An open-area rectangle covering the extent | `unspecified` |
| `highway` | A road strip occupying the middle 20% of the extent's height | `unspecified` |

Dimensions, building counts, and seed are configurable. Preset proportions and
gaps are invented scenario choices, not measured setbacks, typical buildings,
lane widths, or national averages. A material label has no automatic attenuation
value. The original Prolog model remains responsible for reception assumptions.

The geometry contract contains `format`, `sceneType`, `seed`, `extentMeters`,
`features`, and `provenance`. Features contain a unique `id`, `kind` (`building`,
`road`, or `open-area`), a `material` label, and `polygonMeters`. Polygon rings
must close, have otherwise distinct vertices, be simple, have area of at least
0.000001 square metres,
and lie within the scene extent. Clockwise, counterclockwise, and concave rings
are accepted. Holes, multipolygons, altitude, trajectories, and geodetic
coordinates are outside this first contract. Provider adapters may split
disjoint components into distinct features; they must not silently fill holes.

Limits: 256 features, 64 distinct vertices per ring, extents from 1 to 10,000
metres, and seeds from 0 to 2^63-1. The synthetic factory requires dimensions
of at least 10 metres. Public/projected features may overlap intentionally;
the synthetic building factory ensures its own buildings do not overlap.

Factory placement uses SHA-256 keyed by format version, seed, and building
index, so generation is deterministic and independent of global RNG state.
Changing a field/highway seed does not change their fixed geometry.
`validate_scene` returns a detached copy; unknown fields, booleans in numeric
fields, nonfinite values, duplicate feature IDs, and invalid rings fail.
`scene_digest` hashes the complete validated JSON contract with sorted keys;
it is a local content identity, not a geometry-equivalence hash or a safe
public identifier for private geometry.

```python
import json
from pathlib import Path
from star_wpa.simulation_scene import synthetic_scene, validate_scene

presets = json.loads(Path('examples/simulation-scenes.json').read_text())
scenes = [synthetic_scene(**preset) for preset in presets]
assert all(validate_scene(scene) == scene for scene in scenes)
```

## Generic open-geography adapter boundary

`adapt_open_geometry(projected, provenance, *, scene_type, seed)` accepts an
upstream provider's already projected local-metre geometry:

- `projected`: `units: "metres"`, `extentMeters`, and `features` as above.
- `provenance`: `sourceUrl`, `licenseUrl`, `attribution`, `retrievedDate`
  (`YYYY-MM-DD`), `sourceSha256` (lowercase hex), and `coordinateTransform`.
- `coordinateTransform` describes the source CRS, chosen local projection,
  origin, transform/tool version, and accuracy limitations. This first boundary
  requires a nonempty declaration, not a machine-verifiable projection record.
- Source and license URLs must use HTTPS without credentials, whitespace,
  escaped authority text, backslashes, query strings, or fragments. The syntax
  checks do not verify a working URL or a source. Nothing is fetched. Preserve a stable dataset landing URL;
  authenticated downloads and request details stay outside this contract.

The result always records `kind: "public-open"` and
`verification: "declaration-only"`. Required metadata and a supplied hash do
not verify the source, attribution, license, or projection. The adapter rejects
an attempt to assert `verification: "verified"`. Before any real public scene
is used or published, separately check the actual source bytes against the
declared hash, source/license terms, attribution, and projection accuracy. That
provider verification and engine-admission step is still pending.

There is no city-specific logic, Columbus dataset, network fetch, GeoJSON/KML
parser, or claimed public-geography integration in this slice. Tests use only
synthetic metre geometry and example-domain provenance placeholders.

## Synthetic calibration prototype

`star_wpa.simulation_calibration.fit_synthetic_calibration(request)` accepts
only `star-wpa-synthetic-calibration-v1` with `provenance: "synthetic"`. This
label is a caller declaration, not a detector for private data. Current tests
and examples are original synthetic inputs; no user database has been supplied.

The request has `observations` and `knownDistancesMeters`. Observation fields
`id`, `address`, `radio`, `level`, and `frequency` follow the existing
[wardrive export boundary](../star_wpa/ingest.py). `radio` is `W` or `WIFI`;
`level` is dBm and `frequency` is MHz. Optional `time`, `latitude`, `longitude`,
`name`, and `security` are ignored and never returned. This is not a guessed
SQLite table or column mapping.

Every observation ID must match exactly one supplied synthetic distance from
the transmitter in metres. IDs must be unique, all rows must describe one
transmitter, and each exact frequency must have at least three distinct known
distances. Receiver GPS coordinates are never used as transmitter locations
or ground-truth distances. Distances must be 1–100,000 metres; the adapter
does not extrapolate a near-field model below its one-metre reference.

For each frequency, ordinary least squares fits:

```text
RSSI(d) = A - 10 n log10(d / 1 metre)
```

The output contains the one-metre reference signal `A`, path-loss exponent
`n`, sample count, frequency, and `sqrt(sum(residual^2) / sample_count)` in dB.
It rejects insufficient distance spread and exponents outside `(0, 10]`, except
that a floating-point overage of at most 1e-12 at the upper bound is snapped to
10. The intercept and residuals then use that same snapped slope. Larger
overages are rejected; this numerical tolerance is not measurement uncertainty.
Residual RMS describes this fit; it is not a confidence interval, a Monte Carlo
uncertainty estimate, or evidence of real radio calibration. Rows may be
correlated, and repeated rows are not independent measurements. No claims are
made about walls, fading, censoring, antenna patterns, or device power.

Fits contain no observation IDs, MACs, SSIDs, timestamps, coordinates, or raw
rows. A future fit from private input would still be private and must not be
published or Git-tracked automatically merely because identifiers are absent.

```python
import json
from pathlib import Path
from star_wpa.simulation_calibration import fit_synthetic_calibration

request = json.loads(Path('examples/simulation-calibration-synthetic.json').read_text())
fit = fit_synthetic_calibration(request)['fits'][0]
assert fit['referenceSignalDbm'] == -40
assert fit['pathLossExponent'] == 2
assert fit['residualRmseDb'] == 0
```

## Remaining integration work

The producer owns Prolog source, packet generation, elapsed-time schedules,
paired seeds, device/packet coverage metrics, and Monte Carlo uncertainty.
Those are not reimplemented here. The bridge to that engine is not yet implemented.

The executor's future bridge must translate this geometry and explicit RF
assumptions to the reviewed Prolog interface, enforce public-source verification,
and preserve the engine's seed/schedule/metric semantics. A real WiGLE importer
requires private schema inspection, a verified transmitter-distance source,
appropriate measurement grouping and outlier/censoring treatment, and private
output handling. KML/KMZ, routes, captures, user databases, and their revealing
derivatives must remain outside Git. PCAP and virtual-driver layers are later
work, as are actual public map geometry and calibrated RF models.

Run the independent contract and mathematical checks with:

```sh
python3 -m unittest discover -s tests -p 'test_simulation_*.py' -v
```

## Measured contract performance

The reproducible benchmark generates only synthetic inputs in memory:

```sh
python3 scripts/benchmark-simulation-contracts.py
```

On this executor (Python 3.12.14, x86_64), an initial 20-repetition run after
one excluded warm-up measured 4.059 ms median CPU for generating and validating
256 buildings and 23.041 ms median CPU for a 10,000-row synthetic calibration
fit. Corresponding median elapsed times were 4.059 and 23.068 ms. These are
observed local timings, not CI thresholds or portable performance promises.
They do not measure the Prolog coverage engine or establish radio accuracy.
