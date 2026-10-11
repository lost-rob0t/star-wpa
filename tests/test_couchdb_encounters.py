"""Canonical 0.10.1 encounter bounds across CouchDB revision-aware replay.

Uses a deterministic revision-checked memory transport: this is not a live
CouchDB or Kismet integration test. Runtime validation uses the vendored,
immutable Star Language 0.10.1 schema through the maintained contract API.
"""
from copy import deepcopy
import unittest
from urllib.error import HTTPError

from star_wpa.contracts import document, stable_id, validate_bundle
from star_wpa.couchdb import CouchDB


class RevisionCheckedCouchDB(CouchDB):
    """Exercise production CouchDB.publish without an external datastore."""

    def __init__(self):
        self.rows = {}
        self.writes = 0
        self.conflict_once = False

    def get(self, identity):
        row = self.rows.get(identity)
        return deepcopy(row) if row is not None else None

    def request(self, method, path='', body=None, query=None):
        if method != 'PUT' or not isinstance(body, dict):
            raise AssertionError('unexpected CouchDB operation')
        identity = body['_id']
        current = self.rows.get(identity)
        if current is None:
            if '_rev' in body:
                raise AssertionError('new document included a revision')
            revision = 1
        else:
            if body.get('_rev') != current['_rev']:
                raise AssertionError('missing or stale revision CAS')
            if self.conflict_once:
                self.conflict_once = False
                # A revision races between GET and PUT. The maintained
                # implementation must re-read before retrying.
                self.rows[identity] = dict(current, _rev=str(int(current['_rev']) + 1))
                raise HTTPError('http://127.0.0.1/mock', 409, 'Conflict', {}, None)
            revision = int(current['_rev']) + 1
        self.writes += 1
        self.rows[identity] = deepcopy(dict(body, _rev=str(revision)))
        return {'id': identity, 'rev': str(revision)}


class NetworkDeviceEncounterTests(unittest.TestCase):
    ID = stable_id('bluetooth-device', 'lab', '02:11:22:33:44:55')

    @classmethod
    def packet(cls, first, last, *, dataset='lab'):
        return document('network-device', dataset, cls.ID,
                        deviceClass='unknown', firstSeen=first, lastSeen=last)

    def test_newer_then_older_then_replay_preserves_full_history(self):
        couch = RevisionCheckedCouchDB()
        for row in (self.packet(120, 125), self.packet(90, 121),
                    self.packet(128, 130), self.packet(90, 121),
                    self.packet(120, 125)):
            validate_bundle([row])
            couch.publish([row])
        stored = couch.get(self.ID)
        self.assertEqual((stored['firstSeen'], stored['lastSeen']), (90, 130))
        self.assertEqual(stored['deviceClass'], 'unknown')
        self.assertEqual(stored['schemaVersion'], '0.10.1')
        self.assertEqual(stored['dataset'], 'lab')

    def test_no_revision_written_for_equivalent_replay(self):
        couch = RevisionCheckedCouchDB()
        row = self.packet(90, 130)
        couch.publish([row])
        self.assertEqual(couch.publish([deepcopy(row)]),
                         [{'id': self.ID, 'unchanged': True}])
        self.assertEqual(couch.writes, 1)
        self.assertEqual(couch.get(self.ID)['_rev'], '1')

    def test_conflict_retry_preserves_window_and_uses_fresh_revision(self):
        couch = RevisionCheckedCouchDB()
        couch.publish([self.packet(120, 125)])
        couch.conflict_once = True
        couch.publish([self.packet(90, 121)])
        self.assertEqual((couch.get(self.ID)['firstSeen'],
                          couch.get(self.ID)['lastSeen']), (90, 125))
        self.assertEqual(couch.get(self.ID)['_rev'], '3')

    def test_cross_dataset_collision_fails_without_mutation(self):
        couch = RevisionCheckedCouchDB()
        couch.publish([self.packet(120, 125)])
        existing = couch.get(self.ID)
        with self.assertRaisesRegex(ValueError, 'identity conflict'):
            couch.publish([self.packet(90, 130, dataset='other')])
        self.assertEqual(couch.get(self.ID), existing)


if __name__ == '__main__':
    unittest.main()
