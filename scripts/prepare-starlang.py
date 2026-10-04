#!/usr/bin/env python3
"""Fetch exactly the consumer's locked StarLang runtime; never follow a branch."""
import argparse
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
lock = json.loads((root / 'schema/starintel-schema.lock.json').read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--destination', type=Path, default=root / '.cache/star-lang')
args = parser.parse_args()
path = args.destination.resolve()
if not path.exists():
    path.mkdir(parents=True)
    subprocess.run(['git', 'init', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'remote', 'add', 'origin', 'https://github.com/' + lock['canonical_repository'] + '.git'], check=True)
if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain']).strip():
    raise SystemExit('refusing to change a dirty StarLang checkout')
subprocess.run(['git', '-C', str(path), 'fetch', '--depth', '1', 'origin', lock['canonical_commit']], check=True)
subprocess.run(['git', '-C', str(path), 'checkout', '--detach', lock['canonical_commit']], check=True)
subprocess.run(['python3', str(root / 'scripts/sync-starintel-schema.py'), '--lock', str(root / 'schema/starintel-schema.lock.json'), '--source', str(path)], check=True)
print(path)
