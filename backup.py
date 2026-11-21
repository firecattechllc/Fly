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

if __name__ == "__main__":
    print(backup())
