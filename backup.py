"""Consistent SQLite backup with integrity check; keeps all snapshots."""
import datetime
import os
import sqlite3
from pathlib import Path

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
    except Exception:
        b.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        a.close()
        try: b.close()
        except Exception: pass
    os.chmod(target, 0o600)
    return str(target)

if __name__ == "__main__":
    print(backup())
