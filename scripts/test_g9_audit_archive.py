"""Inert clean-checkout and corruption checks for the portable audit."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location(
    "g9_audit", Path(__file__).with_name("verify_g9_audit_archive.py")
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
SOURCE = Path(__file__).resolve().parents[1]


class PortableAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        proposal = json.loads((SOURCE / "docs/evidence/g9-exit-proposal-20260927.json").read_text())
        decision = json.loads((SOURCE / "docs/evidence/g9-exit-decision-20260927.json").read_text())
        paths = set(proposal["evidence_bindings"]) | set(decision["approved_artifacts"])
        paths.update(["docs/evidence/g9-exit-decision-20260927.json",
                      "docs/evidence/g9-artifact-audit-20260927.json"])
        for name in paths:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, dest)
        self.directory = self.root / "docs/evidence/g9-audit-20260927"
        shutil.copytree(SOURCE / "docs/evidence/g9-audit-20260927", self.directory)

    def test_clean_checkout_without_outputs(self):
        self.assertFalse((self.root / "outputs").exists())
        result = audit.verify(self.root)
        self.assertEqual(result["object_identities"], 176)
        self.assertFalse(result["payload_bytes_rehashed"])

    def test_changed_assembler(self):
        with (self.directory / "assemble.py.txt").open("ab") as file:
            file.write(b"\n")
        with self.assertRaisesRegex(ValueError, "assembler anchor"):
            audit.verify(self.root)

    def test_changed_archive(self):
        with (self.directory / "metadata.zip").open("ab") as file:
            file.write(b"changed")
        with self.assertRaisesRegex(ValueError, "archive hash"):
            audit.verify(self.root)

    def test_rehashed_manifest_cannot_replace_anchored_receipt(self):
        archive = self.directory / "metadata.zip"
        manifest_path = self.directory / "archive.json"
        manifest = json.loads(manifest_path.read_text())
        with zipfile.ZipFile(archive) as zipped:
            blobs = {name: zipped.read(name) for name in zipped.namelist()}
        name = "outputs/g8-final-execution-20260923/independent-s3/verification.json"
        changed = json.loads(blobs[name])
        changed["objects"][0]["sha256"] = "0" * 64
        blobs[name] = json.dumps(changed).encode()
        manifest["files"][name] = {"sha256": audit.sha(blobs[name]), "size_bytes": len(blobs[name])}
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, data in blobs.items():
                zipped.writestr(name, data)
        manifest.update(archive_sha256=audit.sha(archive.read_bytes()), archive_size_bytes=archive.stat().st_size)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "S3 receipt anchor"):
            audit.verify(self.root)


if __name__ == "__main__":
    unittest.main()
