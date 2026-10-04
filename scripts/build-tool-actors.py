#!/usr/bin/env python3
"""Verify pinned Parrot package coverage and generate actual StarLang declarations."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_source(catalog, source=None):
    authority = catalog['source']
    stanza = (ROOT / 'catalog/parrot-tools-wireless.control').read_bytes()
    if hashlib.sha256(stanza).hexdigest() != authority['stanzaSha256']:
        raise ValueError('pinned upstream stanza drift')
    if source:
        raw = (subprocess.check_output(['git', '-C', str(source), 'show', authority['commit'] + ':' + authority['path']])
               if (source / '.git').exists() else (source / authority['path']).read_bytes())
        if hashlib.sha256(raw).hexdigest() != authority['sha256']:
            raise ValueError('upstream source hash mismatch')
        upstream = next(b for b in raw.decode().split('\n\n') if b.startswith('Package: parrot-tools-wireless\n')) + '\n'
        if upstream.encode() != stanza:
            raise ValueError('upstream wireless stanza mismatch')
    expected = {}
    for line in stanza.decode().splitlines():
        match = re.fullmatch(r' ([a-z0-9-]+)(?: \[([^]]+)\])?,', line)
        if match:
            name, restrictions = match.groups()
            expected[name] = (restrictions or '').split()
    actual = {row['package']: row['architectureRestrictions'] for row in catalog['packages'] if row['source'] == 'parrot-tools-wireless'}
    if expected != actual:
        raise ValueError('Parrot wireless package coverage or architecture restrictions drift')
    packages = [row['package'] for row in catalog['packages']]
    if len(set(packages)) != len(packages) or any(not re.fullmatch('[a-z0-9][a-z0-9-]*', name) for name in packages):
        raise ValueError('invalid or duplicate package identity')


def render(row):
    name = row['package']
    return f'''(actor wpa-tool-{name}
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-{name}"
   :accepts ()
   :produces ()
   :handler wpa-tool-{name}-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-{name}") (package "{name}") (family "{row['family']}")
              (commandBoundary "operator-local-json-file"))))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'star_wpa/tool_catalog.json').read_text())
    check_source(catalog, args.source)
    directory = ROOT / 'actors/tools'
    expected = {row['package'] + '.star': render(row) for row in catalog['packages']}
    if args.check:
        if {p.name for p in directory.glob('*.star')} != set(expected):
            raise SystemExit('tool actor set is stale')
        for name, content in expected.items():
            if (directory / name).read_text() != content:
                raise SystemExit('generated tool actor is stale: ' + name)
    else:
        directory.mkdir(parents=True, exist_ok=True)
        if {p.name for p in directory.glob('*.star')} - set(expected):
            raise SystemExit('unexpected tool actors require explicit migration')
        for name, content in expected.items():
            (directory / name).write_text(content)
    print(f'validated 31 Parrot baseline packages; {len(expected)} total tool actors')


if __name__ == '__main__':
    main()
