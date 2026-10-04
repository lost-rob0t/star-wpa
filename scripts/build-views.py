#!/usr/bin/env python3
"""Build rebuildable CouchDB projections from reviewed JavaScript source."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build():
    helpers = (ROOT / 'views/helpers.js').read_text()
    views = {}
    for path in sorted((ROOT / 'views/maps').glob('*.js')):
        source = path.read_text().strip()
        brace = source.index('{') + 1
        views[path.stem] = {'map': source[:brace] + '\n' + helpers + source[brace:]}
    views['reading_count_by_window'] = {'map': views['trilateration_windows']['map'], 'reduce': '_count'}
    return {'_id': '_design/wireless', 'language': 'javascript', 'views': views}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'views/wireless.json'
    value = json.dumps(build(), indent=2, sort_keys=True) + '\n'
    if args.check:
        if not target.exists() or target.read_text() != value:
            raise SystemExit('generated wireless views are stale; run scripts/build-views.py')
    else:
        target.write_text(value)


if __name__ == '__main__':
    main()
