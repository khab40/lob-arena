"""Integration checks for copied-ref recovery using isolated Git repositories."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "repair_duplicate_git_refs.py"


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "--allow-empty", "-m", "first")
        self.first = self.git("rev-parse", "HEAD")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "--allow-empty", "-m", "second")
        self.second = self.git("rev-parse", "HEAD")
        self.copies = {"a 2": self.first, "z 2": self.second}
        for name, oid in self.copies.items():
            (self.root / ".git/refs/heads" / name).write_text(oid + "\n")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True, stderr=subprocess.PIPE
        ).strip()

    def run_repair(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              cwd=self.root, capture_output=True, text=True)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / ".git").rglob("*") if p.is_file()}

    def test_later_recovery_conflict_leaves_all_metadata_unchanged(self):
        self.git("update-ref", "refs/recovery/copied-refs/" + self.second, self.first)
        before = self.snapshot()
        for args in [(), ("--apply",)]:
            with self.subTest(args=args):
                result = self.run_repair(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Conflicting recovery ref", result.stderr)
                self.assertEqual(before, self.snapshot())

    def test_matching_recovery_ref_and_repeated_commit_are_supported(self):
        self.git("update-ref", "refs/recovery/copied-refs/" + self.second, self.second)
        self.copies["b 2"] = self.first
        (self.root / ".git/refs/heads/b 2").write_text(self.first + "\n")
        before = self.snapshot()
        self.assertEqual(self.run_repair().returncode, 0)
        self.assertEqual(before, self.snapshot())
        result = self.run_repair("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, oid in self.copies.items():
            self.assertFalse((self.root / ".git/refs/heads" / name).exists())
            backup = self.root / ".git/ref-copy-backups/refs/heads" / name
            self.assertEqual(backup.read_text(), oid + "\n")
            self.assertEqual(self.git("rev-parse", "refs/recovery/copied-refs/" + oid), oid)
        after = self.snapshot()
        self.assertEqual(self.run_repair("--apply").returncode, 0)
        self.assertEqual(after, self.snapshot())


if __name__ == "__main__":
    unittest.main()
