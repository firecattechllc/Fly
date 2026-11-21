import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
import backup

class BackupTests(unittest.TestCase):
    def test_backup_is_standalone_private_and_integral(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"source.db"
            destination=root/"backups"
            db=sqlite3.connect(source)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE sample(value TEXT)")
            db.execute("INSERT INTO sample VALUES('private-data')")
            db.commit()
            result=Path(backup.backup(source,destination))
            db.close()
            self.assertTrue(result.is_file())
            with sqlite3.connect(result) as restored:
                self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(restored.execute("SELECT value FROM sample").fetchone()[0],"private-data")
                self.assertEqual(restored.execute("PRAGMA journal_mode").fetchone()[0],"delete")
            self.assertEqual(stat.S_IMODE(result.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode),0o700)
            for suffix in ("-wal","-shm","-journal"):
                self.assertFalse(Path(str(result)+suffix).exists())
    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                backup.backup(Path(tmp)/"missing.db",Path(tmp)/"backups")

if __name__ == "__main__": unittest.main()
