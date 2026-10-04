#!/usr/bin/env python3
"""Generate immutable runtime source hashes from the consumer's exact pinned Git commit."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
lock = json.loads((root / 'schema/starintel-schema.lock.json').read_text())
roots = ['starlang-compiler', 'starlang-runtime', 'star-process-port', 'star-mailbox', 'star-actor-protocol',
         'star-canonical-json', 'star-logic-ir', 'star-logic-protocol']
paths = subprocess.check_output(['git', '-C', str(args.source), 'ls-tree', '-r', '--name-only',
                                lock['canonical_commit'], '--', *roots], text=True).splitlines()
files = {p: hashlib.sha256(subprocess.check_output(['git', '-C', str(args.source), 'show', lock['canonical_commit'] + ':' + p])).hexdigest()
         for p in paths if p.endswith(('.lisp', '.asd'))}
value = json.dumps({'canonical_commit': lock['canonical_commit'], 'sourceDirectories': roots, 'files': files}, indent=2) + '\n'
target = root / 'schema/starlang-runtime.lock.json'
if args.check:
    if target.read_text() != value:
        raise SystemExit('runtime source lock is stale')
else:
    target.write_text(value)
print(f'verified {len(files)} runtime source files')
