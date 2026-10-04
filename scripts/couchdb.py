#!/usr/bin/env python3
"""Install wireless views or explicitly persist a validated actor output batch."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from star_wpa.couchdb import CouchDB

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('operation', choices=['install-views', 'publish', 'trilateration-input'])
parser.add_argument('--file', type=Path)
parser.add_argument('--dataset')
parser.add_argument('--network-id')
parser.add_argument('--start', type=int)
parser.add_argument('--end', type=int)
args = parser.parse_args()
client = CouchDB.from_environment()
if args.operation == 'install-views':
    design = json.loads((Path(__file__).resolve().parent.parent / 'views/wireless.json').read_text())
    client.install_views(design)
    print('wireless views installed')
elif args.operation == 'publish':
    if args.file is None:
        parser.error('publish requires --file')
    results = client.publish(json.loads(args.file.read_text()))
    print(json.dumps({'documents': len(results)}))
else:
    if None in (args.dataset, args.network_id, args.start, args.end):
        parser.error('trilateration-input requires --dataset, --network-id, --start and --end')
    docs = client.trilateration_bundle(args.dataset, args.network_id, args.start, args.end)
    print(json.dumps({'dataset': args.dataset, 'documents': docs}, allow_nan=False))
