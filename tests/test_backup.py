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

    def test_owner_verifier_backup_is_private_and_matches(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            auth_file=root/"owner-auth.json"
            contents=json.dumps({"algorithm":"pbkdf2-sha256","iterations":310000,
                                 "salt":"a"*64,"digest":"b"*64}).encode()
            auth_file.write_bytes(contents)
            auth_file.chmod(0o600)
            target=root/"backups"
            target.mkdir(mode=0o700)
            source_db=target/"fly-demo.sqlite3"
            source_db.write_bytes(b"test placeholder")
            self.assertTrue(backup.backup_owner(auth_file,target,source_db))
            saved=target/"fly-demo.owner-auth.json"
            self.assertEqual(saved.read_bytes(),contents)
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode),0o600)
    def test_owner_verifier_insecure_permissions_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            auth_file=root/"owner-auth.json"
            auth_file.write_text(json.dumps({"algorithm":"pbkdf2-sha256","salt":"a","digest":"b"}))
            auth_file.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError,"not a private"):
                backup.backup_owner(auth_file,root,root/"fly-test.sqlite3")
            self.assertFalse((root/"fly-test.owner-auth.json").exists())

    def test_complete_recovery_pair_verifies_without_live_data(self):
        import json
        import recovery_check
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"paper.db"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE account(id INTEGER PRIMARY KEY,cash INTEGER)")
                db.execute("INSERT INTO account VALUES(1,1000)")
                db.execute("CREATE TABLE positions(symbol TEXT)")
                db.execute("CREATE TABLE events(id INTEGER)")
            destination=root/"backups"
            db_snapshot=backup.backup(source,destination)
            owner=root/"owner-auth.json"
            owner.write_text(json.dumps({"algorithm":"pbkdf2-sha256","iterations":310000,
                "salt":"a"*64,"digest":"b"*64}))
            owner.chmod(0o600)
            self.assertTrue(backup.backup_owner(owner,destination,db_snapshot))
            result=recovery_check.verify_pair(destination)
            self.assertEqual(result["database"],"ok")
            self.assertEqual(result["owner_record"],"ok")
            self.assertTrue(result["files_private"])
            Path(db_snapshot).with_name(Path(db_snapshot).stem+".owner-auth.json").unlink()
            with self.assertRaisesRegex(RuntimeError,"incomplete"):
                recovery_check.verify_pair(destination)

if __name__ == "__main__": unittest.main()
