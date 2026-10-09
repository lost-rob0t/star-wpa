#!/usr/bin/env python3
"""Check built Nix package discovery outside the source tree, without executing tools."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from star_wpa.contracts import NS
from star_wpa.tools import CATALOG, dispatch_tool


def main():
    runtime, manifest_path, coverage_path = map(Path, sys.argv[1:])
    manifest = json.loads(manifest_path.read_text())
    coverage = json.loads(coverage_path.read_text())
    assert {row['package'] for row in coverage} == set(CATALOG)
    supported = {row['package'] for row in coverage if row['available']}
    assert set(manifest['toolInstallations']) == supported
    os.environ['STAR_WPA_NIX_TOOL_MANIFEST'] = str(manifest_path)
    request = {'dataset': 'nix-offline-discovery', 'operation': 'discover'}
    with tempfile.TemporaryDirectory() as directory:
        request_path = Path(directory) / 'request.json'
        request_path.write_text(json.dumps(request))
        for row in coverage:
            package = row['package']
            # Import from the installed Python environment, never the checkout.
            result = dispatch_tool(package, request)[0]['extensions'][NS]
            expected = 'installed' if package in supported else 'nix-unavailable'
            assert result['status'] == expected, (package, result)
            # Empty PATH and no inherited manifest prove each packaged wrapper
            # supplies the immutable binding, including when launched on Ubuntu.
            env = dict(os.environ, PATH='')
            env.pop('STAR_WPA_NIX_TOOL_MANIFEST', None)
            process = subprocess.run([str(runtime / 'bin' / ('sa-tool-' + package)),
                                      '--request', str(request_path)],
                                     cwd=directory, env=env, text=True,
                                     capture_output=True, timeout=60, check=True)
            wrapped = json.loads(process.stdout)[0]['extensions'][NS]
            assert wrapped == result, (package, wrapped, result)
            if package in supported:
                assert result['installation'] == 'nix-pinned'
                names = {item['name'] for item in result['executables']}
                assert names and set(row['requiredExecutables']) <= names, (package, names)
                assert all(item['path'].startswith('/nix/store/') for item in result['executables'])
            else:
                assert result['reason'] and not result['executables']
    print(json.dumps({'catalogPackages': len(coverage), 'verifiedPackages': len(supported),
                      'unsupported': sorted(set(CATALOG) - supported),
                      'radioToolsExecuted': False}, sort_keys=True))


if __name__ == '__main__':
    main()
