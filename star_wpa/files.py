"""Read regular files with a byte bound on the opened object, not path metadata."""
import os
import stat


def read_bounded(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError('input must be a regular file')
        raw = source.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('input exceeds byte limit')
    return raw
