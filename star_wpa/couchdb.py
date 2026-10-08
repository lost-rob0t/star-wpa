"""Direct CouchDB persistence port. This does not call legacy StarIntel HTTP routes."""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request
from .http import open_http
from .contracts import validate, validate_bundle
from .adapters import MAX_BYTES


def canonical(stored):
    return {k: v for k, v in stored.items() if k not in ('_id', '_rev')}


class CouchDB:
    def __init__(self, url, *, user=None, password=None, timeout=30):
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('CouchDB database URL must not embed credentials, query or fragment')
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.auth = None
        if user is not None:
            self.auth = 'Basic ' + base64.b64encode((user + ':' + (password or '')).encode()).decode()

    @classmethod
    def from_environment(cls):
        return cls(os.environ['STAR_WPA_COUCHDB_URL'], user=os.environ.get('STAR_WPA_COUCHDB_USER'),
                   password=os.environ.get('STAR_WPA_COUCHDB_PASSWORD'))

    def request(self, method, path='', body=None, query=None):
        url = self.url + ('/' + path if path else '')
        if query:
            url += '?' + urlencode(query)
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.auth:
            headers['Authorization'] = self.auth
        data = json.dumps(body, allow_nan=False).encode() if body is not None else None
        with open_http(Request(url, data=data, headers=headers, method=method), timeout=self.timeout) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('CouchDB response exceeds byte limit; use smaller query windows')
        return json.loads(raw)

    def create_database(self):
        try:
            self.request('PUT')
        except HTTPError as error:
            if error.code != 412:
                raise

    def get(self, identity):
        try:
            return self.request('GET', quote(identity, safe=''))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise

    def install_views(self, design):
        identity = design['_id']
        for _ in range(3):
            current = self.get(identity)
            value = dict(design)
            if current:
                if {k: v for k, v in current.items() if k != '_rev'} == value:
                    return {'id': identity, 'unchanged': True}
                value['_rev'] = current['_rev']
            try:
                return self.request('PUT', quote(identity, safe=''), value)
            except HTTPError as error:
                if error.code != 409:
                    raise
        raise RuntimeError('CouchDB design update conflicts exceeded retry limit')

    def publish(self, docs):
        validate_bundle(docs)  # All validation happens before the first write.
        results = []
        for doc in docs:
            identity = doc['id']
            for _ in range(3):
                current = self.get(identity)
                value = doc
                if current:
                    before = canonical(current)
                    if before == doc:
                        results.append({'id': identity, 'unchanged': True})
                        break
                    # Immutable event/geo evidence cannot silently change under a replay ID.
                    if doc['dtype'] not in ('wireless-network', 'wireless-station', 'network-device', 'relation'):
                        raise ValueError('conflicting immutable wireless evidence')
                    if before.get('dataset') != doc['dataset'] or before.get('dtype') != doc['dtype']:
                        raise ValueError('canonical identity conflict')
                    if doc['dtype'] in ('wireless-network', 'wireless-station'):
                        value = dict(before if before.get('lastSeen', 0) > doc.get('lastSeen', 0) else doc)
                        first = min(before.get('firstSeen', 2**63), doc.get('firstSeen', 2**63))
                        if first != 2**63:
                            value['firstSeen'] = first
                    if doc['dtype'] == 'relation' and before.get('validAt', 0) > doc.get('validAt', 0):
                        value = before
                    validate(value)
                    if value == before:
                        results.append({'id': identity, 'unchanged': True})
                        break
                stored = dict(value, _id=identity)
                if current:
                    stored['_rev'] = current['_rev']
                try:
                    results.append(self.request('PUT', quote(identity, safe=''), stored))
                    break
                except HTTPError as error:
                    if error.code != 409:
                        raise
            else:
                raise RuntimeError('CouchDB document update conflicts exceeded retry limit')
        return results

    def observations(self, dataset, network_id, start, end, limit=1000):
        if not isinstance(limit, int) or not 1 <= limit <= 10000 or start > end:
            raise ValueError('invalid observation query bounds')
        page = self.request('GET', '_design/wireless/_view/by_network_time', query={
            'startkey': json.dumps([dataset, network_id, start]),
            'endkey': json.dumps([dataset, network_id, end, {}]),
            'include_docs': 'true', 'limit': str(limit + 1)})
        if len(page['rows']) > limit:
            raise ValueError('observation query exceeds bound; use smaller windows')
        return [canonical(row['doc']) for row in page['rows']]

    def trilateration_bundle(self, dataset, network_id, start, end):
        # Hydrate event relation/geometry closure through the maintained observation graph.
        events = self.observations(dataset, network_id, start, end)
        network = self.get(network_id)
        if network is None:
            raise ValueError('network not found')
        docs = {network_id: canonical(network)}
        for event in events:
            docs[event['id']] = event
            page = self.request('GET', '_design/wireless/_view/relations_by_source', query={
                'startkey': json.dumps([dataset, event['id']]), 'endkey': json.dumps([dataset, event['id'], {}]),
                'include_docs': 'true', 'limit': '101'})
            if len(page['rows']) > 100:
                raise ValueError('observation relation closure exceeds bound')
            for row in page['rows']:
                edge = canonical(row['doc'])
                docs[edge['id']] = edge
                destination = self.get(edge['destination']['id'])
                if destination is None:
                    raise ValueError('missing relation destination')
                dest = canonical(destination)
                docs[dest['id']] = dest
                if dest['dtype'] == 'location':
                    geometry = self.get(dest['geometry']['id'])
                    if geometry is None:
                        raise ValueError('missing location geometry')
                    docs[geometry['id']] = canonical(geometry)
        return validate_bundle(list(docs.values()))
