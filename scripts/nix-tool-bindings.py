#!/usr/bin/env python3
"""Build validated executable bindings; absent supported commands are build failures.

This only reads package outputs. It never starts tools, services, or hardware.
"""
import hashlib
import json
import os
import sys
from pathlib import Path


def build_bindings(inputs):
    # Keep the original list input usable by downstream fixture builders.
    entries = inputs if isinstance(inputs, list) else inputs['packages']
    coverage = [] if isinstance(inputs, list) else inputs.get('coverage', [])
    bindings = {}
    for row in entries:
        root = Path(row['root'])
        executables = {}
        selection = row.get('selectExecutables')
        prefix = row.get('executablePrefix')
        for directory in ('bin', 'sbin'):
            if not (root / directory).is_dir():
                continue
            for path in sorted((root / directory).iterdir()):
                if path.name.startswith('.') or (selection is not None and path.name not in selection):
                    continue
                if prefix and not path.name.startswith(prefix):
                    continue
                if path.is_file() and os.access(path, os.X_OK):
                    if path.stat().st_size > 64 * 1024 * 1024:
                        raise ValueError(f'{row["package"]}: executable exceeds runtime hashing bound: {path.name}')
                    entry = {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    if path.name in executables and executables[path.name] != entry:
                        raise ValueError(f'{row["package"]}: ambiguous executable: {path.name}')
                    executables[path.name] = entry
        missing = set(row.get('requiredExecutables', [])) - executables.keys()
        if missing or not executables:
            raise ValueError(f'{row["package"]}: missing required executables: {sorted(missing) or "any bin/sbin executable"}')
        if row['package'] in bindings:
            raise ValueError(f'duplicate package: {row["package"]}')
        bindings[row['package']] = {'installation': 'nix-pinned', 'version': row['version'], 'executables': executables}
    return {'toolInstallations': bindings, 'toolCoverage': coverage}


def main():
    inputs = json.loads(Path(sys.argv[1]).read_text())
    Path(sys.argv[2]).write_text(json.dumps(build_bindings(inputs), indent=2) + '\n')


if __name__ == '__main__':
    main()
