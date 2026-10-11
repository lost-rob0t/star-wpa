"""Independent geometry and boundary invariants; entirely synthetic inputs."""
import copy
import json
import random
import unittest
from pathlib import Path

from star_wpa.simulation_scene import adapt_open_geometry, scene_digest, synthetic_scene, validate_scene


class SceneTests(unittest.TestCase):
    def test_presets_have_expected_geometry_roles(self):
        for kind, feature_kind, count in (('brick-residential', 'building', 12),
                                         ('supermarket', 'building', 1), ('field', 'open-area', 1),
                                         ('highway', 'road', 1)):
            with self.subTest(kind=kind):
                scene = synthetic_scene(kind)
                self.assertEqual(len(scene['features']), count)
                self.assertEqual({f['kind'] for f in scene['features']}, {feature_kind})
                self.assertEqual(scene['provenance']['kind'], 'synthetic')

    def test_seed_replay_and_global_random_state_are_independent(self):
        before = random.getstate()
        first = synthetic_scene('brick-residential', seed=99)
        self.assertEqual(first, synthetic_scene('brick-residential', seed=99))
        self.assertNotEqual(first['features'], synthetic_scene('brick-residential', seed=100)['features'])
        self.assertEqual(random.getstate(), before)
        self.assertEqual(scene_digest(first), scene_digest(json.loads(json.dumps(first))))
        reverse_keys = dict(reversed(list(first.items())))
        self.assertEqual(scene_digest(first), scene_digest(reverse_keys))

    def test_generated_footprints_are_bounded_disjoint_and_have_known_area(self):
        # Check rectangles directly, independently of the production ring validator.
        for seed in range(8):
            for count in (1, 3, 19, 256):
                for width, height in ((10, 10000), (800, 75), (240, 180)):
                    scene = synthetic_scene('brick-residential', seed=seed, width_meters=width,
                                            height_meters=height, building_count=count)
                    boxes = []
                    for feature in scene['features']:
                        points = feature['polygonMeters']
                        xs, ys = zip(*points)
                        left, right, bottom, top = min(xs), max(xs), min(ys), max(ys)
                        self.assertTrue(0 <= left < right <= width)
                        self.assertTrue(0 <= bottom < top <= height)
                        self.assertEqual(len(set(xs)), 2)
                        self.assertEqual(len(set(ys)), 2)
                        for other in boxes:
                            self.assertTrue(right <= other[0] or other[1] <= left or top <= other[2] or other[3] <= bottom)
                        boxes.append((left, right, bottom, top))
                    # Every footprint uses 64% of each cell dimension; area is at
                    # most 0.64^2 of the full extent (incomplete last row allowed).
                    area = sum((r-l)*(t-b) for l,r,b,t in boxes)
                    self.assertLessEqual(area, width * height * 0.64**2 + 1e-6)

    def test_simple_concave_and_reversed_rings_are_accepted(self):
        scene = synthetic_scene('field', width_meters=10, height_meters=10)
        ring = [[0,0], [10,0], [10,10], [5,5], [0,10], [0,0]]
        for points in (ring, list(reversed(ring))):
            scene['features'][0]['polygonMeters'] = points
            self.assertEqual(validate_scene(scene), scene)

    def test_small_polygon_area_is_invariant_to_large_translation(self):
        for origin in (0, 9999):
            scene = synthetic_scene('field', width_meters=10000, height_meters=10000)
            for side, accepted in ((0.001001, True), (0.000999, False)):
                a, b = origin, origin + side
                ring = [[a,a], [b,a], [b,b], [a,b], [a,a]]
                for points in (ring, list(reversed(ring))):
                    scene['features'][0]['polygonMeters'] = points
                    with self.subTest(origin=origin, side=side, points=points):
                        if accepted:
                            self.assertEqual(validate_scene(scene), scene)
                        else:
                            with self.assertRaises(ValueError):
                                validate_scene(scene)

    def test_bad_rings_fail_including_nonzero_area_self_intersection(self):
        scene = synthetic_scene('field', width_meters=10, height_meters=10)
        rings = [
            [[0,0], [10,0], [10,10], [0,10]],  # not closed
            [[0,0], [1,0], [2,0], [0,0]],  # zero area
            [[0,0], [10,10], [0,8], [8,0], [0,0]],  # crossing, nonzero signed area
            [[0,0], [10,0], [5,0], [5,5], [0,0]],  # adjacent overlap
            [[0,0], [10,0], [10,10], [0,0], [0,10], [0,0]],  # repeated vertex
            [[0,0], [11,0], [10,10], [0,0]],  # out of extent
            [[0,0], [True,0], [10,10], [0,0]],
            [[0,0], [float('nan'),0], [10,10], [0,0]],
            [[0,0], [float('inf'),0], [10,10], [0,0]],
        ]
        for ring in rings:
            with self.subTest(ring=ring):
                scene['features'][0]['polygonMeters'] = ring
                with self.assertRaises(ValueError):
                    validate_scene(scene)

    def test_contract_rejects_unknown_fields_duplicates_and_bad_limits(self):
        original = synthetic_scene('supermarket')
        variants = [dict(original, seed=True), dict(original, seed=-1), dict(original, seed=2**63),
                    dict(original, extentMeters=[0,10]), dict(original, route=[]),
                    dict(original, features=original['features'] * 2),
                    dict(original, provenance={'kind':'private'})]
        for scene in variants:
            with self.subTest(scene=scene), self.assertRaises(ValueError):
                validate_scene(scene)
        for kwargs in ({'building_count':257}, {'building_count':True}, {'width_meters':float('inf')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                synthetic_scene('brick-residential', **kwargs)
        with self.assertRaises(ValueError):
            synthetic_scene('highway', building_count=1)

    def test_public_adapter_requires_provenance_but_never_claims_verification(self):
        # URLs are deliberately example domains, never fetched or represented as
        # evidence of an actual dataset. Geometry is our synthetic field fixture.
        source = synthetic_scene('field')
        projected = {'units':'metres', 'extentMeters':source['extentMeters'], 'features':source['features']}
        provenance = {'sourceUrl':'https://example.org/open-geometry', 'licenseUrl':'https://example.org/license',
                      'attribution':'Synthetic provider contract fixture', 'retrievedDate':'2026-01-01',
                      'sourceSha256':'a'*64, 'coordinateTransform':'Synthetic identity in local metres'}
        result = adapt_open_geometry(projected, provenance, scene_type='field', seed=7)
        self.assertEqual(result['provenance']['verification'], 'declaration-only')
        result['features'][0]['polygonMeters'][0][0] = 2
        self.assertEqual(source['features'][0]['polygonMeters'][0][0], 0)
        for change in ({'sourceUrl':'https://user:secret@example.org/data'}, {'sourceUrl':'http://example.org/data'},
                       {'licenseUrl':''}, {'sourceSha256':'x'*64}, {'retrievedDate':'2026-02-30'},
                       {'verification':'verified'}, {'sourceUrl':'https://example.org/data?token=private'},
                       {'sourceUrl':'https://example.org:bad/data'}, {'sourceUrl':'https://example.org:99999/data'},
                       {'sourceUrl':'https://@example.org/data'}, {'sourceUrl':'https://exam ple.org/data'},
                       {'sourceUrl':'https://example.org/\nprivate'}, {'sourceUrl':'https://[invalid/data'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                adapt_open_geometry(projected, dict(provenance, **change), scene_type='field', seed=7)
        with self.assertRaises(ValueError):
            adapt_open_geometry(dict(projected, units='degrees'), provenance, scene_type='field', seed=7)
        # Caller cannot upgrade a declaration by changing a flag post-adaptation.
        result = adapt_open_geometry(projected, provenance, scene_type='field', seed=7)
        result['provenance']['verification'] = 'verified'
        with self.assertRaises(ValueError):
            validate_scene(result)

    def test_validation_returns_a_detached_document(self):
        scene = synthetic_scene('supermarket')
        before = copy.deepcopy(scene)
        result = validate_scene(scene)
        result['features'][0]['material'] = 'changed'
        self.assertEqual(scene, before)

    def test_documented_scene_configs_execute(self):
        examples = Path(__file__).resolve().parents[1] / 'examples/simulation-scenes.json'
        scenes = [synthetic_scene(**item) for item in json.loads(examples.read_text())]
        self.assertEqual({s['sceneType'] for s in scenes}, {'brick-residential','supermarket','field','highway'})
        self.assertTrue(all(s['provenance']['kind'] == 'synthetic' for s in scenes))

    def test_huge_numbers_fail_with_value_error(self):
        with self.assertRaises(ValueError):
            synthetic_scene('field', width_meters=10**10000)


if __name__ == '__main__':
    unittest.main()
