#!/usr/bin/env python3
"""Build hash-verified executable bindings from explicit immutable Nix package roots."""
import hashlib
import json
import os
import sys
from pathlib import Path

entries = json.loads(Path(sys.argv[1]).read_text())
bindings = {}
for row in entries:
    root = Path(row['root'])
    executables = {}
    for directory in ('bin', 'sbin'):
        if not (root / directory).is_dir():
            continue
        for path in sorted((root / directory).iterdir()):
            if path.is_file() and os.access(path, os.X_OK):
                executables[path.name] = {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if executables:
        bindings[row['package']] = {'installation': 'nix-pinned', 'version': row['version'], 'executables': executables}
Path(sys.argv[2]).write_text(json.dumps({'toolInstallations': bindings}, indent=2) + '\n')
