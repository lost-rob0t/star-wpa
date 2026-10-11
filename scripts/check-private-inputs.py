#!/usr/bin/env python3
"""Reject tracked operator geography and raw packet-capture files."""
import subprocess
from pathlib import PurePosixPath


def main():
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    forbidden = {'.kml', '.kmz', '.pcap', '.pcapng', '.cap'}
    count = sum(PurePosixPath(name).suffix.lower() in forbidden for name in names if name)
    if count:
        # Do not expose possibly sensitive route/capture filenames in CI logs.
        raise SystemExit(f'private input guard: {count} forbidden tracked file(s)')
    print('private input guard: passed')


if __name__ == '__main__':
    main()
