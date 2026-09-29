import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.publisher import Publisher


class SilentLogger:
    def info(self, *args):
        pass


class FakeBuilder:
    records = []

    def __init__(self, config, logger):
        pass

    def build(self, destination):
        connection = sqlite3.connect(destination)
        connection.executescript("""
            CREATE TABLE products (id TEXT PRIMARY KEY, internal_code TEXT NOT NULL,
                barcode TEXT, name TEXT NOT NULL, active INTEGER NOT NULL, raw_json TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE equivalents (code TEXT PRIMARY KEY, product_id TEXT NOT NULL) WITHOUT ROWID;
        """)
        for record in self.records:
            connection.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)", record)
        connection.commit()
        connection.close()
        return {"products": len(self.records), "skipped": 0}


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.config = {
            "paths": {"output_dir": str(root / "output"), "state_dir": str(root / "state")},
            "updates": {"full_snapshot_interval": 20},
            "github": {"enabled": False},
        }
        self.publisher = Publisher(self.config, SilentLogger())
        self.builder = patch("core.publisher.DatabaseBuilder", FakeBuilder)
        self.builder.start()
        FakeBuilder.records = [("1", "1", "111", "Uno", 1, "{}")]

    def tearDown(self):
        self.builder.stop()
        self.directory.cleanup()

    def test_first_build_then_no_change_or_forced_empty_delta(self):
        first = self.publisher.publish_update()
        self.assertEqual((first["kind"], first["version"]), ("full", 1))
        before = (self.publisher.versions.path.read_bytes(), (self.publisher.state / "catalog.json").read_bytes())
        self.assertIsNone(self.publisher.publish_update())  # normal no-change path
        self.assertIsNone(self.publisher.publish_update())  # --force reaches this same content check
        after = (self.publisher.versions.path.read_bytes(), (self.publisher.state / "catalog.json").read_bytes())
        self.assertEqual(before, after)
        self.assertFalse((Path(self.config["paths"]["output_dir"]) / "delta-v2.zip").exists())

    def test_modify_add_and_delete_produce_expected_deltas(self):
        self.publisher.publish_update()
        FakeBuilder.records = [("1", "1", "111", "Uno modificado", 1, "{}")]
        changed = self.publisher.publish_update()
        self.assertEqual(changed["summary"]["operations"], {"upsert": 1, "delete": 0})
        FakeBuilder.records.append(("2", "2", "222", "Dos", 1, "{}"))
        added = self.publisher.publish_update()
        self.assertEqual(added["summary"]["operations"], {"upsert": 1, "delete": 0})
        FakeBuilder.records = [FakeBuilder.records[1]]
        deleted = self.publisher.publish_update()
        self.assertEqual(deleted["summary"]["operations"], {"upsert": 0, "delete": 1})
        package = Path(self.config["paths"]["output_dir"]) / deleted["file"]
        with zipfile.ZipFile(package) as archive:
            operations = [json.loads(line) for line in archive.read("operations.jsonl").decode().splitlines()]
        self.assertEqual(operations, [{"op": "delete", "table": "products", "key": "1"}])

    def test_failed_build_preserves_last_valid_state(self):
        self.publisher.publish_update()
        previous = self.publisher.versions.path.read_bytes()
        with patch("core.publisher.DatabaseBuilder", side_effect=RuntimeError("DBF failure")):
            with self.assertRaisesRegex(RuntimeError, "DBF failure"):
                self.publisher.publish_update()
        self.assertEqual(self.publisher.versions.path.read_bytes(), previous)

    def test_legacy_empty_delta_metadata_is_repaired(self):
        first = self.publisher.publish_update()
        catalog = {"format_version": 1, "current_version": 2, "updates": [first, {**first, "kind": "delta", "version": 2, "previous_version": 1, "summary": {"operations": {"upsert": 0, "delete": 0}}}]}
        (self.publisher.state / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        self.publisher.versions.save(catalog["updates"][-1])
        self.publisher.repair_legacy_empty_deltas()
        repaired = json.loads((self.publisher.state / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(repaired["current_version"], 1)
        self.assertEqual(len(repaired["updates"]), 1)


if __name__ == "__main__":
    unittest.main()
