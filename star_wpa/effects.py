"""Local at-most-once admission for active effects; uncertain attempts stay blocked."""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from .contracts import validate_bundle


def run_once(actor, request, operation):
    path = os.environ.get('STAR_WPA_EFFECT_DB')
    if not path:
        raise PermissionError('active effects require an operator-local effect ledger')
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    key = json.dumps([request['dataset'], actor, request['requestId']])
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()
    with closing(sqlite3.connect(target, timeout=5)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS effects (identity TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT)')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT fingerprint, status, receipt FROM effects WHERE identity=?', (key,)).fetchone()
        if row:
            db.rollback()
            if row[0] != fingerprint:
                raise ValueError('requestId reused with a different active effect')
            if row[1] != 'completed':
                raise PermissionError('previous active effect has an uncertain outcome; operator reconciliation required')
            return validate_bundle(json.loads(row[2]))
        db.execute('INSERT INTO effects VALUES (?, ?, ?, NULL)', (key, fingerprint, 'started'))
        db.commit()
        # A timeout, process error, crash or interruption leaves started, never a false completion.
        docs = operation()
        validate_bundle(docs)
        db.execute('UPDATE effects SET status=?, receipt=? WHERE identity=?',
                   ('completed', json.dumps(docs, allow_nan=False), key))
        db.commit()
        return docs
