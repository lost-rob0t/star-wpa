#!/usr/bin/env python3
"""Verify an exact Git checkout or immutable exported StarLang runtime source."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
lock = json.loads((root / 'schema/starintel-schema.lock.json').read_text())
runtime_lock = json.loads((root / 'schema/starlang-runtime.lock.json').read_text())
source = os.environ.get('STARLANG_SOURCE')
if not source:
    raise SystemExit('STARLANG_SOURCE must name the locked checkout/export')
source = Path(source)
if runtime_lock['canonical_commit'] != lock['canonical_commit']:
    raise SystemExit('runtime and schema pins disagree')
if (source / '.git').exists():
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != lock['canonical_commit']:
        raise SystemExit('runtime revision does not match the consumer lock')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain']).strip():
        raise SystemExit('runtime checkout is dirty')
files = {p.relative_to(source).as_posix() for directory in runtime_lock['sourceDirectories']
         for p in (source / directory).rglob('*') if p.is_file() and p.suffix in ('.lisp', '.asd')}
if files != set(runtime_lock['files']):
    raise SystemExit('exported runtime source closure differs from lock')
for name, expected in runtime_lock['files'].items():
    if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
        raise SystemExit('runtime source hash mismatch: ' + name)
for local, entry in lock['vendored_files'].items():
    if (source / entry['source']).read_bytes() != (root / local).read_bytes():
        raise SystemExit('runtime/schema export mismatch: ' + entry['source'])
subprocess.run(['python3', str(root / 'scripts/sync-starintel-schema.py'), '--lock',
                str(root / 'schema/starintel-schema.lock.json'), '--offline'], check=True)
