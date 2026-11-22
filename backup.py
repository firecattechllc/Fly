"""Consistent, private SQLite backups with integrity verification."""
import datetime
import os
import sqlite3
from pathlib import Path

os.umask(0o077)
SOURCE = Path(os.environ.get("FLY_DB", Path(__file__).parent / "data" / "paper.db"))
DEST = Path(os.environ.get("FLY_BACKUP_DIR", Path.home() / "FLY-Backups"))

def backup(source=SOURCE, destination=DEST):
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise RuntimeError("Source database missing; no backup created")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination, 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = destination / ("fly-" + stamp + ".sqlite3")
    a = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    b = sqlite3.connect(str(target))
    try:
        a.backup(b)
        if b.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity verification failed")
        # Keep backup standalone: do not leave WAL/SHM dependencies beside it.
        b.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        mode = b.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if mode.lower() != "delete":
            raise RuntimeError("Could not finalize standalone backup")
        if b.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Final backup integrity verification failed")
    except Exception:
        b.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        a.close()
        try:
            b.close()
        except Exception:
            pass
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists():
            os.chmod(sidecar, 0o600)
            sidecar.unlink()
    os.chmod(target, 0o600)
    os.chmod(destination, 0o700)
    return str(target)

def backup_owner(auth_path, destination, database_backup):
    """Copy the owner verifier privately; never include it in Git or logs."""
    import hashlib
    import json
    import stat

    auth_path = Path(auth_path)
    if not auth_path.exists():
        return False  # First-run installation before account creation.
    metadata = auth_path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("Owner authentication file is not a private regular file")
    payload = auth_path.read_bytes()
    record = json.loads(payload)
    if (record.get("algorithm") != "pbkdf2-sha256"
            or not isinstance(record.get("digest"), str)
            or not isinstance(record.get("salt"), str)):
        raise RuntimeError("Owner authentication record invalid")
    backup_path = Path(destination) / (Path(database_backup).stem + ".owner-auth.json")
    fd = os.open(str(backup_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if hashlib.sha256(backup_path.read_bytes()).digest() != hashlib.sha256(payload).digest():
            raise RuntimeError("Owner authentication backup mismatch")
        os.chmod(backup_path, 0o600)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
    return True


def backup_system():
    """Create a SQLite snapshot and, if configured, a paired owner verifier."""
    db_backup = backup()
    auth_path = Path(os.environ.get("FLY_AUTH_PATH",
                      Path(__file__).parent / "data" / "owner-auth.json"))
    try:
        backup_owner(auth_path, DEST, db_backup)
    except Exception:
        # Avoid reporting a partial backup as a successful complete recovery set.
        Path(db_backup).unlink(missing_ok=True)
        raise
    return db_backup


if __name__ == "__main__":
    print(backup_system())
