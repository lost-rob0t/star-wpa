#!/usr/bin/env python3
"""Fail closed when a caller substitutes an unpinned StarLang runtime."""
import json
import os
import subprocess
from pathlib import Path
root = Path(__file__).resolve().parent.parent
lock = json.loads((root / 'schema/starintel-schema.lock.json').read_text())
source = os.environ.get('STARLANG_SOURCE')
if not source:
    raise SystemExit('STARLANG_SOURCE must name the locked checkout')
actual = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
if actual != lock['canonical_commit']:
    raise SystemExit('runtime revision does not match the consumer lock')
if subprocess.check_output(['git', '-C', source, 'status', '--porcelain']).strip():
    raise SystemExit('runtime checkout is dirty')
subprocess.run(['python3', str(root / 'scripts/sync-starintel-schema.py'), '--lock', str(root / 'schema/starintel-schema.lock.json'), '--source', source], check=True)
