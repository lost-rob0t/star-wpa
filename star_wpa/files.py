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


# Large Go/GUI tool binaries can exceed the input-document limits. Stream them
# in constant memory, while retaining a finite bound on the opened object.
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024


def sha256_bounded(path, maximum=MAX_EXECUTABLE_BYTES):
    import hashlib
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError('input must be a regular file')
        if metadata.st_size > maximum:
            raise ValueError('executable exceeds hashing byte limit')
        total = 0
        while True:
            chunk = source.read(min(1024 * 1024, maximum - total + 1))
            if not chunk:
                return digest.hexdigest()
            total += len(chunk)
            if total > maximum:
                raise ValueError('executable exceeds hashing byte limit')
            digest.update(chunk)
