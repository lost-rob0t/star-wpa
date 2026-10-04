#!/usr/bin/env python3
"""Real native actor/process proof using an explicitly substituted external-tool fixture."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='star-wpa-native-tool-') as directory:
    base = Path(directory)
    tool = base / 'tool-fixture'
    tool.write_text('#!' + os.environ.get('STAR_WPA_TEST_SHELL', '/bin/sh') + '\nprintf "native-tool-port-fixture"\n')
    tool.chmod(0o700)
    descriptor = {'executable': 'tool-fixture', 'argv': ['--fixture'], 'workingDirectory': directory,
                  'stdinFile': None, 'uiMode': 'headless'}
    policy = {'toolCommands': {'wifiphisher': [descriptor]}, 'toolInstallations': {'wifiphisher': {
        'version': 'external-port-fixture', 'executables': {'tool-fixture': {
            'path': str(tool), 'sha256': hashlib.sha256(tool.read_bytes()).hexdigest()}}}}}
    # The fixture must be selected even on a machine with the genuine tool installed.
    # Native proof uses the explicit source binding via preferPinned in deployment policy.
    policy['toolInstallations']['wifiphisher']['preferPinned'] = True
    (base / 'policy.json').write_text(json.dumps(policy))
    (base / 'request.json').write_text(json.dumps(dict(descriptor, dataset='lab', operation='execute', requestId='native-tool-proof')))
    env = dict(os.environ, STAR_WPA_POLICY_FILE=str(base / 'policy.json'), STAR_WPA_EFFECT_DB=str(base / 'effects.sqlite'),
               STAR_WPA_NATIVE_TOOL_REQUEST=str(base / 'request.json'))
    subprocess.run([env.get('STAR_WPA_SBCL', 'sbcl'), '--script', str(root / 'scripts/native-proof.lisp')], env=env, check=True, cwd=root)
