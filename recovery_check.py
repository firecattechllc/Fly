"""Verify the newest FLY recovery pair without modifying live data."""
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path

DEST = Path(os.environ.get("FLY_BACKUP_DIR", Path.home() / "FLY-Backups"))


def verify_pair(directory=DEST):
    directory = Path(directory)
    if not directory.is_dir():
        raise RuntimeError("Backup directory not found")
    database_files = sorted(directory.glob("fly-*.sqlite3"))
    if not database_files:
        raise RuntimeError("No FLY database backup found")
    db_path = database_files[-1]
    owner_path = directory / (db_path.stem + ".owner-auth.json")
    if not owner_path.is_file():
        raise RuntimeError("Latest recovery pair is incomplete (missing owner record)")
    for path in (db_path, owner_path):
        if not stat.S_ISREG(path.lstat().st_mode) or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError("Recovery file permissions are unsafe")
    with sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup database integrity check failed")
        db.execute("SELECT cash FROM account WHERE id=1").fetchone()
        db.execute("SELECT COUNT(*) FROM positions").fetchone()
        db.execute("SELECT COUNT(*) FROM events").fetchone()
    owner = json.loads(owner_path.read_bytes())
    if (owner.get("algorithm") != "pbkdf2-sha256"
            or owner.get("iterations") != 310000
            or len(bytes.fromhex(owner.get("salt", ""))) != 32
            or len(bytes.fromhex(owner.get("digest", ""))) != 32):
        raise RuntimeError("Owner verifier record invalid")
    return {"database": "ok", "owner_record": "ok", "files_private": True,
            "backup_id": db_path.stem}


if __name__ == "__main__":
    print(json.dumps(verify_pair(), sort_keys=True))
