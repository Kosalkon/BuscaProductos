"""Build, compare and atomically publish product updates."""
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.delta_generator import write_operations
from core.github_publisher import GitHubPublisher
from core.version_manager import VersionManager
from database.builder import DatabaseBuilder


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Publisher:
    def __init__(self, config, logger):
        self.config, self.logger = config, logger
        self.output = Path(config["paths"]["output_dir"])
        self.state = Path(config["paths"]["state_dir"])
        self.snapshot = self.state / "current.sqlite"
        self.versions = VersionManager(self.state)
        self.github = GitHubPublisher(config["github"], logger)

    def publish_update(self):
        """Return metadata only when the resulting database has real changes."""
        self.output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.output) as directory:
            temporary = Path(directory)
            database = temporary / "products.sqlite"
            summary = DatabaseBuilder(self.config, self.logger).build(database)
            operations, counts = None, None
            if self.snapshot.exists():
                operations = temporary / "operations.jsonl"
                counts = write_operations(self.snapshot, database, operations)
                if counts == {"upsert": 0, "delete": 0}:
                    self.logger.info("Processed sources but their effective content is unchanged.")
                    return None
            version = self.versions.next_version()
            full = not self.snapshot.exists() or self._is_snapshot_version(version)
            package, metadata = self._create_package(temporary, database, operations, counts, version, full, summary)
            catalog = self._next_catalog(metadata)
            version_file, catalog_file = temporary / "version.json", temporary / "catalog.json"
            version_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            catalog_file.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
            self.github.publish(version, [package, version_file, catalog_file])
            for file in (package, version_file, catalog_file):
                self._copy_to_output(file)
            self._replace_snapshot(database)
            self.versions.save(metadata)
            self._save_catalog(catalog)
        self.logger.info("Published %s v%s", metadata["kind"], version)
        return metadata

    def repair_legacy_empty_deltas(self):
        """Remove old local metadata entries produced by the pre-content-check bug.

        Package files are deliberately left on disk; only unreachable metadata is repaired.
        This never runs when GitHub publishing is enabled because a remote release cannot be
        safely rewritten from this machine.
        """
        if self.config["github"]["enabled"]:
            return
        path = self.state / "catalog.json"
        if not path.exists():
            return
        catalog = json.loads(path.read_text(encoding="utf-8"))
        updates = list(catalog.get("updates", []))
        original_count = len(updates)
        while updates and self._is_empty_delta(updates[-1]):
            updates.pop()
        if len(updates) == original_count or not updates:
            return
        catalog["updates"] = updates
        catalog["current_version"] = updates[-1]["version"]
        metadata = updates[-1]
        self._save_catalog(catalog)
        self.versions.save(metadata)
        self._write_output_metadata("catalog.json", catalog)
        self._write_output_metadata("version.json", metadata)
        self.logger.info("Removed legacy empty delta metadata; current version is v%s.", metadata["version"])

    @staticmethod
    def _is_empty_delta(metadata):
        return metadata.get("kind") == "delta" and metadata.get("summary", {}).get("operations") == {"upsert": 0, "delete": 0}

    def _is_snapshot_version(self, version):
        return version % int(self.config["updates"]["full_snapshot_interval"]) == 0

    def _create_package(self, temporary, database, operations, counts, version, full, summary):
        kind = "full" if full else "delta"
        manifest = {"format_version": 1, "kind": kind, "version": version, "previous_version": None if full else version - 1, "schema_version": 1, "release_tag": f"products-v{version}"}
        package = temporary / f"{kind}-v{version}.zip"
        content = (database, "products.sqlite") if full else (operations, "operations.jsonl")
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
            archive.write(*content)
        metadata = {**manifest, "file": package.name, "sha256": sha256(package), "size_bytes": package.stat().st_size, "created_at": datetime.now(timezone.utc).isoformat(), "summary": {**summary, "operations": None if full else counts}}
        return package, metadata

    def _next_catalog(self, metadata):
        path = self.state / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"format_version": 1, "updates": []}
        catalog["updates"].append(metadata)
        catalog["current_version"] = metadata["version"]
        return catalog

    def _save_catalog(self, catalog):
        path = self.state / "catalog.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _write_output_metadata(self, name, content):
        path = self.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _copy_to_output(self, source):
        destination = self.output / source.name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)

    def _replace_snapshot(self, database):
        self.state.mkdir(parents=True, exist_ok=True)
        temporary = self.snapshot.with_suffix(".tmp")
        shutil.copy2(database, temporary)
        temporary.replace(self.snapshot)
