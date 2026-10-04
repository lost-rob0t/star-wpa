#!/usr/bin/env python3
"""Provision an isolated disposable CouchDB and test real map indexing + solver hydration."""
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
from star_wpa.couchdb import CouchDB
from star_wpa.trilateration import trilaterate
from test_wireless import WirelessTests

# Use the managed local daemon explicitly; never redirect to a user's remote Docker context.
docker = ['docker', '--host=unix:///var/run/docker.sock']
env = dict(os.environ)
for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
    env.pop(key, None)
env['COUCHDB_USER'] = 'star-wpa-test'
env['COUCHDB_PASSWORD'] = secrets.token_urlsafe(32)
name = 'star-wpa-proof-' + secrets.token_hex(6)
container = subprocess.check_output(docker + ['run', '-d', '--name', name, '-p', '127.0.0.1::5984',
    '-e', 'COUCHDB_USER', '-e', 'COUCHDB_PASSWORD', 'couchdb:3.4.3'], env=env, text=True).strip()
try:
    port = subprocess.check_output(docker + ['port', container, '5984/tcp'], env=env, text=True).strip().rsplit(':', 1)[1]
    client = CouchDB('http://127.0.0.1:' + port + '/wireless-proof', user=env['COUCHDB_USER'], password=env['COUCHDB_PASSWORD'])
    deadline = time.monotonic() + 45
    while True:
        try:
            client.create_database()
            break
        except (HTTPError, URLError, ConnectionError, TimeoutError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
    # Single-node test DB remains per-run and is deleted with the container.
    design = json.loads((root / 'views/wireless.json').read_text())
    client.install_views(design)
    assert client.install_views(design)['unchanged']
    inputs = WirelessTests().solve_input()
    client.publish(inputs)
    again = client.publish(inputs)
    assert all(row.get('unchanged') for row in again)
    network = next(d for d in inputs if d['dtype'] == 'wireless-network')
    rows = client.observations('lab', network['id'], 100, 110)
    assert len(rows) == 4
    with_limit_failed = False
    try:
        client.observations('lab', network['id'], 100, 110, limit=3)
    except ValueError:
        with_limit_failed = True
    assert with_limit_failed
    result = client.request('GET', '_design/wireless/_view/trilateration_windows')
    assert len(result['rows']) == 4
    count = client.request('GET', '_design/wireless/_view/reading_count_by_window', query={'group': 'true'})
    assert count['rows'][0]['value'] == 4
    hydrated = client.trilateration_bundle('lab', network['id'], 100, 110)
    output = trilaterate({'dataset': 'lab', 'documents': hydrated, 'windowSeconds': 10})
    client.publish(output)
    points = client.request('GET', '_design/wireless/_view/by_geo_bucket')
    assert len(points['rows']) == 5
    print('STAR-WPA-LIVE-COUCHDB-PROOF-OK: real views, replay, hydrated 4-receiver solve, derived geo persistence')
finally:
    subprocess.run(docker + ['rm', '-f', container], env=env, stdout=subprocess.DEVNULL, check=True)
